"""Transactional email — SMTP-driven, async, queue-friendly.

References:
- API.md §13 (Email service is a tool used by other modules; no public routes)
- DATA_MODEL.md — emails are not persisted in Phase 1; provider keeps the log
- REQ-046, REQ-092, REQ-074
"""
