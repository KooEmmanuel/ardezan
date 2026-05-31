"""Checkout module — checkout sessions, totals, and Stripe PaymentIntent creation.

Wires together cart revalidation, inventory reservation, and the payment
provider. The order is **not** created here — order creation happens in the
Stripe webhook handler after ``payment_intent.succeeded`` (per ARCHITECTURE
§5.5, ADR-005, REQ-074).

References:
- API.md §8 (Checkout API)
- ARCHITECTURE.md §5.5, §9.2
- REQ-040 (atomic holds), REQ-042 (checkout), REQ-043 (idempotent webhooks)
"""
