# API Contract - Modern AI-Native Clothing Store

> **Status:** Draft v0.1 - implementation planning
> **Runtime:** Python FastAPI
> **Clients:** Next.js storefront/admin, future mobile app
> **Source documents:** `SPECS.md`, `ARCHITECTURE.md`, `DATA_MODEL.md`
> **Date:** 2026-05-27

---

## 1. Purpose

This document defines the Phase 1 API boundaries for the FastAPI backend. It is a planning contract, not final OpenAPI output. The goal is to make frontend, backend, AI, checkout, webhook, and admin work plan from the same interface assumptions.

---

## 2. API Principles

- All business state changes go through FastAPI.
- Next.js owns rendering and UI flow; FastAPI owns data and rules.
- Browser clients never talk directly to MongoDB, Stripe, Gemini, or private object storage.
- Every state-changing endpoint supports idempotency where retries are realistic.
- Errors use one consistent shape.
- Admin endpoints require admin auth and write audit logs for critical actions.
- AI jobs are asynchronous; progress streams through SSE.
- Payment and shipping webhooks are verified, stored, and idempotent.

---

## 3. Base URLs and Versioning

```text
/api/v1
```

Suggested groups:

```text
/api/v1/auth
/api/v1/catalog
/api/v1/cart
/api/v1/checkout
/api/v1/orders
/api/v1/try-on
/api/v1/account
/api/v1/admin
/api/v1/webhooks
/api/v1/media
```

API versioning starts at `v1`. Breaking changes require a new version or explicit migration plan.

---

## 4. Common Request Rules

### 4.1 Auth

Customer session:

```text
Cookie: customer_session=...
```

Admin session:

```text
Cookie: admin_session=...
```

Guest flows:

```text
Authorization: Bearer <signed_guest_token>
```

### 4.2 Idempotency

For state-changing commerce operations:

```text
Idempotency-Key: <client-generated-key>
```

Required for:

- Checkout creation.
- Add full look to cart.
- Payment/order webhook processing.
- Refund requests.
- Order cancellation.
- Address edits.

### 4.3 Pagination

List endpoints use cursor pagination:

```text
?limit=24&cursor=...
```

Response:

```json
{
  "items": [],
  "next_cursor": null
}
```

### 4.4 Error Shape

```json
{
  "error": {
    "code": "OUT_OF_STOCK",
    "message": "This item just sold out.",
    "details": {},
    "request_id": "req_..."
  }
}
```

Common error codes:

```text
UNAUTHENTICATED
FORBIDDEN
VALIDATION_ERROR
NOT_FOUND
CONFLICT
OUT_OF_STOCK
PAYMENT_REQUIRED
RATE_LIMITED
AI_UNAVAILABLE
UPLOAD_REJECTED
IDEMPOTENCY_CONFLICT
WEBHOOK_INVALID_SIGNATURE
INTERNAL_ERROR
```

---

## 5. Auth and Account API

### 5.1 Customer Auth

```text
POST /api/v1/auth/signup
POST /api/v1/auth/login
POST /api/v1/auth/logout
POST /api/v1/auth/password-reset/request
POST /api/v1/auth/password-reset/confirm
GET  /api/v1/account/me
PATCH /api/v1/account/me
```

Signup request:

```json
{
  "email": "customer@example.com",
  "password": "...",
  "name": "Customer Name"
}
```

Account response:

```json
{
  "customer_id": "cust_...",
  "email": "customer@example.com",
  "name": "Customer Name",
  "saved_photo": {
    "exists": true,
    "uploaded_at": "2026-05-27T00:00:00Z"
  }
}
```

### 5.2 Admin Auth

```text
POST /api/v1/admin/auth/login
POST /api/v1/admin/auth/logout
POST /api/v1/admin/auth/password-reset/request
POST /api/v1/admin/auth/password-reset/confirm
GET  /api/v1/admin/me
```

Admin auth is separate from customer auth. Admin routes must never accept a customer session as authorization.

---

## 6. Catalog API

### 6.1 Customer Catalog

```text
GET /api/v1/catalog/products
GET /api/v1/catalog/products/{slug}
GET /api/v1/catalog/categories
GET /api/v1/catalog/search
```

Product list query:

```text
GET /api/v1/catalog/products?category=women&size=M&color=black&min_price=5000&max_price=20000&limit=24
```

Product response:

```json
{
  "product_id": "prod_...",
  "slug": "linen-blazer",
  "title": "Linen Blazer",
  "description": "...",
  "category": "Women",
  "pricing": {
    "base_price_amount": 12900,
    "compare_at_price_amount": 15900,
    "currency": "USD"
  },
  "images": [],
  "variants": [
    {
      "variant_id": "var_...",
      "size": "M",
      "color": "Black",
      "available_for_sale": 3
    }
  ],
  "try_on_eligible": true
}
```

Search is keyword-based in Phase 1. Semantic/vector search is deferred.

### 6.2 Product Try-On Seed

```text
POST /api/v1/try-on/seed-product
```

Request:

```json
{
  "product_id": "prod_..."
}
```

Response:

```json
{
  "seeded_product_id": "prod_...",
  "message": "Upload a photo to try this on."
}
```

---

## 7. Cart API

```text
GET    /api/v1/cart
POST   /api/v1/cart/lines
PATCH  /api/v1/cart/lines/{line_id}
DELETE /api/v1/cart/lines/{line_id}
POST   /api/v1/cart/merge
POST   /api/v1/cart/revalidate
POST   /api/v1/cart/full-look
```

### 7.1 Add Catalog Item

```json
{
  "product_id": "prod_...",
  "variant_id": "var_...",
  "quantity": 1,
  "source": "catalog"
}
```

### 7.2 Add Full Look

```json
{
  "try_on_session_id": "try_...",
  "card_id": "card_...",
  "items": [
    {
      "product_id": "prod_...",
      "variant_id": "var_...",
      "selected_size": "M",
      "quantity": 1
    }
  ]
}
```

Response:

```json
{
  "cart": {},
  "unavailable_items": [],
  "swap_suggestions": []
}
```

Rules:

- Recheck stock and publication state at add time.
- If some items are unavailable, return partial result and swap suggestions.
- Do not trust generation-time inventory.

---

## 8. Checkout API

```text
POST /api/v1/checkout/sessions
GET  /api/v1/checkout/sessions/{checkout_session_id}
POST /api/v1/checkout/sessions/{checkout_session_id}/cancel
```

Create checkout session request:

```json
{
  "cart_id": "cart_...",
  "guest_email": "guest@example.com",
  "shipping_address": {},
  "billing_address": {},
  "discount_code": "WELCOME10"
}
```

Response:

```json
{
  "checkout_session_id": "chk_...",
  "stripe_client_secret": "...",
  "expires_at": "2026-05-27T00:10:00Z",
  "totals": {
    "subtotal_amount": 10000,
    "discount_amount": 0,
    "tax_amount": 800,
    "shipping_amount": 1200,
    "total_amount": 12000,
    "currency": "USD"
  },
  "inventory_holds": []
}
```

Rules:

- Revalidate cart before creating holds.
- Create atomic inventory holds before payment intent.
- If any hold fails, return `OUT_OF_STOCK`.
- Payment success is finalized through webhook, not browser callback.

---

## 9. Orders API

### 9.1 Customer Orders

```text
GET  /api/v1/orders
GET  /api/v1/orders/{order_id}
POST /api/v1/orders/{order_id}/cancel
PATCH /api/v1/orders/{order_id}/shipping-address
```

### 9.2 Guest Order Management

```text
GET   /api/v1/orders/guest/{order_id}
POST  /api/v1/orders/guest/{order_id}/cancel
PATCH /api/v1/orders/guest/{order_id}/shipping-address
POST  /api/v1/orders/guest/{order_id}/claim
```

Guest endpoints require a signed guest token.

Rules:

- Customer/guest cancellation is allowed only before `packed`.
- Customer/guest address edit is allowed only while paid and not packed.
- Support/admin can make changes after verified support process.

---

## 10. Try-On API

### 10.1 Upload and Start Job

```text
POST /api/v1/try-on/sessions
```

Multipart request:

```text
photo: file
height: optional
fit_preference: optional
occasion: optional
prompt: optional
seeded_product_id: optional
use_saved_photo: optional boolean
```

Response:

```json
{
  "try_on_session_id": "try_...",
  "job_id": "job_...",
  "sse_url": "/api/v1/try-on/jobs/job_.../events"
}
```

### 10.2 Job Status and SSE

```text
GET /api/v1/try-on/jobs/{job_id}
GET /api/v1/try-on/jobs/{job_id}/events
```

SSE event:

```text
event: designer.image_completed
id: evt_0007
data: {"job_id":"job_...","stage":"designer","progress_percent":70,"image_url":"...","card_id":"card_..."}
```

Reconnect:

```text
Last-Event-ID: evt_0007
```

### 10.3 Refine Existing Session

```text
POST /api/v1/try-on/sessions/{try_on_session_id}/refine
```

Request:

```json
{
  "prompt": "Show warmer pieces",
  "keep_body_profile": true
}
```

### 10.4 Fitting Room

```text
GET    /api/v1/account/fitting-room
GET    /api/v1/account/fitting-room/{try_on_session_id}
DELETE /api/v1/account/fitting-room/{try_on_session_id}
POST   /api/v1/account/saved-photo
DELETE /api/v1/account/saved-photo
```

Rules:

- Anonymous sessions expire.
- Registered sessions persist until deletion.
- Deleting a session deletes generated images and related AI profile data for that session.

---

## 11. Media API

```text
POST /api/v1/media/signed-upload
POST /api/v1/media/signed-download
GET  /api/v1/media/{media_asset_id}
```

Rules:

- Product public media can be CDN served.
- Private media uses short-lived signed URLs.
- Upload endpoints validate purpose before issuing a signed URL.

---

## 12. Admin API

All admin endpoints require admin auth.

### 12.1 Products and Variants

```text
GET    /api/v1/admin/products
POST   /api/v1/admin/products
GET    /api/v1/admin/products/{product_id}
PATCH  /api/v1/admin/products/{product_id}
DELETE /api/v1/admin/products/{product_id}

POST   /api/v1/admin/products/{product_id}/variants
PATCH  /api/v1/admin/variants/{variant_id}
DELETE /api/v1/admin/variants/{variant_id}
```

### 12.2 Size Charts

```text
GET   /api/v1/admin/size-charts
POST  /api/v1/admin/size-charts
PATCH /api/v1/admin/size-charts/{size_chart_id}
```

### 12.3 Orders and Refunds

```text
GET   /api/v1/admin/orders
GET   /api/v1/admin/orders/{order_id}
PATCH /api/v1/admin/orders/{order_id}/status
PATCH /api/v1/admin/orders/{order_id}/shipping-address
POST  /api/v1/admin/orders/{order_id}/refunds
POST  /api/v1/admin/orders/{order_id}/support-notes
```

### 12.4 Customers

```text
GET /api/v1/admin/customers
GET /api/v1/admin/customers/{customer_id}
```

### 12.5 Analytics and AI Controls

```text
GET   /api/v1/admin/analytics/overview
GET   /api/v1/admin/analytics/ai
GET   /api/v1/admin/ai/jobs
GET   /api/v1/admin/ai/jobs/{job_id}
PATCH /api/v1/admin/settings/ai
```

AI settings payload:

```json
{
  "kill_switch_enabled": false,
  "daily_spend_ceiling_amount": 5000,
  "anonymous_daily_limit": 3,
  "registered_weekly_limit": 10
}
```

### 12.6 Audit Logs

```text
GET /api/v1/admin/audit-logs
```

---

## 13. Webhook API

Webhook receiver may live in Next.js or FastAPI depending on hosting. FastAPI owns final processing.

### 13.1 Stripe

```text
POST /api/v1/webhooks/stripe
```

Required behavior:

- Verify Stripe signature.
- Store `provider_event_id`.
- Process idempotently.
- Create/confirm order on payment success.
- Convert inventory holds to committed sale.
- Update order on refunds.
- Ignore duplicate events.

Important events:

```text
payment_intent.succeeded
payment_intent.payment_failed
checkout.session.completed
charge.refunded
refund.created
refund.updated
```

### 13.2 Shipping

```text
POST /api/v1/webhooks/shipping
```

Required behavior:

- Verify provider signature if available.
- Store event.
- Update fulfillment/tracking state.
- Ignore duplicates.

---

## 14. Rate Limits

Required Phase 1 limits:

| Area | Suggested limit |
|---|---|
| Login | Strict per IP/email |
| Password reset | Strict per email/IP |
| Photo upload | Per IP/device/customer |
| AI generation | Per IP/device/customer and daily spend |
| Guest order link | Per token/IP |
| Checkout creation | Per cart/session |
| Admin auth | Strict per IP/email |

Exact limits belong in environment config and admin settings.

---

## 15. API Acceptance Criteria

The API contract is ready when:

- Every Phase 1 customer flow has an endpoint path.
- Admin CRUD, orders, refunds, AI controls, and audit logs have endpoint paths.
- AI job creation, SSE, reconnect, and refine are defined.
- Webhook idempotency and verification are explicit.
- Error shape is consistent.
- API names map cleanly to `DATA_MODEL.md` collections and `ARCHITECTURE.md` modules.
