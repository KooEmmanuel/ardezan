// Server-only fetch helpers for the admin UI. Forwards the admin_session
// cookie on every call so admin pages render with real auth.

import "server-only";

import { cookies } from "next/headers";

import type { OrderPublic } from "@/lib/types";

// Admin pages are SSR-only (this whole module is ``import "server-only"``),
// which means every fetch runs in Vercel's Node runtime — and Node's
// ``fetch`` requires an absolute URL. ``NEXT_PUBLIC_API_BASE_URL`` is
// empty in prod (so client code can use relative URLs that go through
// the Vercel rewrite), so we prefer ``BACKEND_PROXY_URL`` here to talk
// to Railway directly without an extra hop, and fall through to the
// public base URL or localhost in dev.
const API_BASE_URL =
  process.env.BACKEND_PROXY_URL?.replace(/\/$/, "") ||
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ||
  "http://localhost:8000";

export type AdminAuthResult<T> =
  | { kind: "ok"; data: T }
  | { kind: "unauth" }
  | { kind: "error"; status: number; message: string };

async function fetchAdmin<T>(
  path: string,
  init: RequestInit = {},
): Promise<AdminAuthResult<T>> {
  let cookieHeader = "";
  try {
    cookieHeader = (await cookies())
      .getAll()
      .map((c) => `${c.name}=${c.value}`)
      .join("; ");
  } catch {
    // Outside a request context; fine — server only invokes this from
    // server components which always have a request.
  }
  try {
    const r = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        ...(init.headers ?? {}),
        ...(cookieHeader ? { cookie: cookieHeader } : {}),
      },
      cache: "no-store",
    });
    if (r.status === 401 || r.status === 403) return { kind: "unauth" };
    if (!r.ok) {
      let msg = `${r.status}`;
      try {
        const body = (await r.json()) as { error?: { message?: string } };
        msg = body.error?.message ?? msg;
      } catch {
        // ignore
      }
      return { kind: "error", status: r.status, message: msg };
    }
    return { kind: "ok", data: (await r.json()) as T };
  } catch (err) {
    return {
      kind: "error",
      status: 0,
      message: err instanceof Error ? err.message : "network error",
    };
  }
}

export type AdminMe = {
  admin_id: string;
  email: string;
  name: string;
  role: string;
  scopes: string[];
};

export type AdminProductPublic = {
  product_id: string;
  slug: string;
  title: string;
  category: string;
  status: "draft" | "published" | "archived";
  pricing: { base_price_amount: number; currency: string };
  primary_media_asset_id: string | null;
  created_at: string;
  updated_at: string;
};

export type AdminVariantDetail = {
  variant_id: string;
  product_id: string;
  sku: string;
  title: string | null;
  size: string;
  color: string;
  color_hex: string | null;
  status: "active" | "archived";
  pricing: {
    price_amount: number;
    compare_at_price_amount: number | null;
    currency: string;
  };
  inventory: {
    stock_on_hand: number;
    held_units: number;
    committed_units: number;
    low_stock_threshold: number;
    track_inventory: boolean;
  };
  measurements: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
};

export type AdminProductDetailFull = {
  product_id: string;
  slug: string;
  title: string;
  description: string | null;
  category: string;
  subcategory: string | null;
  gender: "women" | "men" | "unisex";
  tags: string[];
  status: "draft" | "published" | "archived";
  pricing: {
    base_price_amount: number;
    compare_at_price_amount: number | null;
    currency: string;
  };
  media_asset_ids: string[];
  primary_media_asset_id: string | null;
  ai_friendly_media_asset_ids: string[];
  product_details: Record<string, unknown>;
  size_chart_id: string | null;
  ai: Record<string, unknown>;
  seo: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
  primary_image_url: string | null;
  media_urls: string[];
  variants: AdminVariantDetail[];
};

export type AdminProductListItem = {
  product_id: string;
  slug: string;
  title: string;
  category: string;
  subcategory: string | null;
  gender: "women" | "men" | "unisex";
  tags: string[];
  status: "draft" | "published" | "archived";
  pricing: {
    base_price_amount: number;
    compare_at_price_amount: number | null;
    currency: string;
  };
  primary_image_url: string | null;
  variant_count: number;
  stock_on_hand_total: number;
  low_stock_variant_count: number;
  out_of_stock_variant_count: number;
  price_min_amount: number | null;
  price_max_amount: number | null;
  updated_at: string;
};

export type AdminProductListResponse = {
  items: AdminProductListItem[];
  total: number;
  next_cursor: string | null;
};

export type AdminCustomerListItem = {
  customer_id: string;
  email: string;
  name: string;
  email_verified: boolean;
  accepts_marketing: boolean;
  has_saved_photo: boolean;
  body_profile_opted_in: boolean;
  addresses_count: number;
  orders_count: number;
  lifetime_spend_amount: number;
  last_order_at: string | null;
  created_at: string;
  last_login_at: string | null;
};

export type AdminCustomersListResponse = {
  items: AdminCustomerListItem[];
  total: number;
  limit: number;
  offset: number;
  currency: string;
};

export type AdminCustomerDetail = {
  customer_id: string;
  email: string;
  name: string;
  email_verified_at: string | null;
  accepts_marketing: boolean;
  has_saved_photo: boolean;
  body_profile_opted_in: boolean;
  addresses: Array<{
    line1?: string;
    line2?: string;
    city?: string;
    region?: string;
    postal_code?: string;
    country?: string;
    is_default?: boolean;
    [k: string]: unknown;
  }>;
  created_at: string;
  last_login_at: string | null;
  orders_count: number;
  lifetime_spend_amount: number;
  last_order_at: string | null;
  currency: string;
};

export type AdminCustomerOrderRow = {
  order_id: string;
  order_number: string;
  status: string;
  created_at: string;
  total_amount: number;
  currency: string;
  line_count: number;
};

export type AdminCustomerOrdersResponse = {
  items: AdminCustomerOrderRow[];
  total: number;
};

export type AdminAIJobListItem = {
  job_id: string;
  try_on_session_id: string | null;
  customer_id: string | null;
  anonymous_session_id: string | null;
  status: string;
  current_stage: string | null;
  estimated_cost_amount: number | null;
  failure_reason: string | null;
  created_at: string;
  completed_at: string | null;
};

export type AdminAIJobsResponse = {
  items: AdminAIJobListItem[];
  total: number;
  limit: number;
  offset: number;
};

export type AdminAIJobDetail = {
  job_id: string;
  try_on_session_id: string | null;
  customer_id: string | null;
  anonymous_session_id: string | null;
  status: string;
  current_stage: string | null;
  input: Record<string, unknown>;
  progress_events: Array<{
    type?: string;
    stage?: string;
    message?: string;
    progress_percent?: number;
    payload?: Record<string, unknown>;
    created_at?: string;
    [k: string]: unknown;
  }>;
  provider_calls: Array<{
    provider?: string;
    model?: string;
    operation?: string;
    duration_ms?: number;
    cost_amount?: number;
    success?: boolean;
    error?: string | null;
    created_at?: string;
    [k: string]: unknown;
  }>;
  cost: {
    estimated_amount?: number;
    actual_amount?: number;
    currency?: string;
    [k: string]: unknown;
  };
  failure: {
    reason?: string;
    failed_stage?: string;
    technical_detail?: string;
    [k: string]: unknown;
  } | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  expires_at: string | null;
};

export type AdminAnalyticsOverview = {
  revenue_total_amount: number;
  revenue_currency: string;
  orders_total: number;
  orders_today: number;
  orders_last_7_days: number;
  top_products: Array<{
    product_id: string;
    title: string;
    quantity_sold: number;
    revenue_amount: number;
  }>;
  low_stock_variants: Array<{
    variant_id: string;
    product_id: string;
    sku: string;
    size: string;
    color: string;
    available_for_sale: number;
    low_stock_threshold: number;
  }>;
};

export type AdminDashboardMetrics = {
  currency: string;
  revenue_today_amount: number;
  revenue_week_amount: number;
  orders_today_count: number;
  orders_week_count: number;
  orders_pending_fulfillment: number;
  orders_pending_payment: number;
  low_stock_variant_count: number;
  out_of_stock_variant_count: number;
  active_products_count: number;
  draft_products_count: number;
  refunds_pending_count: number;
  revenue_sparkline: number[];
};

export type AdminOrderListItem = {
  order_id: string;
  order_number: string;
  status: string;
  customer_id: string | null;
  guest_email: string | null;
  totals: { total_amount: number; currency: string };
  // The list endpoint returns the full OrderAdminPublic doc — we read
  // ``lines[].kind`` just to flag custom-design orders in the table.
  lines: { kind?: "catalog" | "custom_design" }[];
  created_at: string;
};

export type AdminOrdersListResponse = {
  items: AdminOrderListItem[];
  total: number;
  limit: number;
  offset: number;
};

export type AdminOrderTryOnItem = {
  product_id: string;
  variant_id: string;
  product_title: string | null;
  category: string | null;
  color: string | null;
  recommended_size: string | null;
  selected_size: string | null;
  price_amount: number | null;
};

export type AdminOrderTryOnLook = {
  line_id: string;
  sku: string;
  title_snapshot: string;
  size: string | null;
  color: string | null;
  quantity: number;
  try_on_session_id: string;
  try_on_card_id: string | null;
  outfit_name: string | null;
  rationale: string | null;
  generated_look_image_url: string | null;
  source_photo_url: string | null;
  images_available: boolean;
  session_source: string | null;
  session_status: string | null;
  session_created_at: string | null;
  items: AdminOrderTryOnItem[];
};

export type AdminOrderTryOnResponse = {
  order_id: string;
  order_number: string;
  looks: AdminOrderTryOnLook[];
};

export type AdminAISettings = {
  kill_switch_enabled: boolean;
  daily_spend_ceiling_amount: number;
  anonymous_daily_limit: number;
  registered_weekly_limit: number;
  currency: string;
};

export type AdminAIAnalytics = {
  today_spend_amount: number;
  today_spend_ceiling_amount: number;
  daily_spend_pct: number;
  kill_switch_enabled: boolean;
  try_on_starts_7d: number;
  try_on_completed_7d: number;
  try_on_partial_7d: number;
  try_on_failed_7d: number;
  failed_jobs_recent: Array<{
    job_id: string;
    status: string;
    failed_stage: string | null;
    failure_reason: string | null;
    customer_or_session_id: string | null;
    created_at: string;
  }>;
  currency: string;
};

export type AdminAuditLogItem = {
  audit_log_id: string;
  actor_id: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  created_at: string;
};

export type AdminAuditLogsResponse = {
  items: AdminAuditLogItem[];
  total: number;
  limit: number;
  offset: number;
};

export type InventoryVariantProduct = {
  title: string;
  slug: string;
  category: string;
  status: string;
  primary_image_url: string | null;
};

export type InventoryVariant = {
  variant_id: string;
  product_id: string;
  sku: string;
  title: string | null;
  size: string;
  color: string;
  color_hex: string | null;
  status: string;
  pricing: {
    price_amount: number;
    compare_at_price_amount: number | null;
    currency: string;
  };
  inventory: {
    stock_on_hand: number;
    held_units: number;
    committed_units: number;
    low_stock_threshold: number;
    track_inventory: boolean;
  };
  stock_on_hand: number;
  held_units: number;
  low_stock_threshold: number;
  track_inventory: boolean;
  stock_state: "healthy" | "low" | "oos" | "untracked";
  product: InventoryVariantProduct | null;
  updated_at: string;
};

export type InventoryVariantsResponse = {
  items: InventoryVariant[];
  total: number;
  limit: number;
  offset: number;
};

export type InventoryMovement = {
  movement_id: string;
  variant_id: string;
  product_id: string | null;
  delta: number;
  quantity_after: number;
  reason: string;
  source_type: string;
  source_id: string | null;
  actor_id: string | null;
  note: string | null;
  created_at: string;
};

export type InventoryMovementsResponse = {
  items: InventoryMovement[];
  total: number;
  limit: number;
  offset: number;
};

export const adminApi = {
  me: () => fetchAdmin<AdminMe>("/api/v1/admin/me"),

  listProducts: (params?: {
    status?: string;
    category?: string;
    q?: string;
    limit?: number;
    cursor?: string;
  }) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status", params.status);
    if (params?.category) qs.set("category", params.category);
    if (params?.q) qs.set("q", params.q);
    qs.set("limit", String(params?.limit ?? 50));
    if (params?.cursor) qs.set("cursor", params.cursor);
    return fetchAdmin<AdminProductListResponse>(`/api/v1/admin/products?${qs.toString()}`);
  },

  getDashboardMetrics: () =>
    fetchAdmin<AdminDashboardMetrics>("/api/v1/admin/dashboard"),

  listCustomers: (params?: {
    q?: string;
    verified?: "yes" | "no";
    marketing?: "yes" | "no";
    sort?: "recent" | "spend" | "orders";
    limit?: number;
    offset?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.q) qs.set("q", params.q);
    if (params?.verified) qs.set("verified", params.verified);
    if (params?.marketing) qs.set("marketing", params.marketing);
    if (params?.sort) qs.set("sort", params.sort);
    qs.set("limit", String(params?.limit ?? 50));
    if (params?.offset) qs.set("offset", String(params.offset));
    return fetchAdmin<AdminCustomersListResponse>(
      `/api/v1/admin/customers?${qs.toString()}`,
    );
  },

  getCustomer: (id: string) =>
    fetchAdmin<AdminCustomerDetail>(`/api/v1/admin/customers/${encodeURIComponent(id)}`),

  listCustomerOrders: (id: string, limit = 20) =>
    fetchAdmin<AdminCustomerOrdersResponse>(
      `/api/v1/admin/customers/${encodeURIComponent(id)}/orders?limit=${limit}`,
    ),

  getProduct: (id: string) =>
    fetchAdmin<AdminProductDetailFull>(`/api/v1/admin/products/${id}`),

  listOrders: (params?: {
    status?: string;
    limit?: number;
    offset?: number;
    has_custom_design?: boolean;
  }) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status", params.status);
    qs.set("limit", String(params?.limit ?? 50));
    if (params?.offset) qs.set("offset", String(params.offset));
    if (params?.has_custom_design !== undefined) {
      qs.set("has_custom_design", String(params.has_custom_design));
    }
    return fetchAdmin<AdminOrdersListResponse>(`/api/v1/admin/orders?${qs.toString()}`);
  },

  getOrder: (id: string) => fetchAdmin<OrderPublic>(`/api/v1/admin/orders/${id}`),

  getOrderTryOns: (id: string) =>
    fetchAdmin<AdminOrderTryOnResponse>(
      `/api/v1/admin/orders/${encodeURIComponent(id)}/try-ons`,
    ),

  getOrderCustomDesigns: (id: string) =>
    fetchAdmin<{
      items: {
        line_id: string;
        design_session_id: string | null;
        status: string;
        title_snapshot: string | null;
        fabric?: {
          fabric_id: string;
          name: string;
          color_family: string;
          cost_per_yard_amount: number;
          weight: string;
          finish: string | null;
        };
        piece_type?: string;
        complexity?: string;
        brief?: string;
        fit_note?: string | null;
        estimate?: {
          yardage: number;
          material_amount: number;
          tailoring_amount: number;
          total_amount: number;
          currency: string;
        };
        image_url: string | null;
        reference_image_url?: string | null;
        unit_price_amount?: number;
        created_at?: string;
      }[];
    }>(
      `/api/v1/admin/orders/${encodeURIComponent(id)}/custom-designs`,
    ),

  getAISettings: () =>
    fetchAdmin<AdminAISettings>("/api/v1/admin/settings/ai"),

  getAIAnalytics: () =>
    fetchAdmin<AdminAIAnalytics>("/api/v1/admin/analytics/ai"),

  getAnalyticsOverview: () =>
    fetchAdmin<AdminAnalyticsOverview>("/api/v1/admin/analytics/overview"),

  listAIJobs: (params?: {
    status?: string;
    customer_id?: string;
    anonymous_session_id?: string;
    limit?: number;
    offset?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status", params.status);
    if (params?.customer_id) qs.set("customer_id", params.customer_id);
    if (params?.anonymous_session_id)
      qs.set("anonymous_session_id", params.anonymous_session_id);
    qs.set("limit", String(params?.limit ?? 50));
    if (params?.offset) qs.set("offset", String(params.offset));
    return fetchAdmin<AdminAIJobsResponse>(`/api/v1/admin/ai/jobs?${qs.toString()}`);
  },

  getAIJob: (jobId: string) =>
    fetchAdmin<AdminAIJobDetail>(`/api/v1/admin/ai/jobs/${encodeURIComponent(jobId)}`),

  listAuditLogs: (params?: { limit?: number; offset?: number; action?: string }) => {
    const qs = new URLSearchParams();
    qs.set("limit", String(params?.limit ?? 50));
    if (params?.offset) qs.set("offset", String(params.offset));
    if (params?.action) qs.set("action", params.action);
    return fetchAdmin<AdminAuditLogsResponse>(`/api/v1/admin/audit-logs?${qs.toString()}`);
  },

  listInventoryVariants: (params?: {
    health?: "all" | "low" | "oos" | "healthy" | "untracked";
    q?: string;
    product_id?: string;
    limit?: number;
    offset?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.health) qs.set("health", params.health);
    if (params?.q) qs.set("q", params.q);
    if (params?.product_id) qs.set("product_id", params.product_id);
    qs.set("limit", String(params?.limit ?? 200));
    if (params?.offset) qs.set("offset", String(params.offset));
    return fetchAdmin<InventoryVariantsResponse>(
      `/api/v1/admin/inventory/variants?${qs.toString()}`,
    );
  },

  listInventoryMovements: (params?: {
    variant_id?: string;
    product_id?: string;
    limit?: number;
    offset?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.variant_id) qs.set("variant_id", params.variant_id);
    if (params?.product_id) qs.set("product_id", params.product_id);
    qs.set("limit", String(params?.limit ?? 100));
    if (params?.offset) qs.set("offset", String(params.offset));
    return fetchAdmin<InventoryMovementsResponse>(
      `/api/v1/admin/inventory/movements?${qs.toString()}`,
    );
  },
};
