"""Customers module — auth, account, server-side cart, Fitting Room.

Per DATA_MODEL §6.1 and SPECS §5.2. Reuses ``app/security.py`` primitives
(Argon2 + signed session cookies) — admin and customer sessions are
isolated by audience-specific cookie salts so a leak of one secret never
authenticates as the other.

M5 sub-milestones:
- M5.1 (this turn): signup, login, logout, /me, require_customer dep
- M5.2: server-side cart (CRUD + merge)
- M5.3: customer-facing orders (list, get, cancel, edit address, claim)
- M5.4: Fitting Room (try-on session list, saved-photo opt-in)
"""
