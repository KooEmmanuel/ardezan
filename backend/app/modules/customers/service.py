"""Customer auth business logic — signup, login, profile updates.

The ``customer_session`` cookie is signed with the customer-audience salt
from ``app/security.py`` so an admin token cookie can't authenticate as a
customer (and vice versa).

Failed logins share the same generic error message as successful-but-disabled
attempts to avoid account enumeration. Argon2 parameters are upgraded
transparently on next login via ``needs_rehash``.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from app.db import C
from app.errors import ApiError, ErrorCode
from app.logging_setup import get_logger
from app.modules.customers.repository import CustomerRepository
from app.modules.customers.tokens import (
    PASSWORD_RESET_TTL_SECONDS,
    hash_token,
    sign_email_verification,
    sign_password_reset,
    verify_email_verification,
    verify_password_reset,
)
from app.queue import get_queue
from app.security import (
    equalize_login_timing,
    hash_password,
    needs_rehash,
    verify_password,
)

log = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _customer_id() -> str:
    return f"cust_{secrets.token_hex(8)}"


_INVALID_CREDS_MESSAGE = "Email or password is incorrect."


class CustomerService:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self.db = db
        self.repo = CustomerRepository(db)

    # ── Anonymous-to-customer claim ────────────────────────────
    async def claim_anonymous_sessions(
        self,
        *,
        customer_id: str,
        anonymous_session_id: str | None,
    ) -> dict[str, int]:
        """Re-key any design / try-on / job rows under ``anonymous_session_id``
        so the new customer sees them in their activity hub.

        Best-effort: a Mongo hiccup here shouldn't fail signup or login.
        Only rows still flagged anonymous (``customer_id == None``) are
        touched — we never overwrite a row that already belongs to
        someone else.
        """
        if not anonymous_session_id:
            return {"designs": 0, "try_ons": 0, "jobs": 0}

        now = _now()
        criteria = {
            "anonymous_session_id": anonymous_session_id,
            "customer_id": None,
        }
        update = {"$set": {"customer_id": customer_id, "updated_at": now}}

        designs = 0
        try_ons = 0
        jobs = 0
        try:
            r = await self.db[C.design_sessions].update_many(criteria, update)
            designs = r.modified_count
        except Exception as exc:  # noqa: BLE001
            log.warning("claim.designs_failed", error=str(exc))
        try:
            r = await self.db[C.try_on_sessions].update_many(criteria, update)
            try_ons = r.modified_count
        except Exception as exc:  # noqa: BLE001
            log.warning("claim.try_ons_failed", error=str(exc))
        try:
            # ai_jobs uses ``updated_at`` too, same shape. Worth claiming
            # so the cost / audit history follows the customer.
            r = await self.db[C.ai_jobs].update_many(criteria, update)
            jobs = r.modified_count
        except Exception as exc:  # noqa: BLE001
            log.warning("claim.jobs_failed", error=str(exc))

        log.info(
            "claim.completed",
            customer_id=customer_id,
            anonymous_session_id=anonymous_session_id,
            designs=designs,
            try_ons=try_ons,
            jobs=jobs,
        )
        return {"designs": designs, "try_ons": try_ons, "jobs": jobs}

    # ── Signup ─────────────────────────────────────────────────
    async def signup(
        self,
        *,
        email: str,
        password: str,
        name: str,
        accepts_marketing: bool = False,
    ) -> dict[str, Any]:
        email_normalized = email.lower().strip()
        now = _now()
        customer_id = _customer_id()
        doc: dict[str, Any] = {
            "customer_id": customer_id,
            "email": email_normalized,
            "email_verified_at": None,
            "name": name,
            "phone": None,
            "password_hash": hash_password(password),
            "auth_provider": "password",
            "addresses": [],
            "saved_photo": {
                "media_asset_id": None,
                "opted_in": False,
                "photo_uploaded_at": None,
                "photo_consent_version": None,
            },
            "body_profile": {
                "opted_in": False,
                "source_try_on_session_id": None,
                "measurements_estimate": None,
                "fit_preference": None,
                "style_preferences": [],
                "updated_at": None,
            },
            "quotas": {
                "try_on_weekly_limit": None,
                "try_on_used_this_week": 0,
                "quota_window_starts_at": now,
            },
            "accepts_marketing": accepts_marketing,
            "last_login_at": now,
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        try:
            await self.repo.insert(doc)
        except DuplicateKeyError as exc:
            raise ApiError(
                ErrorCode.CONFLICT,
                "An account already exists for that email.",
                http_status=409,
            ) from exc
        log.info(
            "customer.signup",
            customer_id=customer_id,
            email=email_normalized,
            accepts_marketing=accepts_marketing,
        )

        # Kick off email verification asynchronously. Best-effort: a queue
        # outage shouldn't fail signup — the customer can ask to resend.
        try:
            await self.request_email_verification(customer_id)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "customer.signup_verify_enqueue_failed",
                customer_id=customer_id,
                error=str(exc),
            )

        return doc

    # ── Login ──────────────────────────────────────────────────
    async def login(self, email: str, password: str) -> dict[str, Any]:
        email_normalized = email.lower().strip()
        customer = await self.repo.find_by_email(email_normalized)
        if customer is None:
            # Keep timing constant with the wrong-password path so response
            # latency doesn't reveal whether the email has an account.
            equalize_login_timing()
            log.info("customer.login_failed", reason="no_account", email=email_normalized)
            raise ApiError(
                ErrorCode.UNAUTHENTICATED, _INVALID_CREDS_MESSAGE, http_status=401
            )
        if not verify_password(password, customer["password_hash"]):
            log.info(
                "customer.login_failed",
                reason="bad_password",
                customer_id=customer["customer_id"],
            )
            raise ApiError(
                ErrorCode.UNAUTHENTICATED, _INVALID_CREDS_MESSAGE, http_status=401
            )

        # Transparent rehash if argon2 parameters were upgraded.
        if needs_rehash(customer["password_hash"]):
            await self.repo.update_password_hash(
                customer["customer_id"], hash_password(password)
            )
            log.info("customer.password_rehashed", customer_id=customer["customer_id"])

        await self.repo.update_last_login(customer["customer_id"])
        log.info("customer.login_succeeded", customer_id=customer["customer_id"])
        return customer

    # ── Email verification (M6.4) ──────────────────────────────
    async def request_email_verification(self, customer_id: str) -> dict[str, Any]:
        """Generate a fresh verify-email token + enqueue the send job.

        Idempotent: if the customer's email is already verified, returns a
        no-op result instead of mailing a useless link.
        """
        customer = await self.repo.find_by_id(customer_id)
        if not customer:
            raise ApiError(
                ErrorCode.NOT_FOUND, "Customer not found.", http_status=404
            )
        if customer.get("email_verified_at"):
            return {"queued": False, "reason": "already_verified"}

        token = sign_email_verification(
            customer_id=customer_id, email=customer["email"]
        )
        try:
            queue = get_queue()
            await queue.enqueue_job(
                "send_email_verification",
                to=customer["email"],
                name=customer.get("name") or "",
                token=token,
            )
        except RuntimeError as exc:
            # Queue not initialised (e.g. boot smoke test) — log + swallow.
            log.warning("customer.verify_enqueue_failed", error=str(exc))
        log.info("customer.verify_requested", customer_id=customer_id)
        return {"queued": True}

    async def confirm_email_verification(self, token: str) -> dict[str, Any]:
        payload = verify_email_verification(token)
        if not payload:
            raise ApiError(
                ErrorCode.UNAUTHENTICATED,
                "Verification link is invalid or has expired.",
                http_status=400,
            )
        customer_id = str(payload.get("customer_id") or "")
        token_email = str(payload.get("email") or "")
        customer = await self.repo.find_by_id(customer_id)
        if not customer or customer["email"] != token_email:
            # Email changed since the token was issued — invalidate.
            raise ApiError(
                ErrorCode.UNAUTHENTICATED,
                "Verification link is no longer valid.",
                http_status=400,
            )

        if customer.get("email_verified_at"):
            return {"verified": True, "already": True}

        updated = await self.repo.mark_email_verified(customer_id)
        log.info("customer.email_verified", customer_id=customer_id)
        return {"verified": True, "already": False, "customer_id": customer_id,
                "verified_at": (updated or {}).get("email_verified_at")}

    # ── Password reset (M6.4) ──────────────────────────────────
    async def request_password_reset(self, email: str) -> None:
        """Always returns None — caller maps to 204 regardless of whether the
        email exists. Prevents account-existence enumeration.
        """
        normalized = email.lower().strip()
        customer = await self.repo.find_by_email(normalized)
        if not customer:
            log.info("customer.reset_requested_unknown_email", email=normalized)
            return

        token = sign_password_reset(customer_id=customer["customer_id"])
        expires_at = _now() + timedelta(seconds=PASSWORD_RESET_TTL_SECONDS)
        await self.repo.set_password_reset(
            customer["customer_id"],
            token_hash=hash_token(token),
            expires_at=expires_at,
        )
        try:
            queue = get_queue()
            await queue.enqueue_job(
                "send_password_reset",
                to=customer["email"],
                name=customer.get("name") or "",
                token=token,
            )
        except RuntimeError as exc:
            log.warning("customer.reset_enqueue_failed", error=str(exc))
        log.info("customer.reset_requested", customer_id=customer["customer_id"])

    async def confirm_password_reset(
        self, token: str, new_password: str
    ) -> dict[str, Any]:
        payload = verify_password_reset(token)
        if not payload:
            raise ApiError(
                ErrorCode.UNAUTHENTICATED,
                "Reset link is invalid or has expired.",
                http_status=400,
            )

        customer_id = str(payload.get("customer_id") or "")
        customer = await self.repo.find_by_id(customer_id)
        if not customer:
            raise ApiError(
                ErrorCode.UNAUTHENTICATED,
                "Reset link is no longer valid.",
                http_status=400,
            )

        # Anti-replay: the hash of the presented token must match what we
        # recorded on issue. Cleared when consumed, so a second click fails.
        stored = (customer.get("password_reset") or {}).get("token_hash")
        if not stored or stored != hash_token(token):
            raise ApiError(
                ErrorCode.UNAUTHENTICATED,
                "Reset link has already been used.",
                http_status=400,
            )

        await self.repo.consume_password_reset(
            customer_id, new_hash=hash_password(new_password)
        )
        log.info("customer.password_reset", customer_id=customer_id)
        return {"reset": True, "customer_id": customer_id}

    # ── Profile ────────────────────────────────────────────────
    async def update_profile(
        self,
        customer_id: str,
        fields: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not fields:
            return await self.repo.find_by_id(customer_id)
        return await self.repo.update_profile(customer_id, fields)
