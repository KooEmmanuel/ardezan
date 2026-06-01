import type {
  Address,
  BodyProfileStatus,
  CartLineInput,
  CategoryListResponse,
  CheckoutSessionPublic,
  Complexity,
  CostBreakdown,
  CustomerLoginResponse,
  CustomerPublic,
  DesignSessionCreateResponse,
  DesignSessionPublic,
  FabricPublic,
  JobCreatedResponse,
  JobPublic,
  PieceType,
  ProductDetail,
  ProductListResponse,
  RevalidateResponse,
  SavedPhotoStatus,
  SiteMediaResponse,
  TryOnFormInput,
  TryOnSessionDetail,
} from "@/lib/types";

// In production we leave ``NEXT_PUBLIC_API_BASE_URL`` empty so every
// API call becomes a relative URL like ``/api/v1/...``. The browser
// then hits the storefront origin (``www.ardezan.com``), Vercel's
// edge proxy forwards it to Railway via the ``rewrites()`` block in
// ``next.config.ts``. Net effect: the API appears same-origin, so
// session cookies are first-party and CORS goes away entirely.
//
// In dev we keep the absolute URL because there's nothing in front of
// the Next dev server to proxy through.
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type FetchOptions = RequestInit & {
  idempotencyKey?: string;
};

/**
 * Typed API error that preserves the backend's error envelope
 * (``{ error: { code, message, details } }``) so callers can branch on
 * ``code`` — e.g. show the "verify your email" banner on EMAIL_NOT_VERIFIED
 * rather than a generic toast. Still an ``Error`` subclass, so existing
 * ``err instanceof Error ? err.message`` handling keeps working.
 */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details: Record<string, unknown>;

  constructor(args: {
    code: string;
    message: string;
    status: number;
    details?: Record<string, unknown>;
  }) {
    super(args.message);
    this.name = "ApiError";
    this.code = args.code;
    this.status = args.status;
    this.details = args.details ?? {};
  }
}

/** True when a logged-in customer must verify their email before this action. */
export function isEmailNotVerified(err: unknown): err is ApiError {
  return err instanceof ApiError && err.code === "EMAIL_NOT_VERIFIED";
}

async function toApiError(
  response: Response,
  fallback: string,
): Promise<ApiError> {
  let code = "INTERNAL_ERROR";
  let message = `${fallback} (${response.status})`;
  let details: Record<string, unknown> = {};
  try {
    const body = (await response.json()) as {
      error?: {
        code?: string;
        message?: string;
        details?: Record<string, unknown>;
      };
    };
    if (body.error) {
      code = body.error.code ?? code;
      message = body.error.message ?? message;
      details = body.error.details ?? {};
    }
  } catch {
    // Non-JSON body — keep the generic message.
  }
  return new ApiError({ code, message, status: response.status, details });
}

async function apiFetch<T>(path: string, options: FetchOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (options.idempotencyKey) {
    headers.set("Idempotency-Key", options.idempotencyKey);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
    cache: "no-store",
    credentials: "include",
  });

  if (!response.ok) {
    throw await toApiError(response, "Request failed");
  }

  return (await response.json()) as T;
}

// Multipart sender — fetch sets the Content-Type with the boundary itself,
// so we must NOT pre-set it the way ``apiFetch`` does.
async function apiUpload<T>(path: string, body: FormData): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    body,
    cache: "no-store",
    credentials: "include",
  });
  if (!response.ok) {
    throw await toApiError(response, "Upload failed");
  }
  return (await response.json()) as T;
}

export function formatMoney(amount: number | undefined, currency = "USD"): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
  }).format((amount ?? 0) / 100);
}

export const api = {
  listProducts: (params?: { category?: string; q?: string }) => {
    const search = new URLSearchParams();
    if (params?.category) search.set("category", params.category);
    if (params?.q) search.set("q", params.q);
    const path = params?.q ? "/api/v1/catalog/search" : "/api/v1/catalog/products";
    return apiFetch<ProductListResponse>(`${path}?${search.toString()}`);
  },
  listCategories: () => apiFetch<CategoryListResponse>("/api/v1/catalog/categories"),
  getProduct: (slug: string) => apiFetch<ProductDetail>(`/api/v1/catalog/products/${slug}`),
  revalidateCart: (lines: CartLineInput[]) =>
    apiFetch<RevalidateResponse>("/api/v1/cart/revalidate", {
      method: "POST",
      body: JSON.stringify({ lines }),
    }),

  // Sends the anonymous localStorage cart up to the server on login/signup
  // so the customer doesn't lose what they had selected. Backend follows
  // REQ-044: same variant in both carts keeps the higher quantity, try-on
  // lines stay separate. Returns the merged server cart (we don't currently
  // mirror it back into localStorage because revalidate stays the source
  // of truth for the cart page).
  mergeAnonymousCart: (lines: CartLineInput[]) =>
    apiFetch<{ cart_id: string; lines: unknown[] }>("/api/v1/cart/merge", {
      method: "POST",
      body: JSON.stringify({ lines }),
    }),
  createCheckoutSession: (input: {
    lines: CartLineInput[];
    guest_email: string;
    shipping_address: Address;
    shipping_method?: "standard" | "express";
  }) =>
    apiFetch<CheckoutSessionPublic>("/api/v1/checkout/sessions", {
      method: "POST",
      idempotencyKey: `checkout_${crypto.randomUUID()}`,
      body: JSON.stringify({ shipping_method: "standard", ...input }),
    }),

  // ── Try-on (M4) ────────────────────────────────────────────────
  createTryOnSession: (photo: File, fields: TryOnFormInput) => {
    const body = new FormData();
    body.set("photo", photo, photo.name);
    body.set("age_confirmed", String(fields.age_confirmed));
    if (fields.height) body.set("height", fields.height);
    if (fields.fit_preference) body.set("fit_preference", fields.fit_preference);
    if (fields.occasion) body.set("occasion", fields.occasion);
    if (fields.prompt) body.set("prompt", fields.prompt);
    if (fields.seeded_product_id) body.set("seeded_product_id", fields.seeded_product_id);
    if (fields.anonymous_session_id) {
      body.set("anonymous_session_id", fields.anonymous_session_id);
    }
    return apiUpload<JobCreatedResponse>("/api/v1/try-on/sessions", body);
  },

  getTryOnJob: (jobId: string) =>
    apiFetch<JobPublic>(`/api/v1/try-on/jobs/${jobId}`),

  getTryOnSession: (sessionId: string) =>
    apiFetch<TryOnSessionDetail>(`/api/v1/try-on/sessions/${sessionId}`),

  refineTryOnSession: (sessionId: string, prompt: string) =>
    apiFetch<JobCreatedResponse>(
      `/api/v1/try-on/sessions/${sessionId}/refine`,
      { method: "POST", body: JSON.stringify({ prompt }) },
    ),

  // ── Site media (branded UI images) ─────────────────────────────
  getSiteMedia: () => apiFetch<SiteMediaResponse>("/api/v1/site/media"),

  // ── Customer auth (M5) ─────────────────────────────────────────
  // ``anonymous_session_id`` lets the backend claim any sessions the
  // customer created before they had an account, so their first visit
  // to the activity hub isn't empty.
  signup: (input: {
    email: string;
    password: string;
    name: string;
    accepts_marketing?: boolean;
    anonymous_session_id?: string;
  }) =>
    apiFetch<CustomerLoginResponse>("/api/v1/auth/signup", {
      method: "POST",
      body: JSON.stringify({ accepts_marketing: false, ...input }),
    }),

  login: (input: {
    email: string;
    password: string;
    anonymous_session_id?: string;
  }) =>
    apiFetch<CustomerLoginResponse>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify(input),
    }),

  logout: () =>
    apiFetch<{ status: string }>("/api/v1/auth/logout", { method: "POST" }),

  getMe: () => apiFetch<CustomerPublic>("/api/v1/account/me"),

  confirmEmailVerification: (token: string) =>
    apiFetch<{ verified: boolean }>("/api/v1/auth/verify-email/confirm", {
      method: "POST",
      body: JSON.stringify({ token }),
    }),

  requestEmailVerification: () =>
    apiFetch<{ queued: boolean }>("/api/v1/auth/verify-email/request", {
      method: "POST",
      body: JSON.stringify({}),
    }),

  requestPasswordReset: (email: string) =>
    fetch(`${API_BASE_URL}/api/v1/auth/password-reset`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
      credentials: "include",
    }).then((r) => {
      if (!r.ok && r.status !== 204)
        throw new Error(`reset request failed: ${r.status}`);
      return { ok: true };
    }),

  confirmPasswordReset: (input: { token: string; new_password: string }) =>
    apiFetch<{ reset: boolean }>("/api/v1/auth/password-reset/confirm", {
      method: "POST",
      body: JSON.stringify(input),
    }),

  // ── Saved photo + body profile ─────────────────────────────────
  getSavedPhotoStatus: () =>
    apiFetch<SavedPhotoStatus>("/api/v1/account/saved-photo"),

  optInSavedPhoto: (input: { try_on_session_id: string; consent_version?: string }) =>
    apiFetch<SavedPhotoStatus>("/api/v1/account/saved-photo", {
      method: "POST",
      body: JSON.stringify({ consent_version: "v1", ...input }),
    }),

  deleteSavedPhoto: () =>
    apiFetch<SavedPhotoStatus>("/api/v1/account/saved-photo", { method: "DELETE" }),

  getBodyProfileStatus: () =>
    apiFetch<BodyProfileStatus>("/api/v1/account/body-profile"),

  optInBodyProfile: (input: { try_on_session_id: string }) =>
    apiFetch<BodyProfileStatus>("/api/v1/account/body-profile", {
      method: "POST",
      body: JSON.stringify(input),
    }),

  deleteBodyProfile: () =>
    apiFetch<BodyProfileStatus>("/api/v1/account/body-profile", { method: "DELETE" }),

  listFittingRoom: () =>
    apiFetch<{
      items: { try_on_session_id: string; representative_outfit_name: string | null; created_at: string }[];
    }>("/api/v1/account/fitting-room?limit=20"),

  // ── Design Me ──────────────────────────────────────────────────
  listFabrics: () =>
    apiFetch<{ items: FabricPublic[] }>("/api/v1/fabrics"),

  estimateFabric: (
    fabricId: string,
    piece_type: PieceType,
    complexity: Complexity = "standard",
  ) => {
    const q = new URLSearchParams({ piece_type, complexity });
    return apiFetch<CostBreakdown>(
      `/api/v1/fabrics/${fabricId}/estimate?${q.toString()}`,
    );
  },

  createDesignSession: (
    photo: File,
    fields: {
      fabric_id: string;
      piece_type: PieceType;
      complexity: Complexity;
      brief: string;
      fit_note?: string;
      age_confirmed: boolean;
      anonymous_session_id?: string;
      // Optional style reference image — Pinterest screenshot, photo
      // of a similar piece, sketch. Passed to Gemini as a second
      // image and surfaced on the admin tailor brief.
      style_reference?: File;
    },
  ) => {
    const body = new FormData();
    body.set("photo", photo, photo.name);
    body.set("fabric_id", fields.fabric_id);
    body.set("piece_type", fields.piece_type);
    body.set("complexity", fields.complexity);
    body.set("brief", fields.brief);
    body.set("age_confirmed", String(fields.age_confirmed));
    if (fields.fit_note) body.set("fit_note", fields.fit_note);
    if (fields.anonymous_session_id) {
      body.set("anonymous_session_id", fields.anonymous_session_id);
    }
    if (fields.style_reference) {
      body.set(
        "style_reference",
        fields.style_reference,
        fields.style_reference.name,
      );
    }
    return apiUpload<DesignSessionCreateResponse>(
      "/api/v1/design-sessions",
      body,
    );
  },

  getDesignSession: (id: string) =>
    apiFetch<DesignSessionPublic>(`/api/v1/design-sessions/${id}`),
};
