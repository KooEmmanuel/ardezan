"""Inventory module — variant stock, soft checkout holds, last-unit handling.

Per ``ARCHITECTURE.md`` §5.3 and ``REQ-040``. Holds are created atomically at
checkout start; on payment success they convert to a stock decrement; on
expiry/release they free the locked units.

No customer-facing router — holds are an internal mechanism used by the
Checkout and Orders modules. Admin stock-adjustment endpoints land in M3.
"""
