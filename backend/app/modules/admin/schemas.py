"""Admin module schemas.

Mirrors ``DATA_MODEL.md`` §6.2 (admin_users) and §10.1 (audit_logs).
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

AdminRole = Literal["owner", "operations", "support"]
AdminStatus = Literal["active", "disabled"]


# ── Requests ────────────────────────────────────────────────────────
class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=200)


# ── Response shapes ─────────────────────────────────────────────────
class AdminPublic(BaseModel):
    """What ``/admin/me`` returns. Never exposes the password hash."""

    admin_id: str
    email: str
    name: str
    role: AdminRole
    scopes: list[str] = Field(default_factory=list)
    status: AdminStatus = "active"
    last_login_at: datetime | None = None
    mfa_enabled: bool = False


class AdminLoginResponse(BaseModel):
    admin: AdminPublic
    expires_at: datetime


# ── Audit log shape ─────────────────────────────────────────────────
class AuditLogEntry(BaseModel):
    audit_log_id: str
    actor_type: Literal["admin", "system", "customer"]
    actor_id: str | None
    action: str
    target_type: str | None = None
    target_id: str | None = None
    before_summary: dict | None = None
    after_summary: dict | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime
