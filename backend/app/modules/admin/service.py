"""Admin login + audit orchestration.

Login is deliberately strict:
- Same generic error for "wrong email" and "wrong password" (no account
  enumeration).
- Disabled accounts can't sign in.
- ``last_login_at`` updated atomically on success.
- An ``admin.login`` audit row is written on every successful login;
  ``admin.login_failed`` on every failed attempt.

Password rehash on login is checked — if Argon2 parameters have been
upgraded since the user's last login, we transparently re-hash.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.errors import ApiError, ErrorCode
from app.logging_setup import get_logger
from app.modules.admin.repository import AdminRepository
from app.security import (
    equalize_login_timing,
    hash_password,
    needs_rehash,
    verify_password,
)

log = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _admin_id() -> str:
    return f"admin_{secrets.token_hex(8)}"


_INVALID_CREDS_MESSAGE = "Email or password is incorrect."


class AdminService:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self.db = db
        self.repo = AdminRepository(db)

    # ── Authentication ─────────────────────────────────────────
    async def login(
        self,
        email: str,
        password: str,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        email_normalized = email.lower().strip()
        admin = await self.repo.find_by_email(email_normalized)

        if admin is None or admin.get("status") != "active":
            # Same error path so attackers can't tell which case fired.
            # Keep timing constant so a missing account can't be distinguished
            # from a disabled one (or a wrong password) by response latency.
            equalize_login_timing()
            await self.repo.write_audit(
                actor_id=None,
                action="admin.login_failed",
                target_type="admin",
                target_id=None,
                after={"email_attempted": email_normalized, "reason": "no_active_account"},
                ip_address=ip_address,
                user_agent=user_agent,
            )
            raise ApiError(
                ErrorCode.UNAUTHENTICATED, _INVALID_CREDS_MESSAGE, http_status=401
            )

        if not verify_password(password, admin["password_hash"]):
            await self.repo.write_audit(
                actor_id=admin["admin_id"],
                action="admin.login_failed",
                target_type="admin",
                target_id=admin["admin_id"],
                after={"reason": "bad_password"},
                ip_address=ip_address,
                user_agent=user_agent,
            )
            raise ApiError(
                ErrorCode.UNAUTHENTICATED, _INVALID_CREDS_MESSAGE, http_status=401
            )

        # Rehash on login if argon2 parameters were upgraded.
        if needs_rehash(admin["password_hash"]):
            new_hash = hash_password(password)
            await self.db[self.repo.admins.name].update_one(
                {"admin_id": admin["admin_id"]},
                {"$set": {"password_hash": new_hash, "updated_at": _now()}},
            )
            log.info("admin.password_rehashed", admin_id=admin["admin_id"])

        await self.repo.update_last_login(admin["admin_id"])
        await self.repo.write_audit(
            actor_id=admin["admin_id"],
            action="admin.login",
            target_type="admin",
            target_id=admin["admin_id"],
            ip_address=ip_address,
            user_agent=user_agent,
        )
        log.info(
            "admin.login_succeeded",
            admin_id=admin["admin_id"],
            role=admin.get("role"),
        )
        return admin

    async def logout(
        self,
        admin_id: str,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        await self.repo.write_audit(
            actor_id=admin_id,
            action="admin.logout",
            target_type="admin",
            target_id=admin_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    # ── Bootstrap (dev / first deploy) ─────────────────────────
    async def create_owner_if_missing(
        self,
        *,
        email: str,
        password: str,
        name: str = "Owner",
    ) -> tuple[dict[str, Any], bool]:
        """Idempotently create the initial owner admin.

        Returns ``(admin_doc, created_now)`` — ``created_now`` is False if an
        admin with this email already existed.
        """
        existing = await self.repo.find_by_email(email)
        if existing is not None:
            return existing, False

        now = _now()
        admin_id = _admin_id()
        doc: dict[str, Any] = {
            "admin_id": admin_id,
            "email": email.lower(),
            "name": name,
            "password_hash": hash_password(password),
            "role": "owner",
            "scopes": ["*"],
            "mfa": {"enabled": False, "method": None, "enrolled_at": None},
            "status": "active",
            "last_login_at": None,
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        await self.repo.insert(doc)
        await self.repo.write_audit(
            actor_id=None,
            action="admin.bootstrap_owner",
            target_type="admin",
            target_id=admin_id,
            after={"email": email.lower(), "role": "owner"},
        )
        log.info("admin.bootstrap_owner", admin_id=admin_id, email=email)
        return doc, True
