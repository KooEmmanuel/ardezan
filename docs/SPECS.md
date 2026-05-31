# Specification — Modern AI-Native Clothing Store

> **Status:** Draft v0.1 — foundation document
> **Owner:** Emmanuel Nyatefe
> **Date:** 2026-05-26

---

## 1. What We're Building (In One Paragraph)

A single-owner online clothing store with two halves: a **customer storefront** built around an AI try-on experience, and an **admin panel** the owner uses to manage inventory, orders, and operations. When a customer lands on the site, they don't see a catalog of products — they see an invitation to upload a photo and have the store style them. After ~15 seconds, they get ten personalized outfits rendered onto their body, ready to add to cart. Traditional catalog browsing is one click away for anyone who wants it, but it is the opt-out, not the default.

This is not a SaaS, not a marketplace, not a brand identity exercise. It is one store the owner runs, built from scratch instead of on Shopify so the AI experience can be first-class.

---

## 2. Who Uses It

| Role | What they do | How they enter |
|---|---|---|
| **Anonymous Customer** | Browse, search, AI try-on (capped), add to cart, checkout as guest | Visit homepage |
| **Registered Customer** | Everything above + saved profile, order history, higher capped try-ons | Email signup |
| **Store Owner (Admin)** | Manage products, inventory, orders, customers, view analytics | Admin login |
| **Operations Staff** *(future)* | Fulfill orders, handle returns, customer support | Admin login with limited scope |

---

## 3. The Customer Experience

The customer can shop in two views. They are not separate apps — both live on the same site and switch instantly via a header toggle.

### 3.1 The Two Views (Header Toggle)

Every page has a persistent segmented control in the header:

```
[ Try-On ]  [ Catalog ]
```

- **Try-On** is selected by default for any first-time visitor.
- The choice persists in `localStorage`. A returning visitor who previously switched to Catalog lands back in Catalog.
- On mobile the toggle compresses to two icons but stays in the header.
- The toggle is always one tap away — switching views never requires going back to the homepage.

### 3.2 Try-On View (Default Landing)

This is the first thing a new customer sees. No product grid, no banners — just the invitation to be styled.

The view has three states:

| State | When | What's shown |
|---|---|---|
| **Empty** | First-time visitor, or after "Start over" | Centered upload zone, one-line value prop ("See clothes on you in 15 seconds"), `Refine` link that expands optional fields (height, fit preference, occasion) |
| **Loading** | After upload, while the orchestrator runs | Live progress streamed from the orchestrator: "Reading your photo…" → "Finding pieces that fit…" → "Styling outfit 3 of 10…". No abstract spinner. |
| **Results** | After generation completes | Grid of up to 10 try-on cards. Each card: the customer wearing the outfit, a short outfit name, the per-item product list, the bundle total + each item price, "Add full look to cart", and a per-item add button next to each line. A `Refine` bar sits above the grid for follow-up prompts. A `Start over` link sits in a subtle secondary position. |

**Try-on card contents.** Each card represents an outfit, which may be a single item or a multi-piece bundle.
- The **bundle total** is shown as the primary price; per-item prices are shown beneath in a smaller weight.
- A **recommended size** is auto-selected per item using the Analyzer's measurements; the customer can override the size per item from a compact selector on the card.
- "Add full look to cart" adds every item at the recommended (or user-overridden) size.
- A per-item add button lets the customer pick only one piece of the outfit instead of the whole bundle.
- If a recommended item is on sale, its compare-at price is shown struck through next to the sale price.

**Refinement vs. starting over.** When a customer with existing results asks for changes ("swap the trousers", "show warmer pieces"), the orchestrator re-runs against the existing profile and produces new variants — it does **not** discard the photo or re-analyze the body. Starting over is an explicit, separate action.

**Hesitant-visitor fallback.** A small secondary affordance below the upload zone — *"Not ready to upload? See looks on our models"* — lets a visitor preview a curated set of pre-generated outfits on a generic model. This is not the AI try-on; it's a low-commitment bridge into the experience that still avoids dumping the visitor into the raw catalog.

**Resilience during generation.** A try-on session is identified by a server-side `job_id`. If the page refreshes or the SSE stream drops mid-generation, the client reattaches to the in-progress job using `last-event-id`. If the job has already completed, the cached result is returned. If the job is unrecoverable, the UI cleanly resets to the Empty state with a one-line explanation.

**Responsive layout:**
- Mobile: 1-column card grid with swipe; upload zone fills width.
- Tablet: 2-column grid; upload zone max ~600px centered.
- Desktop: 3–4 column grid; upload zone max ~600px centered (never stretches edge-to-edge on wide monitors).

### 3.3 Catalog View (Opt-Out)

The traditional path for anyone who doesn't want to upload a photo, or who is shopping for someone else, or who prefers browsing.

- Browse by category (Men, Women, New, Accessories)
- Search and filter (size, color, price)
- View product → add to cart → checkout
- Receive shipping confirmation by email

**Search behavior (Phase 1):** keyword search with simple filters. Semantic / vector-based search is on-brand for an AI store but adds infrastructure (embedding generation, vector index) and is deferred to Phase 2 once we have real query telemetry to tune against.

A small "Try this on you" link on each product page is the bridge back into Try-On — it pre-loads that specific product as the seed for a try-on session.

### 3.4 Conversational Refinement (Inside Try-On)

The `Refine` bar at the top of the Results state accepts natural-language prompts:
- "Find me a semi-formal outfit for an outdoor summer wedding"
- "Pack a virtual suitcase of 5 pieces for a London trip"
- "Show this blazer with darker trousers instead"

Without a photo uploaded, the same bar still works but returns standard catalog matches with no body-rendered images.

### 3.5 Returning Visitors

What the customer sees on return depends on whether they're signed in.

**Anonymous returning** (same browser, within 24 hours):
- Browser-side `localStorage` keeps only the generated **image URLs and product IDs** from their last session — never the original uploaded photo.
- On return they see their last results with a banner: *"Welcome back — here's what we styled for you. [Try again] [Start over]"*.
- After 24 hours, results expire and the view falls back to the Empty state.

**Signed-in returning:**
- Land in their **Fitting Room** — a grid of past try-on sessions, most recent first, each shown as one representative card.
- Top of the page: prominent `Start a new try-on` button, with a `Use my saved photo` fast-path that skips upload if they previously opted in to save.
- Clicking any past session opens the full 10-card view from that day.
- The Fitting Room is itself a state of the Try-On view; the header toggle still switches them to Catalog at any time.

### 3.6 UI Direction — Premium Glass, Not Glass Everywhere

The visual direction should combine **minimalist luxury commerce** with **selective liquid glass / glassmorphism**. The store is AI-native, so it should feel modern and slightly magical, but it is still selling clothes and taking payments. Trust, readability, and product clarity matter more than visual effects.

Recommendation:
- Use glassmorphism as the signature treatment for the **Try-On experience**, especially the upload card, generated outfit cards, refine bar, progress state, floating mobile navigation, and AI result overlays.
- Use a cleaner minimalist layout for **Catalog, Product Detail, Cart, Checkout, and Admin** so prices, sizes, inventory, payment details, and order information stay clear.
- Avoid neo-brutalism for this project; it is memorable, but too loud for a premium AI clothing store.
- Avoid claymorphism and skeuomorphism as the main style; they feel playful/tactile, but less aligned with fashion commerce and AI styling.
- Borrow the restraint of minimalist luxury for typography, spacing, product photography, and checkout trust.
- Borrow the depth of liquid glass for moments where the customer is interacting with AI.

Glassmorphism usage rules:
- Glass only works when there is visual depth behind it: soft gradients, blurred fashion imagery, or subtle color fields. Do not place glass cards on plain white pages and expect the effect to work.
- Keep glass layers limited to 2–3 stacked surfaces to avoid visual noise and mobile GPU cost.
- Text on glass must meet WCAG AA contrast. If contrast is uncertain, use a more opaque surface or a solid fallback.
- Every glass surface must have a fallback solid/semi-solid background for browsers or devices where `backdrop-filter` performs poorly.
- Primary commerce actions like `Add to cart`, `Checkout`, `Pay`, and `Refund` should use solid, high-contrast buttons rather than low-contrast glass buttons.
- Product photos should remain crisp and unblurred. Glass can frame or overlay them, but should not reduce product detail.

Suggested visual system:
- **Base:** warm white / soft gray commerce pages with generous whitespace.
- **Accent:** deep teal, black, ivory, and controlled AI-blue/green gradients.
- **Typography:** clean sans-serif for UI; optional elegant serif or high-contrast display type for campaign/editorial headings.
- **Surfaces:** solid cards for catalog and checkout; frosted glass cards for try-on upload/results/refinement.
- **Motion:** subtle fade/blur transitions during AI progress; respect `prefers-reduced-motion`.

---

## 4. What the Store Owner Does

The admin panel is a normal e-commerce back office with a few AI-specific additions.

**Standard:**
- Add / edit / delete products (title, description, price, sizes, colors, photos, stock count)
- View and update orders (paid → packed → shipped → delivered)
- Manage customers (view profile, contact, order history)
- View basic analytics (revenue, top products, conversion rate)
- Manage suppliers, delivery partners, and shipping rules

**AI-specific:**
- Tag products with **AI metadata** (fabric type, formality, fit shape, season, color palette). These tags are what the AI Recommender uses to match products to a customer profile.
- Review AI try-on performance: which products are most often recommended, how often try-ons convert to purchase, flagged "expectation gap" complaints.
- Set the **email-gate threshold** (how many free try-ons before signup is required) — *open decision, see §13*.

---

## 5. Core Commerce Requirements

These are the normal e-commerce requirements that must exist underneath the AI experience. The AI can make the store feel new, but the store still has to behave like a dependable clothing business.

### 5.1 Products, Variants, and Inventory

Every product must support:
- Product title, description, category, tags, price, sale price, status, and publication state.
- Multiple images, including product photos optimized for the catalog and AI-friendly images when available.
- Variants by size, color, SKU, and stock count. Inventory is tracked at the variant level, not only the product level.
- Product measurements, material, care instructions, fit notes, and return eligibility.
- Size chart data: house/brand size chart, body measurement ranges per size, garment measurements when available, and fallback behavior when no chart exists.
- AI eligibility flag so the owner can decide whether a product can appear in generated outfits.
- AI metadata: fabric type, formality, fit shape, season, color palette, body/occasion suitability, layering compatibility.

Inventory rules:
- Stock decrements only after successful payment confirmation.
- Checkout must prevent purchase of out-of-stock variants.
- Low-stock and out-of-stock states must be visible in the admin panel.
- **Soft reservation on checkout start.** When a customer reaches the checkout step, the variants in their cart are soft-held for ~10 minutes (configurable). Soft-held units count against availability for everyone else. If payment succeeds, the hold converts into a real decrement; if payment fails, the customer abandons, or the timer expires, the hold releases automatically.
- **Last-unit race.** Soft holds use an atomic conditional update on the variant document (e.g., MongoDB `findOneAndUpdate` with a stock check) so two simultaneous attempts cannot both succeed. The losing customer sees a clear "this just sold out" message at checkout, not a silent failure.
- **Size auto-suggest from body analysis.** When the Analyzer produces measurements, the system maps them to the nearest available variant size per product using a per-product or per-brand size chart. The recommendation is shown on each try-on card and added to cart by default; the customer can override the size before adding.

### 5.2 Cart and Checkout

The checkout flow must support:
- Guest checkout and registered customer checkout.
- Cart item editing, quantity changes, variant changes, and item removal.
- Shipping address collection, billing details, and address validation where supported.
- Taxes, shipping rates, discounts/promo codes, and order totals before payment.
- Payment success, payment failure, cancellation, refund, and webhook reconciliation.
- Email confirmation after order placement and shipping updates after fulfillment.

Payment webhooks must be idempotent. A repeated webhook should not create duplicate orders, double-decrement inventory, or send duplicate critical emails.

**Cart persistence:**
- **Anonymous customers** — cart lives in browser `localStorage`, keyed by a stable client-side cart ID. The cart survives page reloads and browser restarts but is scoped to the device.
- **Registered customers** — cart lives server-side on the customer document, available across devices.
- **Login merge** — when a guest with items in their local cart signs in or signs up, the local cart is merged into the server cart. Conflicts (same variant in both carts) keep the higher quantity; the customer sees a one-line note on the cart page.
- **Stale cart revalidation** — before checkout starts, every cart item is revalidated against current product status, variant availability, stock, price, and promotion rules. If an item is unavailable, unpublished, repriced, or out of stock, the cart updates clearly before the customer reaches payment.

**Guest-to-account claim:** A guest who completes checkout receives a one-time secure link in their confirmation email to create an account and claim the order into it. The claim window stays open for 7 days. After that, support can manually attach orders by verified email.

### 5.3 Orders, Fulfillment, and Returns

Orders move through clear statuses:

```
pending_payment → paid → packed → shipped → delivered
```

Cancelled, refunded, partially refunded, returned, and exchanged states must also be supported, even if the Phase 1 return process is manual.

Phase 1 does **not** need automated returns, but it does need:
- A visible return/exchange policy.
- Admin ability to mark an order as return requested, returned, exchanged, refunded, or partially refunded.
- Customer support notes on orders.
- Refund handling through the payment provider.

**Order modification:**
- **Customer-initiated** — a customer can cancel their order from their order history as long as it has not entered the `packed` status. After `packed`, cancellation requires admin action and the change-of-mind is treated as a return request.
- **Guest customer changes** — guest customers do not have order history. Their confirmation email includes a secure order-management link for cancellation and address edits within the same pre-`packed` rules. If the secure link is expired or unavailable, support can make the change after verifying the order email.
- **Customer shipping address edit** — allowed while the order is `paid` but not yet `packed`. Validated against the supported delivery region before saving.
- **Admin-initiated** — admin can cancel, refund (full or partial), and edit shipping address at any pre-shipment status. Adding a new line item to an existing order is not supported in Phase 1; the operational answer is "create a new linked order" so the audit trail stays clean. Every modification is recorded in the order's audit log.

### 5.4 Admin Security and Permissions

Admin access must be protected more strictly than customer access.

Phase 1 requires:
- Secure admin login.
- Password reset flow.
- Role-ready admin user model, even if there is only one owner at launch.
- Audit log for product changes, inventory changes, order status changes, refunds, and admin login events.
- Confirmation prompts for destructive actions like deleting products, refunding orders, or cancelling fulfillment.

MFA is strongly recommended for the owner account before real orders are accepted.

---

## 6. The AI Orchestrator — How It Works

When a customer uploads a photo and asks for recommendations, a chain of three AI agents runs. One orchestrator coordinates them.

```
[Photo + Optional Form]
        ↓
   [ORCHESTRATOR]  ← coordinator; never calls the LLM directly for end-user content
        ↓
   ┌────┴────┐
   ↓         
[1. ANALYZER]   "Read the customer."
  Input:  Photo, height, fit preference
  Output: Body shape, skin undertone, estimated measurements, current outfit style
        ↓
[2. RECOMMENDER]  "Pick products that fit them."
  Input:  Analyzer profile + current catalog (via MongoDB MCP)
  Output: Top 10 product or outfit combinations, ranked
        ↓
[3. DESIGNER]   "Show them wearing it."
  Input:  Customer photo + each recommended outfit
  Output: 10 rendered try-on images (Nano Banana / Gemini 2.5 Flash Image)
        ↓
[ORCHESTRATOR returns 10 cards to frontend via SSE stream]
```

Each step streams progress back to the UI so the customer sees what's happening ("Reading your photo…", "Finding pieces that fit…", "Styling outfit 3 of 10…") rather than staring at a spinner.

If any step fails, the orchestrator returns partial results — e.g., recommendations without renders — rather than nothing.

**Stock awareness during the orchestration:**
- The Recommender filters the candidate set to variants with `stock > 0` in at least one size that fits the customer's measurements, at generation time.
- Stock is **rechecked at the moment of "Add full look to cart"**, not trusted from generation time. If any item is no longer available, the UI surfaces a swap suggestion ("This jacket just sold out — here's the closest match") rather than failing silently or adding a doomed line item.
- If the entire recommended outfit becomes unavailable, the customer is offered an in-place re-roll of the affected outfit without re-running the Analyzer.

### 6.1 AI Quality and Safety Rules

The AI experience needs guardrails because customers are uploading personal photos and expecting visual results that affect purchase decisions.

Before generation, the upload flow must reject or ask for a better photo when:
- The image contains multiple people and the primary subject is unclear.
- The body is too obscured, cropped, blurry, dark, or low resolution.
- The photo contains nudity, explicit content, or unsafe content.
- The file type, file size, or dimensions are outside the allowed limits.

**Minor detection.** Uploaded photos detected as containing a minor are auto-rejected even when the rest of the image is otherwise safe. The rejection message points to the 18+ requirement; no second attempt is offered on the same upload.

The AI should avoid body-shaming language. Customer-facing text should describe fit and styling in neutral, useful terms, not in judgmental terms.

Try-on cards must include a short disclaimer: generated images are visual approximations and do not guarantee exact fit, fabric drape, color accuracy, or final tailoring.

**AI-generated content disclosure.** Every try-on image is labeled as AI-generated in a visible but non-intrusive way (e.g., a small "AI preview" badge in a consistent corner of the card, plus an `alt` text that names it as such for screen readers). Where technically supported, generated images should embed durable provenance metadata (e.g., C2PA/IPTC `digitalSourceType` of `trainedAlgorithmicMedia`), but the visible label is the primary user-facing disclosure because metadata can be stripped by downloads, screenshots, optimization pipelines, and social platforms. This supports EU AI Act Article 50 disclosure expectations and equivalent US state laws.

### 6.2 AI Abuse and Cost Controls

Local browser limits are useful for UX, but they are not enough for cost control. Phase 1 must include server-side controls:
- Rate limits by account, IP, and device/session fingerprint where legally appropriate.
- Daily spend ceilings and an admin kill switch for AI generation.
- Per-user/session try-on caps for anonymous and registered users.
- Queueing or backpressure when AI generation demand is high.
- Bot protection on upload and generation endpoints.
- Logging of generation count, provider cost estimate, latency, failure reason, and conversion outcome.

If the AI budget is exhausted or the provider is down, the storefront falls back to catalog shopping and the UI explains that try-on is temporarily unavailable.

---

## 7. What We Store (and What We Don't)

### Stored
- **Products** — catalog, variants, SKUs, stock counts, product photos, measurements, and AI metadata tags
- **Orders** — line items, shipping address, taxes, shipping method, payment status, refund status, fulfillment status (we never store card numbers; that's the payment provider's job)
- **Registered customer profiles** — email, name, addresses, saved photo (only if they explicitly opt in), AI-derived body profile, order history. Saved photos carry `photo_uploaded_at` and `photo_consent_version` timestamps so consent reissuance after a privacy policy change is auditable.
- **Admin users** — credentials, role, audit log of admin actions
- **AI analytics** — recommendation hit rates, generation counts, cost per session

### Not Stored
- **Anonymous customer photos** — processed in memory or short-lived cache, deleted after the session ends or after a hard cap (e.g., 15 minutes), whichever comes first
- **Anonymous customer body profiles** — same rule
- **Payment card details** — handled entirely by the payment provider (Stripe / similar)

### Cached Client-Side
- **Anonymous try-on results** — only the generated image URLs and product IDs are kept in browser `localStorage` for up to 24 hours so a returning visitor can see their last results. The image URLs themselves are time-limited signed URLs that expire on the same schedule, so a leaked URL doesn't grant indefinite access.
- **View preference** — whether the visitor last used Try-On or Catalog view.

### Generated Image Retention

Generated try-on images are separate from original uploaded photos:
- Anonymous generated images may be stored only long enough to power the 24-hour return experience, then deleted or made inaccessible.
- Signed URLs for anonymous generated images expire within the same 24-hour window.
- Registered customer generated images can be retained as part of their Fitting Room until the customer deletes the session or account.
- If a registered customer deletes a saved try-on session, the generated images and related AI profile data for that session must be deleted as well.

The privacy flow is simple: nothing about you is kept unless you create an account. This is a feature, not a footnote — it goes in the upload modal copy.

### Image Rights and Usage

The generated try-on image is a derivative of the customer's likeness combined with the store's product imagery. Ownership and use must be unambiguous in the Terms of Service.

- **Customer owns their likeness** — including its appearance in generated images. The customer can request deletion at any time.
- **Store retains a limited license** to display generated images back to the customer who created them, and to use anonymized aggregates (e.g., heatmaps of body shape distributions) for product and operational analytics.
- **No marketing reuse without explicit consent.** Generated images of an identifiable customer are never used in advertising, social posts, or homepage content unless the customer opts in via a separate consent prompt.
- **No third-party sale** of customer photos, generated images, or body profile data.

---

## 8. Integrations (External Systems We Talk To)

| System | What it does for us | How we talk to it |
|---|---|---|
| **Google Gemini API** | Body analysis, conversational understanding, function-calling for the orchestrator | REST (Gemini SDK) |
| **Nano Banana (Gemini 2.5 Flash Image)** | Try-on image generation | REST (Gemini SDK) |
| **MongoDB Atlas** | Primary database | Native driver + MongoDB MCP server (so the AI agent can query catalog directly) |
| **Stripe** (or equivalent) | Payments, invoicing, refunds | REST + webhooks |
| **Shipping carrier** (TBD: DoorDash for local, FedEx/UPS for long-haul) | Delivery, tracking | REST + webhooks |
| **Email service** (e.g., Resend, SendGrid) | Order confirmations, password resets, marketing | REST |
| **Image storage** (S3 or equivalent) | Product photos, opted-in customer photos, generated try-on images | REST (signed URLs) |
| **Supplier APIs** *(future, Phase 3+)* | Inventory replenishment, drop-ship | Per-supplier |

---

## 9. Non-Functional Requirements (The Boring Stuff That Matters)

### Privacy
- Anonymous photo uploads are processed ephemerally and deleted within 15 minutes.
- Photo upload modal shows in plain language: *"Your photo is sent to Google for analysis and image generation. We don't keep it unless you create an account."*
- Age gate before upload: 18+ confirmation checkbox. Heavier verification may be required in some jurisdictions — to be reviewed per launch market.
- GDPR / CCPA compliance: data export, account deletion, processing log.
- Consent copy must explain that uploaded photos are sent to third-party AI providers for analysis and image generation.
- The provider retention/training policy must be reviewed before launch and reflected in the privacy policy.
- Body analysis may create sensitive inferences. Store only what is needed for styling, and only for registered users who have opted in.
- Customers must be able to delete saved photos, generated try-on sessions, and their account data.

### Cost Control
- Each try-on session costs real money (analyzer call + 10 image generations ≈ $0.30–$1.50 at current pricing).
- Anonymous users get a hard cap (e.g., 3 try-ons per day) before being asked to sign up. The cap is enforced as the **lesser of per-IP, per-browser-fingerprint, and per-localStorage-marker** — `localStorage` alone is trivially bypassed by clearing site data.
- Registered users get a generous but finite weekly cap (e.g., 10 try-on sessions) to prevent abuse.
- Admin can see per-day spend and set ceilings.
- Limits are enforced server-side, not only in `localStorage`.
- Admin can disable AI generation without taking down catalog shopping or checkout.

### Performance
- Storefront pages: server-rendered, target < 2s to first contentful paint.
- AI orchestrator end-to-end: target < 15s for the full 10 try-ons; partial results stream as they're ready.
- Catalog search: < 300ms for typical queries.

### Reliability
- A failure in the AI layer must never break traditional shopping. If Gemini is down, the site still sells clothes.
- Orders, payments, and inventory updates are the critical path and get the strictest error handling.
- Payment, order, and inventory operations must be recoverable after retries, webhook repeats, and provider timeouts.

### Observability
- Track storefront errors, admin errors, AI job failures, payment webhook failures, and email delivery failures.
- Log each AI job with request ID, user/session ID, provider calls, latency, status, cost estimate, and failure reason.
- Log payment and shipping webhooks with enough detail to debug duplicates, retries, and missed events.
- Admin dashboard should show revenue, conversion rate, AI spend, AI conversion rate, failed generations, top recommended products, and expectation-gap complaints.

### Accessibility
- WCAG 2.1 AA minimum. The AI features are an enhancement; the traditional storefront must be usable without them.
- Upload, refine, cart, checkout, and admin flows must work by keyboard.
- Catalog shopping must remain usable without generated images.
- AI-generated images need meaningful surrounding text so screen reader users can understand the outfit and products.

### SEO and Discoverability
- Product and category pages must be crawlable even though the default homepage is Try-On.
- Product pages need unique titles, descriptions, canonical URLs, structured data where practical, and shareable URLs.
- Catalog view should be reachable by direct URL, not only by toggling from the Try-On view.

### Security and Upload Handling
- Uploaded files must be validated by type, size, dimensions, and content safety checks.
- Signed URLs must expire and should not expose permanent object paths.
- Admin routes must be protected server-side.
- Customer and admin sessions must use secure cookies and CSRF protection where applicable.
- Secrets live in environment variables or a secrets manager, never in source control.

### Deployment and Operations
- Separate development, staging, and production environments.
- Database backups and restore process before real orders are accepted.
- CI checks for build, lint, and tests.
- Environment-specific configuration for payments, AI providers, email, storage, and webhooks.
- Basic runbook for provider outages, failed payments, AI budget exhaustion, and manual order correction.

---

## 10. Out of Scope for Phase 1

We are explicitly not building these yet. Listed here so they don't sneak in.

- **3D body avatars or fabric simulation engines.** Image-only renders are sufficient to validate the concept.
- **Wardrobe twin / closet integration.** Phase 3.
- **Calendar-aware proactive recommendations.** Phase 3.
- **Multi-tenant / multi-brand support.** Not the business.
- **Native mobile apps.** The Next.js site will be mobile-responsive; native comes later if needed.
- **Agentic checkout.** The AI never spends the customer's money. Cart and payment stay human-driven.
- **Returns automation.** Phase 2.
- **Multi-currency / multi-locale storefronts.** Phase 1 launches in one currency, one country, one language.
- **Multi-warehouse inventory.** Inventory is tracked from a single fulfillment origin in Phase 1.
- **Pre-order / backorder / waitlists.** Out-of-stock means out-of-stock until restocked.
- **Accessories try-on** (shoes, hats, bags, jewelry). The Designer is scoped to torso + lower-body apparel in Phase 1.
- **Gift mode** (uploading another person's photo for them). Phase 2 at earliest, after consent UX is resolved.
- **Marketing email program / newsletter automation.** Phase 1 sends transactional email only.
- **Full cookie consent management platform (CMP) with granular vendor controls.** A minimum-viable consent banner is required for GDPR/CCPA at launch; the full enterprise-style CMP is deferred.
- **Semantic / vector search.** Phase 1 catalog search is keyword-based.
- **Adding line items to an existing order.** The clean operational path is a new linked order.

---

## 11. Delivery Model

The project is still delivered in phases, but **Phase 1 is not one giant launch**. Phase 1 is the full MVP build, delivered through smaller milestones so we can move from foundation to usable store to AI-native shopping without pretending everything has to land at once.

### Phase 1 — MVP Build

Phase 1 gets the basic product into existence: a working storefront, admin panel, checkout flow, inventory/order management, and the first usable AI try-on experience. The goal is not perfection yet. The goal is to build the full foundation end-to-end so the owner can see and test the business as a real store.

| Milestone | What ships | Goal |
|---|---|---|
| **1. Foundation** | Project setup, database schema, auth foundation, product model, image storage, basic admin shell | Establish the technical base everything else sits on |
| **2. Catalog Commerce** | Product browsing, product detail pages, cart, checkout, payments, order records, basic email confirmations | Make the store capable of selling clothes without AI |
| **3. Admin Operations** | Product CRUD, variant/stock management, order status updates, customer records, basic analytics | Give the owner control of day-to-day operations |
| **4. AI Try-On v1** | Photo upload, analyzer/recommender/designer orchestration, streamed progress, 10 generated looks, add full look to cart | Prove the identity-first shopping experience |
| **5. Accounts + Fitting Room** | Customer signup/login, saved try-on sessions, optional saved photo, order history | Let returning customers continue from previous sessions |
| **6. MVP Stabilization** | Bug fixes, basic privacy controls, rate limits, error handling, deployment readiness | Prepare the MVP for real user testing |

### Phase 2 — UAT, Hardening, and Rework

Phase 2 starts after the MVP exists end-to-end. This is where we slow down, test deeply, find edge cases, and improve or rewrite pieces that were good enough for MVP but not good enough for real launch.

Phase 2 includes:
- User acceptance testing with the owner and a small group of real shoppers.
- Fixing checkout, payment, inventory, shipping, and admin edge cases.
- Improving the AI try-on quality based on real results and expectation-gap complaints.
- Reworking flows that feel confusing once tested by real users.
- Strengthening privacy, abuse prevention, logging, analytics, and operational tooling.
- Cleaning up technical shortcuts taken during MVP if they create risk for launch.

### Phase 3 — Expansion

Phase 3 is for new capabilities after the MVP has been tested and hardened.

| Area | Examples |
|---|---|
| **Recommendation depth** | Wardrobe context, weather-aware suggestions, fit preference learning |
| **Operations expansion** | Supplier integrations, deeper returns automation, replenishment workflows |
| **Personalization** | Closet integration, calendar-aware proactive recommendations |
| **New surfaces** | Native mobile app, richer customer profile, post-purchase styling |

---

## 12. Phase 1 Acceptance Criteria

Phase 1 is done when the MVP can be used end-to-end by the owner and a small test group without developer intervention for normal shopping flows.

### Customer Storefront
- A visitor can switch between Try-On and Catalog at any time.
- A visitor can browse products, search/filter, view a product, add a variant to cart, and check out as a guest.
- A registered customer can sign in, view order history, and access saved try-on sessions.
- The cart prevents invalid quantities and out-of-stock purchases.
- Customers receive order confirmation and shipping/status emails.

### Admin Panel
- The owner can create and edit products, variants, stock, product photos, and AI metadata.
- The owner can view orders, update fulfillment status, issue refunds through the payment provider, and add support notes.
- The owner can view basic customer records, revenue, top products, conversion rate, AI spend, and AI try-on conversion.
- Admin actions that affect inventory, orders, refunds, or product availability are logged.

### AI Try-On
- A customer can upload a valid photo and receive streamed progress while the orchestrator runs.
- The system returns up to 10 try-on cards with generated image, outfit name, product list, price, and add-full-look-to-cart action.
- Bad uploads are rejected with clear next-step guidance.
- If image generation partially fails, successful recommendations still appear.
- If the AI provider is unavailable, catalog shopping and checkout continue working.

### Privacy, Safety, and Operations
- Anonymous uploaded photos and body profiles are deleted within the configured retention window.
- Anonymous generated images and signed URLs expire within 24 hours.
- Registered customers can delete saved photos and try-on sessions.
- Server-side rate limits, AI spend ceilings, and an admin AI kill switch are in place.
- Payment webhooks are idempotent and do not create duplicate orders.
- Error tracking, AI job logging, payment webhook logging, and basic admin analytics are available.

---

## 13. Open Decisions

These don't block writing the spec, but must be locked before implementation.

1. **Email-gate threshold.** How many free anonymous try-ons before requiring signup? Default proposal: **3 per day (per-IP / per-fingerprint / per-localStorage)**, then signup required.
2. **Age gate.** Hard 18+ confirmation, or soft (just a checkbox)? Soft is easier; hard may be needed in some markets.
3. **Payment provider.** Stripe is the default; confirm vs. alternatives.
4. **Shipping partner mix.** DoorDash for local same-day vs. traditional carriers for everything else — needs to be decided based on the owner's target geography.
5. **Initial product catalog source.** Owner-photographed inventory, or first-time use of stock photos while ramping up?
6. **AI provider retention terms.** Confirm whether uploaded photos or generated outputs are retained or used for model training by the selected provider.
7. **MFA requirement.** Decide whether MFA is required before launch or only strongly recommended for the owner account.
8. **Return policy.** Define return window, final-sale categories, exchange rules, and refund timing.
9. **Tax calculation approach.** Decide whether to use Stripe Tax, a tax provider, or a simpler launch-market-specific setup.
10. **Bot protection.** Decide which protection is acceptable for upload/generation endpoints without hurting legitimate shoppers.
11. **Launch market + currency.** Phase 1 launches in one country with one currency. The specific market drives tax, shipping, payment, language, and compliance choices. Needs to be locked before the architecture document is final.
12. **Size chart source.** Whether the auto-size mapping uses a single house size chart, per-brand charts, or both (per-brand with house fallback). Affects the product data model.
13. **Hesitant-visitor fallback set.** Approve the curated "see on our models" content used for visitors who won't upload. Needs ~6–10 pre-generated outfit images at launch.
14. **Marketing reuse opt-in copy.** Final wording for the optional consent to use a customer's generated images in marketing.

---

## 14. Glossary

- **Orchestrator** — The backend service that coordinates the chain of AI agents. It owns the workflow; the agents own the AI calls.
- **Analyzer / Recommender / Designer** — The three AI agents in the orchestrator chain. Names describe their roles, not specific products or models.
- **Try-on session** — One full pass from photo upload through 10 rendered recommendations.
- **AI metadata** — Per-product tags (fabric, formality, fit shape, palette) used by the Recommender to match products to a customer profile.
- **Identity-first** — Design principle: the catalog stays hidden until the system knows who the customer is.
