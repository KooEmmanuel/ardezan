# Data Model - Modern AI-Native Clothing Store

> **Status:** Draft v0.1 - implementation planning
> **Source documents:** `SPECS.md`, `ARCHITECTURE.md`, `requirements-tracker.xlsx`
> **Primary datastore:** MongoDB Atlas
> **Owner:** Emmanuel Nyatefe
> **Date:** 2026-05-27

---

## 1. Purpose

This document defines the Phase 1 MongoDB data model for the AI-native clothing store. It is not final code, but it should be concrete enough to drive:

- FastAPI Pydantic schemas.
- MongoDB collection creation and indexes.
- API contracts.
- Admin CRUD screens.
- AI orchestration and retention logic.
- Milestone implementation tickets.

The model favors explicit collections over deeply nested "everything in one document" records where separate lifecycle, indexing, audit, or retention behavior is needed.

---

## 2. Global Conventions

### 2.1 IDs

- MongoDB `_id` is the canonical database identifier.
- Public API IDs should be stable string IDs, e.g. `prod_`, `var_`, `ord_`, `job_`.
- External provider IDs are stored in provider-specific fields, e.g. `stripe_payment_intent_id`.
- Never expose internal-only IDs in signed URLs or public object paths.

### 2.2 Timestamps

Every collection should include:

```text
created_at
updated_at
```

Documents with lifecycle or retention behavior also include:

```text
deleted_at
expires_at
archived_at
```

Use UTC timestamps everywhere.

### 2.3 Soft Delete

Use soft delete for business records that affect auditability:

- Products
- Variants
- Customers
- Admin users
- Orders

Use hard delete for ephemeral/private artifacts after retention windows:

- Anonymous uploaded photos
- Anonymous body profiles
- Anonymous generated images after expiration
- Expired inventory holds

### 2.4 Money

Store money as integer minor units:

```text
price_amount: 12999
currency: "USD"
```

Do not store floats for money.

### 2.5 Audit Metadata

Records modified by admin actions should carry light metadata:

```text
created_by_admin_id
updated_by_admin_id
```

The full immutable history lives in `audit_logs`.

---

## 3. Collection Overview

| Collection | Purpose | Phase 1 Required |
|---|---|---|
| `products` | Product-level catalog data and AI eligibility | Yes |
| `variants` | SKU, size/color, price, stock, availability | Yes |
| `size_charts` | House/brand size mapping and measurement ranges | Yes |
| `media_assets` | Product, upload, generated, and fallback image metadata | Yes |
| `customers` | Registered customer accounts and profile data | Yes |
| `admin_users` | Owner/admin identity and roles | Yes |
| `carts` | Registered carts and server cart snapshots | Yes |
| `inventory_holds` | Soft holds during checkout | Yes |
| `orders` | Order, payment, fulfillment, refund, return state | Yes |
| `payment_events` | Payment webhook idempotency and debugging | Yes |
| `try_on_sessions` | Saved try-on sessions and result cards | Yes |
| `ai_jobs` | AI orchestration state and progress event log | Yes |
| `generated_images` | Generated try-on image metadata and retention | Yes |
| `audit_logs` | Immutable admin/system action logs | Yes |
| `analytics_events` | Funnel, conversion, AI, and complaint events | Yes |
| `settings` | Store config, AI kill switch, spend ceilings | Yes |

---

## 4. Catalog Collections

### 4.1 `products`

Owns product-level merchandising and AI metadata.

```text
{
  _id,
  product_id: "prod_...",
  slug,
  title,
  description,
  category,
  subcategory,
  tags: [],
  status: "draft" | "published" | "archived",
  publication: {
    published_at,
    unpublished_at
  },
  pricing: {
    base_price_amount,
    compare_at_price_amount,
    currency
  },
  media_asset_ids: [],
  primary_media_asset_id,
  ai_friendly_media_asset_ids: [],
  product_details: {
    material,
    care_instructions,
    fit_notes,
    return_eligible: true,
    final_sale: false
  },
  size_chart_id,
  ai: {
    eligible: true,
    fabric_type,
    formality,
    fit_shape,
    season,
    color_palette: [],
    body_suitability: [],
    occasion_suitability: [],
    layering_compatibility: [],
    compatibility_tags: []
  },
  seo: {
    title,
    description,
    canonical_path
  },
  created_at,
  updated_at,
  deleted_at
}
```

Recommended indexes:

```text
unique(product_id)
unique(slug)
status + category
status + tags
ai.eligible + status
text(title, description, tags)
```

Notes:

- Product-level `status` controls customer visibility.
- AI recommender can only use `status=published` and `ai.eligible=true`.
- Product media is referenced through `media_assets`, not embedded binary data.

### 4.2 `variants`

Owns purchasable SKUs and stock.

```text
{
  _id,
  variant_id: "var_...",
  product_id,
  sku,
  title,
  size,
  color,
  color_hex,
  status: "active" | "inactive" | "archived",
  pricing: {
    price_amount,
    compare_at_price_amount,
    currency
  },
  inventory: {
    stock_on_hand,
    committed_units,
    low_stock_threshold,
    track_inventory: true
  },
  measurements: {
    garment_chest,
    garment_waist,
    garment_hip,
    garment_inseam,
    garment_length,
    unit: "in" | "cm"
  },
  created_at,
  updated_at,
  deleted_at
}
```

Recommended indexes:

```text
unique(variant_id)
unique(sku)
product_id + status
product_id + size + color
status + inventory.stock_on_hand
```

Inventory availability is calculated by the backend:

```text
available_for_sale = stock_on_hand - committed_units - active_holds
```

### 4.3 `size_charts`

Supports recommended-size mapping from AI measurements.

```text
{
  _id,
  size_chart_id: "size_...",
  name,
  scope: "house" | "brand" | "product",
  brand,
  product_id,
  unit: "in" | "cm",
  sizes: [
    {
      label: "S",
      body_measurements: {
        chest_min,
        chest_max,
        waist_min,
        waist_max,
        hip_min,
        hip_max,
        inseam_min,
        inseam_max,
        height_min,
        height_max
      },
      fit_notes
    }
  ],
  fallback_size_chart_id,
  created_at,
  updated_at
}
```

Recommended indexes:

```text
unique(size_chart_id)
scope + brand
product_id
```

Fallback rule:

- Product chart wins.
- Brand chart next.
- House chart last.
- If no chart exists, do not auto-select with confidence; show "Select size" with a recommendation disclaimer.

---

## 5. Media Collections

### 5.1 `media_assets`

Canonical metadata for stored images and files.

```text
{
  _id,
  media_asset_id: "media_...",
  owner_type: "product" | "customer" | "try_on_session" | "system",
  owner_id,
  purpose: "product_catalog" | "product_ai" | "customer_upload" | "generated_try_on" | "fallback_model",
  storage: {
    bucket,
    object_key,
    cdn_url,
    content_type,
    byte_size,
    width,
    height,
    checksum
  },
  access: {
    visibility: "public" | "private",
    signed_url_required: true
  },
  retention: {
    policy: "product_lifetime" | "anonymous_15_min" | "anonymous_24_hour" | "registered_until_deleted",
    expires_at,
    deleted_at
  },
  provenance: {
    ai_generated: false,
    provider,
    c2pa_embedded: false,
    digital_source_type
  },
  created_at,
  updated_at
}
```

Recommended indexes:

```text
unique(media_asset_id)
owner_type + owner_id
purpose + retention.expires_at
retention.expires_at
```

---

## 6. Identity Collections

### 6.1 `customers`

Registered customer accounts.

```text
{
  _id,
  customer_id: "cust_...",
  email,
  email_verified_at,
  name,
  phone,
  password_hash,
  auth_provider,
  addresses: [
    {
      address_id,
      label,
      name,
      line1,
      line2,
      city,
      region,
      postal_code,
      country,
      is_default_shipping,
      is_default_billing
    }
  ],
  saved_photo: {
    media_asset_id,
    opted_in: false,
    photo_uploaded_at,
    photo_consent_version
  },
  body_profile: {
    opted_in: false,
    source_try_on_session_id,
    measurements_estimate,
    fit_preference,
    style_preferences: [],
    updated_at
  },
  quotas: {
    try_on_weekly_limit,
    try_on_used_this_week,
    quota_window_starts_at
  },
  created_at,
  updated_at,
  deleted_at
}
```

Recommended indexes:

```text
unique(customer_id)
unique(email)
deleted_at
```

Privacy rule:

- Saved photo and body profile are stored only with explicit opt-in.
- Account deletion must remove or anonymize associated private media and profile data.

### 6.2 `admin_users`

Owner/admin accounts.

```text
{
  _id,
  admin_id: "admin_...",
  email,
  name,
  password_hash,
  role: "owner" | "operations" | "support",
  scopes: [],
  mfa: {
    enabled,
    method,
    enrolled_at
  },
  status: "active" | "disabled",
  last_login_at,
  created_at,
  updated_at,
  deleted_at
}
```

Recommended indexes:

```text
unique(admin_id)
unique(email)
role + status
```

---

## 7. Cart and Inventory Collections

### 7.1 `carts`

Server-side carts for registered users and optional server snapshots.

```text
{
  _id,
  cart_id: "cart_...",
  customer_id,
  status: "active" | "converted" | "abandoned",
  lines: [
    {
      line_id,
      product_id,
      variant_id,
      quantity,
      source: "catalog" | "try_on_full_look" | "try_on_single_item",
      try_on_session_id,
      try_on_card_id,
      price_snapshot: {
        price_amount,
        compare_at_price_amount,
        currency
      },
      added_at
    }
  ],
  last_validated_at,
  created_at,
  updated_at
}
```

Recommended indexes:

```text
unique(cart_id)
customer_id + status
updated_at
```

### 7.2 `inventory_holds`

Soft holds created when checkout starts.

```text
{
  _id,
  hold_id: "hold_...",
  cart_id,
  checkout_session_id,
  customer_id,
  guest_cart_id,
  variant_id,
  product_id,
  quantity,
  status: "active" | "committed" | "released" | "expired",
  expires_at,
  committed_at,
  released_at,
  created_at,
  updated_at
}
```

Recommended indexes:

```text
unique(hold_id)
checkout_session_id + status
variant_id + status
status + expires_at
```

Cleanup:

- Worker expires `active` holds where `expires_at < now`.

---

## 8. Order and Payment Collections

### 8.1 `orders`

```text
{
  _id,
  order_id: "ord_...",
  order_number,
  customer_id,
  guest_email,
  guest_management_token_hash,
  guest_claim_expires_at,
  status: "pending_payment" | "paid" | "packed" | "shipped" | "delivered" | "cancelled" | "refunded" | "partially_refunded" | "return_requested" | "returned" | "exchanged",
  lines: [
    {
      line_id,
      product_id,
      variant_id,
      sku,
      title_snapshot,
      size,
      color,
      quantity,
      unit_price_amount,
      compare_at_price_amount,
      currency,
      source: "catalog" | "try_on_full_look" | "try_on_single_item",
      try_on_session_id,
      try_on_card_id
    }
  ],
  totals: {
    subtotal_amount,
    discount_amount,
    tax_amount,
    shipping_amount,
    total_amount,
    currency
  },
  shipping_address,
  billing_address,
  payment: {
    provider: "stripe",
    stripe_payment_intent_id,
    stripe_checkout_session_id,
    payment_status,
    paid_at
  },
  fulfillment: {
    carrier,
    service_level,
    tracking_number,
    shipped_at,
    delivered_at
  },
  refunds: [
    {
      refund_id,
      provider_refund_id,
      amount,
      reason,
      status,
      created_at
    }
  ],
  support_notes: [],
  linked_order_ids: [],
  created_at,
  updated_at,
  cancelled_at
}
```

Recommended indexes:

```text
unique(order_id)
unique(order_number)
customer_id + created_at
guest_email + created_at
status + created_at
payment.stripe_payment_intent_id
fulfillment.tracking_number
```

### 8.2 `payment_events`

Webhook idempotency and debugging.

```text
{
  _id,
  payment_event_id: "payevt_...",
  provider: "stripe",
  provider_event_id,
  event_type,
  related_order_id,
  related_payment_intent_id,
  status: "received" | "processed" | "ignored" | "failed",
  raw_payload_hash,
  received_at,
  processed_at,
  failure_reason
}
```

Recommended indexes:

```text
unique(provider + provider_event_id)
related_order_id
status + received_at
```

---

## 9. AI Collections

### 9.1 `try_on_sessions`

Customer-visible try-on sessions.

```text
{
  _id,
  try_on_session_id: "try_...",
  customer_id,
  anonymous_session_id,
  source: "upload" | "saved_photo" | "product_seed" | "fallback_model",
  uploaded_media_asset_id,
  saved_photo_used: false,
  optional_inputs: {
    height,
    fit_preference,
    occasion,
    prompt
  },
  body_profile_snapshot: {
    measurements_estimate,
    body_shape,
    skin_undertone,
    current_style_notes,
    confidence
  },
  result_cards: [
    {
      card_id,
      outfit_name,
      generated_image_id,
      total_amount,
      currency,
      disclaimer_shown: true,
      ai_preview_label_shown: true,
      items: [
        {
          product_id,
          variant_id,
          recommended_size,
          selected_size,
          price_amount,
          compare_at_price_amount,
          rationale
        }
      ],
      status: "available" | "partially_unavailable" | "unavailable"
    }
  ],
  status: "active" | "completed" | "completed_partial" | "expired" | "deleted",
  expires_at,
  created_at,
  updated_at,
  deleted_at
}
```

Recommended indexes:

```text
unique(try_on_session_id)
customer_id + created_at
anonymous_session_id + expires_at
status + expires_at
```

### 9.2 `ai_jobs`

Backend orchestration record.

```text
{
  _id,
  job_id: "job_...",
  try_on_session_id,
  customer_id,
  anonymous_session_id,
  status: "queued" | "validating_upload" | "analyzing_photo" | "building_catalog_context" | "recommending_outfits" | "generating_images" | "completed" | "completed_partial" | "failed" | "cancelled" | "expired",
  current_stage,
  input: {
    uploaded_media_asset_id,
    optional_inputs,
    seeded_product_id
  },
  progress_events: [
    {
      event_id,
      type,
      stage,
      message,
      progress_percent,
      created_at
    }
  ],
  provider_calls: [
    {
      provider,
      model,
      purpose: "analyzer" | "recommender" | "designer",
      request_id,
      status,
      latency_ms,
      estimated_cost_amount,
      currency,
      error_code,
      error_message,
      created_at
    }
  ],
  cost: {
    estimated_total_amount,
    currency
  },
  failure: {
    reason,
    recoverable,
    failed_stage
  },
  created_at,
  updated_at,
  completed_at,
  expires_at
}
```

Recommended indexes:

```text
unique(job_id)
try_on_session_id
customer_id + created_at
anonymous_session_id + created_at
status + created_at
expires_at
```

### 9.3 `generated_images`

Generated image-specific metadata.

```text
{
  _id,
  generated_image_id: "genimg_...",
  try_on_session_id,
  job_id,
  media_asset_id,
  customer_id,
  anonymous_session_id,
  provider: "gemini",
  model: "gemini-2.5-flash-image",
  outfit_card_id,
  product_ids: [],
  variant_ids: [],
  disclosure: {
    ai_preview_label_shown: true,
    alt_text_marks_ai_generated: true,
    provenance_metadata_embedded: false
  },
  retention: {
    policy: "anonymous_24_hour" | "registered_until_deleted",
    expires_at,
    deleted_at
  },
  created_at,
  updated_at
}
```

Recommended indexes:

```text
unique(generated_image_id)
try_on_session_id
job_id
retention.expires_at
```

---

## 10. Audit, Analytics, and Settings

### 10.1 `audit_logs`

```text
{
  _id,
  audit_log_id: "audit_...",
  actor_type: "admin" | "system" | "customer",
  actor_id,
  action,
  target_type,
  target_id,
  before_summary,
  after_summary,
  ip_address,
  user_agent,
  created_at
}
```

Recommended indexes:

```text
actor_type + actor_id + created_at
target_type + target_id + created_at
action + created_at
```

Audit logs are append-only.

### 10.2 `analytics_events`

```text
{
  _id,
  analytics_event_id: "evt_...",
  event_type,
  customer_id,
  anonymous_session_id,
  order_id,
  product_id,
  try_on_session_id,
  metadata,
  created_at
}
```

Recommended indexes:

```text
event_type + created_at
customer_id + created_at
try_on_session_id
order_id
```

### 10.3 `settings`

Small collection for store-level operational configuration.

```text
{
  _id,
  key,
  value,
  updated_by_admin_id,
  updated_at
}
```

Suggested keys:

```text
ai.kill_switch
ai.daily_spend_ceiling
ai.anonymous_daily_limit
ai.registered_weekly_limit
checkout.soft_hold_minutes
store.launch_country
store.currency
privacy.consent_version
```

Recommended indexes:

```text
unique(key)
```

---

## 11. CatalogContext Contract

The Recommender receives a bounded catalog context, not raw MongoDB access.

```text
CatalogContext {
  version: "2026-05-27",
  body_profile_summary: {
    estimated_measurements,
    fit_preference,
    occasion,
    style_notes
  },
  candidates: [
    {
      product_id,
      title,
      category,
      price_amount,
      sale_price_amount,
      currency,
      fabric_type,
      formality,
      fit_shape,
      season,
      color_palette,
      compatibility_tags,
      image_references,
      variants: [
        {
          variant_id,
          size,
          color,
          available_for_sale,
          recommended_size_confidence
        }
      ]
    }
  ],
  constraints: {
    max_outfits: 10,
    max_items_per_outfit: 4,
    excluded_product_ids,
    seeded_product_id
  }
}
```

Rules:

- Only published, AI-eligible, in-stock candidates.
- No customer PII.
- No supplier private data.
- No admin notes.
- Candidate count should be capped to keep prompts bounded.

---

## 12. Retention Summary

| Data | Retention |
|---|---|
| Anonymous uploaded photo | Delete within session or 15 minutes, whichever comes first |
| Anonymous body profile | Same as anonymous uploaded photo |
| Anonymous generated images | Expire/delete within 24 hours |
| Anonymous local result cache | Browser-side only, 24 hours |
| Registered saved photo | Until user deletes photo/account or revokes consent |
| Registered generated images | Until session/account deletion |
| Payment events | Retain for operational/legal debugging |
| Audit logs | Append-only; retain long-term |
| Analytics events | Retain as aggregated/operational data, minimize PII |

---

## 13. Data Model Acceptance Criteria

This data model is ready for implementation when:

- Each Phase 1 requirement maps to a collection or explicit no-storage decision.
- Indexes exist for product browsing, search, stock checks, checkout holds, order lookup, AI job lookup, and retention cleanup.
- Privacy-sensitive records have retention metadata.
- Payment webhook idempotency has a unique provider event index.
- Inventory holds can be expired and committed safely.
- `CatalogContext` is approved before AI recommender implementation starts.
