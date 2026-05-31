"""Signed tokens for email verification + password reset (M6.4).

Reuses ``guest_token_secret`` with distinct salts so a verification token
cannot be replayed as a reset token (and vice versa). Same itsdangerous
serializer pattern as session cookies, just different lifetimes.

Verification is idempotent so we don't need an anti-replay nonce — the
``email_verified_at`` field acts as the once-set flag.

Password reset *does* need anti-replay (attacker shoulder-surfing a
reset link could overwrite the legit user's new password). The token's
SHA-256 is stored on ``customers.password_reset.token_hash`` when issued
and cleared on consumption — confirm rejects when the hash doesn't match.
"""
from __future__ import annotations

import hashlib
from typing import Any

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import get_settings

EMAIL_VERIFY_SALT = "atelier-email-verify-v1"
PASSWORD_RESET_SALT = "atelier-password-reset-v1"

EMAIL_VERIFY_TTL_SECONDS = 60 * 60 * 24   # 24h — generous, matches mailbox latency.
PASSWORD_RESET_TTL_SECONDS = 60 * 60      # 1h — short, reset is high-impact.


def _serializer(salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().guest_token_secret, salt=salt)


# ── Email verification ─────────────────────────────────────────────
def sign_email_verification(
    *, customer_id: str, email: str
) -> str:
    """Sign a verify-email token. Embedded payload includes the email so a
    later change of email invalidates outstanding tokens."""
    return _serializer(EMAIL_VERIFY_SALT).dumps(
        {"customer_id": customer_id, "email": email.lower().strip()}
    )


def verify_email_verification(token: str) -> dict[str, Any] | None:
    """Return the payload if valid, else ``None``."""
    try:
        data = _serializer(EMAIL_VERIFY_SALT).loads(
            token, max_age=EMAIL_VERIFY_TTL_SECONDS
        )
    except (BadSignature, SignatureExpired):
        return None
    return data if isinstance(data, dict) else None


# ── Password reset ──────────────────────────────────────────────────
def sign_password_reset(*, customer_id: str) -> str:
    """Sign a reset token. The caller stores ``hash_token(token)`` on the
    customer doc; ``confirm`` matches the presented token's hash to prevent
    replay after a successful reset."""
    return _serializer(PASSWORD_RESET_SALT).dumps({"customer_id": customer_id})


def verify_password_reset(token: str) -> dict[str, Any] | None:
    try:
        data = _serializer(PASSWORD_RESET_SALT).loads(
            token, max_age=PASSWORD_RESET_TTL_SECONDS
        )
    except (BadSignature, SignatureExpired):
        return None
    return data if isinstance(data, dict) else None


def hash_token(token: str) -> str:
    """Stable SHA-256 hex digest — used to store reset tokens so a DB leak
    doesn't expose live reset capability."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


__all__ = [
    "EMAIL_VERIFY_TTL_SECONDS",
    "PASSWORD_RESET_TTL_SECONDS",
    "sign_email_verification",
    "verify_email_verification",
    "sign_password_reset",
    "verify_password_reset",
    "hash_token",
]
