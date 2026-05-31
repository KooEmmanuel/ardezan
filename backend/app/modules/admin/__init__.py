"""Admin module — M3 Admin Operations.

Per ARCHITECTURE.md §4.2 and §5.8 and REQ-051. Owns:
- Admin auth (login, logout, session cookie, future MFA)
- Product / variant / size chart CRUD (M3.2)
- Order management and refunds (M3.3)
- Audit log writes for critical actions
- AI controls (kill switch, spend ceilings) (M3.4)
- Basic analytics (M3.5)

This file scaffolds the module; concrete CRUD lives in sibling files.
"""
