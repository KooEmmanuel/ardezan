"""Webhook receivers — Stripe payments, shipping carriers.

Per ``ARCHITECTURE.md`` §5.5 and ``ADR-005``, the Stripe webhook is the *only*
path that creates orders. This isolates revenue-critical state changes from
the browser callback (which the customer might never reach).

References:
- API.md §13 (Webhook API)
- DATA_MODEL.md §8.2 (payment_events collection)
- REQ-043, REQ-074
"""
