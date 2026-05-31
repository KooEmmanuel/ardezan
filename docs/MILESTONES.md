# Milestones - Modern AI-Native Clothing Store

> **Status:** Draft v0.1 - build planning
> **Source documents:** `SPECS.md`, `ARCHITECTURE.md`, `DATA_MODEL.md`, `API.md`, `UI_FLOWS.md`, `requirements-tracker.xlsx`
> **Date:** 2026-05-27

---

## 1. Purpose

This document turns Phase 1 into a buildable sequence. The milestones follow the delivery model in `SPECS.md`:

1. Foundation
2. Catalog Commerce
3. Admin Operations
4. AI Try-On v1
5. Accounts + Fitting Room
6. MVP Stabilization

Phase 1 is the full MVP build. Phase 2 is UAT, hardening, edge cases, rework, and cleanup after the MVP exists end-to-end.

---

## 2. Build Principles

- Build commerce foundations before AI magic.
- Keep AI asynchronous from day one.
- Keep catalog/checkout working without AI.
- Make every milestone demonstrable.
- Use `requirements-tracker.xlsx` as the source of status.
- Do not start a milestone if its blocking open decisions are unresolved.
- Every milestone should update architecture/data/API/UI docs when reality changes.

---

## 3. Milestone 1 - Foundation

### Goal

Establish the technical base everything else sits on.

### Scope

- Repo/app structure.
- Next.js frontend shell.
- FastAPI backend shell.
- Python worker shell.
- MongoDB connection.
- Environment config.
- Basic auth/session foundation.
- Base product/variant/size chart models.
- Object storage integration.
- Logging/error tracking baseline.
- Initial CI checks.

### Key Requirements

- `REQ-001` single-owner system.
- `REQ-027` UI direction.
- `REQ-030` visual tokens.
- `REQ-033` product basics.
- `REQ-034` product media.
- `REQ-035` variant inventory.
- `REQ-036` size chart data.
- `REQ-037` AI metadata.
- `REQ-064` stored data.
- `REQ-070` integrations.
- `REQ-079` deployment ops.

### Deliverables

- Next.js app boots with storefront/admin route shells.
- FastAPI app boots with health endpoint.
- Worker process boots and can run a test job.
- MongoDB indexes for foundation collections.
- Product/variant/size chart Pydantic schemas.
- Storage bucket/prefix strategy implemented for dev.
- CI runs lint/type/build checks where applicable.

### Acceptance

- Developer can run frontend, backend, and worker locally.
- Health checks pass.
- A seed product with variants and images can be created through backend/dev tooling.
- No secrets are committed.

### Blocking Decisions

- Launch market + currency.
- Size chart source.
- Hosting direction, at least for local/staging assumptions.

---

## 4. Milestone 2 - Catalog Commerce

### Goal

Make the store capable of selling clothes without AI.

### Scope

- Catalog page.
- Product detail page.
- Keyword search and filters.
- Cart.
- Stale cart revalidation.
- Checkout.
- Stripe payment integration.
- Inventory soft holds.
- Payment webhooks.
- Order creation.
- Transactional order email.
- Guest checkout and guest order link baseline.

### Key Requirements

- `REQ-003` catalog one click away.
- `REQ-020` catalog commerce.
- `REQ-021` keyword search.
- `REQ-038` stock decrement after payment.
- `REQ-039` out-of-stock prevention.
- `REQ-040` soft holds/last-unit race.
- `REQ-042` checkout.
- `REQ-043` idempotent payment webhooks.
- `REQ-044` cart persistence.
- `REQ-045` stale cart revalidation.
- `REQ-047` order states.
- `REQ-077` SEO/discoverability.

### Deliverables

- Customer can browse catalog.
- Customer can view product details.
- Customer can add selected variant to cart.
- Cart revalidates before checkout.
- Checkout creates inventory holds.
- Stripe payment success creates/updates order.
- Webhook replay is safe.
- Confirmation email sends.

### Acceptance

- Guest user can complete a non-AI purchase.
- Out-of-stock variants cannot be purchased.
- Two simultaneous attempts for one last unit do not oversell.
- Catalog/product pages are crawlable/directly routable.

### Blocking Decisions

- Payment provider confirmation.
- Tax approach.
- Shipping partner or basic shipping rules.

---

## 5. Milestone 3 - Admin Operations

### Goal

Give the owner control of day-to-day operations.

### Scope

- Admin auth.
- Product CRUD.
- Variant/SKU/stock management.
- Size chart management.
- Product media management.
- AI metadata editing.
- Order list/detail.
- Fulfillment status updates.
- Refund actions.
- Manual return/exchange states.
- Support notes.
- Customer records.
- Audit logs.
- Basic analytics dashboard.

### Key Requirements

- `REQ-006` owner admin.
- `REQ-007` role-ready admin model.
- `REQ-031` owner operations.
- `REQ-032` AI metadata/performance controls.
- `REQ-048` manual returns/refunds.
- `REQ-049` order modification.
- `REQ-050` linked order rule.
- `REQ-051` admin security.
- `REQ-075` observability/admin analytics.

### Deliverables

- Admin can create/edit/publish/archive product.
- Admin can create/edit variants and stock.
- Admin can edit AI metadata.
- Admin can view and update orders.
- Admin can issue refund through payment provider.
- Admin can add support note.
- Admin can view audit log.
- Admin can see basic dashboard.

### Acceptance

- Owner can operate catalog and orders without developer intervention.
- Every critical admin action writes an audit log.
- Destructive actions require confirmation.

### Blocking Decisions

- MFA requirement.
- Return policy.
- Admin role/scopes for Phase 1.

---

## 6. Milestone 4 - AI Try-On v1

### Goal

Prove the identity-first shopping experience.

### Scope

- Try-On default landing.
- Photo upload.
- Optional fields.
- Upload safety validation.
- AI job creation.
- SSE progress stream.
- Analyzer.
- CatalogContext adapter.
- Recommender.
- Designer/image generation.
- Generated image storage.
- Try-on results grid.
- Add full look to cart.
- Per-item add.
- Refine prompt.
- Product detail "Try this on you" seed.
- AI quotas, spend ceilings, kill switch.
- Partial failure handling.

### Key Requirements

- `REQ-002` AI-first default.
- `REQ-011` empty upload state.
- `REQ-012` streamed loading.
- `REQ-013` result cards.
- `REQ-014` add full look/per-item add.
- `REQ-015` recommended sizes.
- `REQ-016` refinement.
- `REQ-018` resilient job reconnect.
- `REQ-022` product try-on seed.
- `REQ-052` orchestrator.
- `REQ-053` Analyzer/Recommender/Designer.
- `REQ-054` partial failure.
- `REQ-055` stock awareness.
- `REQ-057` upload rejection.
- `REQ-058` minor detection.
- `REQ-061` AI disclosure.
- `REQ-062` abuse/cost controls.
- `REQ-063` AI outage fallback.

### Deliverables

- User can upload valid photo and start job.
- Invalid/unsafe uploads are rejected with clear guidance.
- Browser sees live progress via SSE.
- Worker runs Analyzer -> Recommender -> Designer.
- Up to 10 cards render with generated images.
- Results can add full look or single item to cart.
- Refine runs without re-uploading/re-analyzing photo.
- AI kill switch disables generation but not catalog/checkout.

### Acceptance

- A full try-on job completes in staging with realistic product data.
- Partial image generation failure still returns usable recommendations.
- Refresh during generation can reconnect or recover gracefully.
- AI-generated image disclosure appears visibly and in alt text.

### Blocking Decisions

- AI provider retention terms.
- Age gate approach.
- Bot protection.
- Email-gate threshold.
- Hesitant-visitor fallback image set.

---

## 7. Milestone 5 - Accounts + Fitting Room

### Goal

Let returning customers continue from previous sessions.

### Scope

- Customer signup/login.
- Password reset.
- Order history.
- Saved addresses.
- Optional saved photo.
- Photo consent/version tracking.
- Fitting Room session list.
- Fitting Room session detail.
- Delete saved photo.
- Delete try-on session.
- Guest-to-account order claim.
- Registered cart merge.

### Key Requirements

- `REQ-005` registered customer.
- `REQ-025` anonymous returning.
- `REQ-026` Fitting Room.
- `REQ-046` guest order claim.
- `REQ-065` saved photo consent.
- `REQ-068` registered image retention.
- `REQ-069` image rights.
- `REQ-100` customer acceptance.

### Deliverables

- Customer can create account and log in.
- Guest can claim order within configured window.
- Registered customer can view order history.
- Registered customer can view and open saved try-on sessions.
- Customer can opt in to saved photo.
- Customer can delete saved photo and sessions.

### Acceptance

- Returning registered user can start new try-on from saved photo.
- Deleting saved photo removes related private media.
- Deleting session removes generated images and related AI profile data.

### Blocking Decisions

- Marketing reuse opt-in copy.
- Saved photo consent wording.

---

## 8. Milestone 6 - MVP Stabilization

### Goal

Prepare the MVP for real user testing.

### Scope

- Bug fixing.
- Accessibility pass.
- Privacy/retention verification.
- Rate limits.
- Spend ceilings.
- Webhook replay tests.
- Inventory race tests.
- Error tracking.
- Admin analytics polish.
- SEO metadata.
- Deployment runbook.
- Backup/restore verification.
- UAT checklist.

### Key Requirements

- `REQ-071` privacy.
- `REQ-072` cost control.
- `REQ-073` performance.
- `REQ-074` reliability.
- `REQ-075` observability.
- `REQ-076` accessibility.
- `REQ-078` security/upload handling.
- `REQ-079` deployment ops.
- `REQ-099` Phase 1 acceptance.
- `REQ-101` admin acceptance.
- `REQ-102` AI acceptance.
- `REQ-103` privacy/ops acceptance.

### Deliverables

- Error tracking active.
- Structured logs active.
- Payment webhook logs inspectable.
- AI job logs inspectable.
- Retention cleanup verified.
- Accessibility issues triaged/fixed.
- SEO basics complete.
- Production-like staging environment.
- Backup/restore tested.
- Runbook created.

### Acceptance

- Owner and small test group can use MVP end-to-end without developer intervention for normal flows.
- Catalog/checkout continue during AI outage.
- Payment webhooks are idempotent.
- Server-side AI rate limits and spend controls are active.
- Anonymous photos/body profiles/generate images expire per policy.

---

## 9. Phase 2 - UAT, Hardening, and Rework

Phase 2 begins after Phase 1 MVP exists end-to-end.

Focus:

- Owner UAT.
- Small shopper test group.
- Checkout/payment edge cases.
- Inventory/shipping edge cases.
- AI expectation-gap review.
- Flow rewrites based on observed confusion.
- Privacy and abuse hardening.
- Technical shortcut cleanup.
- Stronger analytics.
- Returns automation planning.

Phase 2 is not "new features first." It is making the MVP trustworthy enough for real launch.

---

## 10. Open Decision Timing

| Decision | Must be resolved by |
|---|---|
| Launch market + currency | Before Milestone 1 data/config finalization |
| Size chart source | Before Milestone 1 product model implementation |
| Payment provider | Before Milestone 2 checkout |
| Tax approach | Before Milestone 2 checkout |
| Shipping partner/rules | Before Milestone 2 checkout |
| MFA requirement | Before Milestone 3 admin launch |
| Return policy | Before Milestone 3 order operations |
| AI provider retention terms | Before Milestone 4 upload enabled |
| Age gate approach | Before Milestone 4 upload enabled |
| Bot protection | Before Milestone 4 public generation |
| Email-gate threshold | Before Milestone 4 public generation |
| Hesitant visitor fallback set | Before Milestone 4 UI polish |
| Marketing reuse opt-in copy | Before Milestone 5 saved sessions/photo consent |

---

## 11. Tracking Process

Use `requirements-tracker.xlsx` as the source of project status.

Recommended status flow:

```text
Not Started -> Designed -> In Progress -> Built -> Tested -> Accepted
```

Each requirement row should be updated when:

- A document covers it.
- A ticket is created.
- Build starts.
- Build completes.
- Verification passes.
- Owner/UAT acceptance happens.

Required tracker fields during build:

- Status.
- Owner.
- Related spec doc.
- Related ticket.
- Risk level.
- Decision needed.
- Reason/notes.

---

## 12. Milestone Acceptance Criteria

A milestone is complete when:

- Its required tracker rows are at least `Built`.
- Its acceptance criteria are demonstrated.
- New risks/decisions are added to the tracker.
- Docs are updated if implementation changed the plan.
- No critical known blocker remains for the next milestone.

Phase 1 is complete when Milestone 6 acceptance passes and the owner can run the normal store flows without developer intervention.
