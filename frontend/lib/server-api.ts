// Server-only fetch helpers. These run during Next.js's server render of
// React Server Components, so the initial HTML the browser receives already
// contains real product data and image URLs — no client-side fetch waterfall.

import "server-only";

import type {
  CategoryListResponse,
  OrderPublic,
  ProductDetail,
  ProductListResponse,
  SiteMediaResponse,
  TryOnSessionDetail,
} from "@/lib/types";

// Server-side fetches go straight to Railway, NOT through the
// /api/* Vercel rewrite. Two reasons:
//   1. Going through the rewrite from inside a Vercel function would
//      route Vercel → Vercel → Railway — needless extra hop.
//   2. We pick the host from ``BACKEND_PROXY_URL`` (server-only env,
//      not baked into the client bundle), so the Railway hostname
//      stays off the public JS.
// Falls back to the public base URL, then to localhost in dev.
const API_BASE_URL =
  process.env.BACKEND_PROXY_URL?.replace(/\/$/, "") ||
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ||
  "http://localhost:8000";

// Next dedupes identical fetches automatically within a single render. The
// ``revalidate`` window lets the same server render cache stay warm for the
// next ~60 seconds across all visitors before being regenerated in the
// background. Good fit for a catalog that doesn't change minute-to-minute.
const REVALIDATE_SECONDS = 60;

async function serverFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    next: { revalidate: REVALIDATE_SECONDS },
  });
  if (!response.ok) {
    throw new Error(
      `Server fetch failed: ${response.status} ${path.slice(0, 80)}`,
    );
  }
  return (await response.json()) as T;
}

export const serverApi = {
  listProducts: (params?: { category?: string; q?: string; limit?: number }) => {
    const search = new URLSearchParams();
    if (params?.category) search.set("category", params.category);
    if (params?.q) search.set("q", params.q);
    if (params?.limit) search.set("limit", String(params.limit));
    const path = params?.q
      ? `/api/v1/catalog/search?${search.toString()}`
      : `/api/v1/catalog/products?${search.toString()}`;
    return serverFetch<ProductListResponse>(path);
  },

  listCategories: () =>
    serverFetch<CategoryListResponse>("/api/v1/catalog/categories"),

  getProduct: (slug: string) =>
    serverFetch<ProductDetail>(`/api/v1/catalog/products/${slug}`),

  getSiteMedia: () => serverFetch<SiteMediaResponse>("/api/v1/site/media"),

  getOrder: async (orderId: string, opts?: { token?: string; cookie?: string }) => {
    const params = new URLSearchParams();
    if (opts?.token) params.set("token", opts.token);
    const headers: Record<string, string> = {};
    if (opts?.cookie) headers.cookie = opts.cookie;
    const r = await fetch(
      `${API_BASE_URL}/api/v1/orders/${encodeURIComponent(orderId)}?${params.toString()}`,
      { headers, cache: "no-store" },
    );
    if (!r.ok) {
      // Annotate the error so callers can distinguish "needs auth" (the
      // confirmation page should show a friendly hint instead of 404)
      // from a real "no such order".
      const err = new Error(`order fetch failed: ${r.status}`) as Error & {
        status?: number;
      };
      err.status = r.status;
      throw err;
    }
    return (await r.json()) as OrderPublic;
  },

  getTryOnSession: async (sessionId: string, cookie: string) => {
    const headers: Record<string, string> = {};
    if (cookie) headers.cookie = cookie;
    const r = await fetch(
      `${API_BASE_URL}/api/v1/try-on/sessions/${encodeURIComponent(sessionId)}`,
      { headers, cache: "no-store" },
    );
    if (!r.ok) throw new Error(`session fetch failed: ${r.status}`);
    return (await r.json()) as TryOnSessionDetail;
  },

  listMyOrders: async (cookie: string, params?: { limit?: number; offset?: number }) => {
    const qs = new URLSearchParams();
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.offset) qs.set("offset", String(params.offset));
    const r = await fetch(
      `${API_BASE_URL}/api/v1/orders?${qs.toString()}`,
      { headers: cookie ? { cookie } : undefined, cache: "no-store" },
    );
    if (r.status === 401) return null;
    if (!r.ok) throw new Error(`orders list failed: ${r.status}`);
    return (await r.json()) as {
      items: OrderPublic[];
      total: number;
      limit: number;
      offset: number;
    };
  },

  getDesignSession: async (designSessionId: string) => {
    // Public read — guest customers viewing their confirmation page need
    // it too, so this isn't behind a cookie.
    const r = await fetch(
      `${API_BASE_URL}/api/v1/design-sessions/${encodeURIComponent(designSessionId)}`,
      { cache: "no-store" },
    );
    if (!r.ok) return null;
    return (await r.json()) as { image_url: string | null };
  },

  listMyDesigns: async (cookie: string, params?: { limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.limit) qs.set("limit", String(params.limit));
    const r = await fetch(
      `${API_BASE_URL}/api/v1/account/designs?${qs.toString()}`,
      { headers: cookie ? { cookie } : undefined, cache: "no-store" },
    );
    if (r.status === 401) return null;
    if (!r.ok) throw new Error(`designs list failed: ${r.status}`);
    return (await r.json()) as {
      items: {
        design_session_id: string;
        status: "draft" | "ready" | "failed";
        title: string;
        fabric_name: string;
        piece_type: string;
        image_url: string | null;
        total_amount: number;
        currency: string;
        created_at: string;
      }[];
      total: number;
      limit: number;
      offset: number;
    };
  },

  getMe: async (cookie: string) => {
    const r = await fetch(`${API_BASE_URL}/api/v1/account/me`, {
      headers: cookie ? { cookie } : undefined,
      cache: "no-store",
    });
    if (r.status === 401) return null;
    if (!r.ok) throw new Error(`me failed: ${r.status}`);
    return (await r.json()) as {
      customer_id: string;
      email: string;
      name: string | null;
      email_verified: boolean;
    };
  },
};
