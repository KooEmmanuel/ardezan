"""Orders module — order lifecycle, customer reads, refunds.

Orders are created from a successful ``payment_intent.succeeded`` webhook
event (per ARCHITECTURE §5.5, ADR-005). Customer and admin endpoints for
modification land in M3 alongside auth.

References:
- API.md §9 (Orders API)
- DATA_MODEL.md §8.1 (orders collection)
- REQ-047, REQ-049, REQ-074
"""
