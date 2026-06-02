// ── Site media (branded UI images) ────────────────────────────────
export type HeroLookSlot =
  | "hero_look_01"
  | "hero_look_02"
  | "hero_look_03"
  | "hero_look_04"
  | "hero_look_05"
  | "hero_look_06";

export type SiteMediaSlot =
  | HeroLookSlot
  | "hero_mobile"
  | "category_women"
  | "category_men"
  | "category_bespoke"
  | "category_new"
  | "category_accessories"
  | "editorial_no_01";

export const HERO_LOOK_SLOTS: HeroLookSlot[] = [
  "hero_look_01",
  "hero_look_02",
  "hero_look_03",
  "hero_look_04",
  "hero_look_05",
  "hero_look_06",
];

export type SiteMediaResponse = {
  slots: Record<SiteMediaSlot, string | null>;
};

export type Money = {
  currency: string;
  base_price_amount?: number;
  price_amount?: number;
  compare_at_price_amount?: number | null;
};

export type ProductListItem = {
  product_id: string;
  slug: string;
  title: string;
  category: string;
  pricing: Money;
  primary_media_asset_id: string | null;
  primary_image_url: string | null;
  try_on_eligible: boolean;
};

export type ProductListResponse = {
  items: ProductListItem[];
  next_cursor: string | null;
};

export type CategoryListResponse = {
  categories: string[];
};

export type VariantPublic = {
  variant_id: string;
  sku: string;
  size: string;
  color: string;
  color_hex: string | null;
  pricing: Money;
  available_for_sale: number;
};

export type ProductDetail = ProductListItem & {
  description: string | null;
  subcategory: string | null;
  tags: string[];
  media_asset_ids: string[];
  media_urls: string[];
  ai_friendly_media_asset_ids: string[];
  product_details: {
    material?: string | null;
    care_instructions?: string | null;
    fit_notes?: string | null;
    return_eligible?: boolean;
    final_sale?: boolean;
  };
  variants: VariantPublic[];
  size_chart_id: string | null;
};

export type CartLineKind = "catalog" | "custom_design";

export type CartLineInput = {
  line_id: string;
  kind?: CartLineKind;
  // Required for kind=catalog; absent for kind=custom_design.
  product_id?: string | null;
  variant_id?: string | null;
  // Required for kind=custom_design; absent on catalog lines.
  design_session_id?: string | null;
  quantity: number;
  source: "catalog" | "try_on_full_look" | "try_on_single_item" | "design_me";
  try_on_session_id?: string | null;
  try_on_card_id?: string | null;
  expected_unit_price_amount?: number | null;
};

export type CartLineState = CartLineInput & {
  kind: CartLineKind;
  product_title: string | null;
  variant_title: string | null;
  size: string | null;
  color: string | null;
  color_hex: string | null;
  primary_media_asset_id: string | null;
  primary_image_url: string | null;
  status: "ok" | "price_changed" | "low_stock" | "out_of_stock" | "removed";
  pricing: Money | null;
  line_subtotal_amount: number;
  available_quantity: number;
  message: string | null;
};

export type RevalidateResponse = {
  lines: CartLineState[];
  totals: {
    subtotal_amount: number;
    item_count: number;
    currency: string;
  };
  any_changes: boolean;
  blocks_checkout: boolean;
};

export type Address = {
  name: string;
  line1: string;
  line2?: string | null;
  city: string;
  region?: string | null;
  postal_code: string;
  country: string;
  phone?: string | null;
};

// ── Customers / auth (M5) ─────────────────────────────────────────
export type CustomerPublic = {
  customer_id: string;
  email: string;
  name: string;
  email_verified_at: string | null;
  addresses: Address[];
  has_saved_photo: boolean;
  body_profile_opted_in: boolean;
  last_login_at: string | null;
  created_at: string;
};

export type CustomerLoginResponse = {
  customer: CustomerPublic;
  expires_at: string;
};

export type SavedPhotoStatus = {
  opted_in: boolean;
  has_photo: boolean;
  photo_url: string | null;
  photo_uploaded_at: string | null;
  photo_consent_version: string | null;
};

export type BodyProfileStatus = {
  opted_in: boolean;
  source_try_on_session_id: string | null;
  measurements_estimate: Record<string, unknown> | null;
  fit_preference: string | null;
  updated_at: string | null;
};

// ── Try-on (M4) ────────────────────────────────────────────────────
export type JobCreatedResponse = {
  try_on_session_id: string;
  job_id: string;
  sse_url: string;
};

export type JobPublic = {
  job_id: string;
  try_on_session_id: string | null;
  status:
    | "queued"
    | "validating_upload"
    | "analyzing_photo"
    | "building_catalog_context"
    | "recommending_outfits"
    | "generating_images"
    | "completed"
    | "completed_partial"
    | "failed"
    | "cancelled"
    | "expired";
  current_stage: string | null;
  progress_percent: number;
  failure_reason: string | null;
  estimated_cost_amount: number | null;
  created_at: string;
  completed_at: string | null;
};

export type ResultCardItem = {
  product_id: string;
  variant_id: string;
  product_title?: string | null;
  category?: string | null;
  color?: string | null;
  color_hex?: string | null;
  recommended_size?: string | null;
  selected_size?: string | null;
  price_amount: number;
  compare_at_price_amount?: number | null;
  rationale?: string | null;
};

export type ResultCard = {
  card_id: string;
  outfit_name: string | null;
  rationale: string | null;
  generated_image_id: string | null;
  image_url: string | null;
  total_amount: number;
  currency: string;
  status: "available" | "partially_unavailable" | "unavailable";
  items: ResultCardItem[];
};

export type TryOnSessionDetail = {
  try_on_session_id: string;
  source: "upload" | "product_seed";
  status: string;
  optional_inputs: Record<string, unknown>;
  body_profile_snapshot: Record<string, unknown> | null;
  result_cards: ResultCard[];
  created_at: string;
  updated_at: string;
};

export type TryOnFormInput = {
  height?: string;
  fit_preference?: "slim" | "regular" | "relaxed" | "oversized";
  occasion?: string;
  prompt?: string;
  seeded_product_id?: string;
  age_confirmed: boolean;
  anonymous_session_id?: string;
};

export type TryOnEvent = {
  type: string;
  stage: string | null;
  message: string | null;
  progress_percent: number | null;
  payload: Record<string, unknown>;
  created_at?: string;
};

export type OrderLine = {
  line_id: string;
  kind?: CartLineKind;
  product_id: string | null;
  variant_id: string | null;
  design_session_id?: string | null;
  title_snapshot: string;
  size: string | null;
  color: string | null;
  quantity: number;
  unit_price_amount: number;
  line_total_amount: number;
};

export type OrderRefund = {
  refund_id: string;
  provider_refund_id: string;
  amount: number;
  reason: string | null;
  status: string;
  created_at: string;
};

export type OrderReturnRequest = {
  reason: string;
  line_ids: string[];
  requested_at: string;
  status: "pending" | "received" | "rejected";
  note: string | null;
  received_at: string | null;
  refund_id: string | null;
};

export type OrderPublic = {
  order_id: string;
  order_number: string;
  status: string;
  customer_id: string | null;
  guest_email: string | null;
  lines: OrderLine[];
  totals: {
    subtotal_amount: number;
    discount_amount: number;
    tax_amount: number;
    shipping_amount: number;
    total_amount: number;
    currency: string;
  };
  shipping_address: Address;
  payment: {
    stripe_payment_intent_id: string | null;
    payment_status: string;
    paid_at?: string | null;
  };
  fulfillment: {
    status: string;
    carrier: string | null;
    service_level: string | null;
    tracking_number: string | null;
    tracking_url: string | null;
    shipped_at: string | null;
    delivered_at: string | null;
  };
  refunds?: OrderRefund[];
  return_request?: OrderReturnRequest | null;
  created_at: string;
};

export type CheckoutSessionPublic = {
  checkout_session_id: string;
  status: "open" | "paid" | "expired" | "cancelled" | "failed";
  totals: {
    subtotal_amount: number;
    discount_amount: number;
    tax_amount: number;
    shipping_amount: number;
    total_amount: number;
    currency: string;
  };
  stripe_client_secret: string | null;
  stripe_publishable_key: string | null;
  expires_at: string;
  created_at: string;
};

// ── Design Me ────────────────────────────────────────────────────────
export type PieceType =
  | "shirt"
  | "blouse"
  | "trouser"
  | "skirt"
  | "dress"
  | "jacket"
  | "blazer"
  | "coat"
  | "overshirt"
  | "tee"
  | "caftan"
  | "agbada"
  | "dashiki"
  | "kaba";

export type Complexity = "simple" | "standard" | "intricate";

export type FabricSwatch = {
  gradient: string | null;
  image_url: string | null;
};

export type FabricPublic = {
  fabric_id: string;
  name: string;
  description: string;
  color_family: string;
  cost_per_yard_amount: number;
  currency: string;
  suitable_for: PieceType[];
  swatch: FabricSwatch;
  weight: "light" | "medium" | "heavy";
  finish: string | null;
};

export type CostBreakdown = {
  fabric_id: string;
  piece_type: PieceType;
  complexity: Complexity;
  yardage: number;
  material_amount: number;
  tailoring_amount: number;
  total_amount: number;
  currency: string;
  estimate_note: string;
};

export type DesignSessionPublic = {
  design_session_id: string;
  status: "draft" | "ready" | "failed";
  fabric: {
    fabric_id: string;
    name: string;
    color_family: string;
    cost_per_yard_amount: number;
    currency: string;
    weight: string;
    finish: string | null;
  };
  piece_type: PieceType;
  complexity: Complexity;
  brief: string;
  fit_note: string | null;
  estimate: CostBreakdown;
  image_url: string | null;
  failure_reason: string | null;
  created_at: string;
  updated_at: string;
};

export type DesignSessionCreateResponse = {
  design_session_id: string;
  status: "draft" | "ready" | "failed";
  estimate: CostBreakdown;
  image_url: string | null;
  failure_reason: string | null;
};
