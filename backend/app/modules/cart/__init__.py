"""Cart module — anonymous cart revalidation + try-on full-look add.

Per SPECS §5.2: anonymous carts live in browser ``localStorage``; the backend
provides stateless revalidation so the frontend can detect stale prices, low
stock, or removed items before checkout.

Server-side carts for registered customers (collection ``carts``) are scaffolded
in the schema but their CRUD endpoints land in M5 alongside auth.

References:
- API.md §7 (Cart API)
- DATA_MODEL.md §7.1 (carts collection)
- ARCHITECTURE.md §5.4 (cart rules)
- REQ-044, REQ-045, REQ-055
"""
