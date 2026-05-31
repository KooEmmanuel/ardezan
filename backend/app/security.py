"""Auth primitives shared by admin (M3) and customer (M5) sessions.

Two concerns live here:

1. **Password hashing** via Argon2id (the OWASP-recommended scheme).
2. **Signed session cookies** via ``itsdangerous`` — separate per audience
   (admin vs customer) by using distinct ``salt`` strings, so a customer
   session token never authenticates as admin even if both secrets leaked.

Cookie payloads are kept tiny: just the user id and role. We re-read the
user document on every request to enforce ``status=active`` and pick up
permission changes immediately.
"""
from __future__ import annotations

from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

# Argon2id with the library's secure defaults (memory_cost=64MB, time_cost=3,
# parallelism=4). Tune in M6 if hot paths show contention.
_HASHER = PasswordHasher()

# Precomputed decoy hash used to equalize login timing. When a login attempt
# names an email that has no account, we still run a verify against this hash
# so the response latency matches the "account exists, wrong password" path —
# otherwise an attacker could enumerate accounts by timing.
_TIMING_EQUALIZATION_HASH = _HASHER.hash("timing-equalization-placeholder")

# Salts namespace cookies by audience. Changing a salt invalidates every
# session in that audience — useful as a kill switch in an incident.
ADMIN_COOKIE_SALT = "atelier-admin-session-v1"
CUSTOMER_COOKIE_SALT = "atelier-customer-session-v1"

# Default session lifetimes (seconds). Externalised to config later if needed.
ADMIN_SESSION_TTL = 60 * 60 * 12       # 12 hours
CUSTOMER_SESSION_TTL = 60 * 60 * 24 * 30   # 30 days


# ── Passwords ───────────────────────────────────────────────────────
def hash_password(plain: str) -> str:
    """Return an Argon2id hash for ``plain``. Includes salt + parameters."""
    return _HASHER.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time verification. Returns False on any mismatch / bad hash."""
    try:
        _HASHER.verify(hashed, plain)
        return True
    except (VerifyMismatchError, InvalidHashError):
        return False
    except Exception:
        return False


def needs_rehash(hashed: str) -> bool:
    """True if the hash uses outdated parameters and should be re-hashed on
    next successful login. Cheap to check."""
    return _HASHER.check_needs_rehash(hashed)


def equalize_login_timing() -> None:
    """Run a decoy Argon2 verify to keep login response time constant.

    Call this on the "no such account" branch of a login flow so it costs
    roughly the same wall-clock time as verifying a real password. Without it,
    a missing-account response returns faster than a wrong-password one, which
    lets an attacker enumerate registered emails by timing. Never raises — the
    mismatch against the decoy hash is expected and swallowed.
    """
    try:
        _HASHER.verify(_TIMING_EQUALIZATION_HASH, "wrong-password")
    except Exception:
        pass


# ── Session cookies ─────────────────────────────────────────────────
def sign_session(payload: dict[str, Any], secret: str, *, salt: str) -> str:
    """Sign a small payload with the audience-specific salt."""
    serializer = URLSafeTimedSerializer(secret, salt=salt)
    return serializer.dumps(payload)


def verify_session(
    token: str,
    secret: str,
    *,
    salt: str,
    max_age_seconds: int,
) -> dict[str, Any] | None:
    """Verify signature + expiry. Returns the payload dict or ``None``."""
    serializer = URLSafeTimedSerializer(secret, salt=salt)
    try:
        data = serializer.loads(token, max_age=max_age_seconds)
    except (BadSignature, SignatureExpired):
        return None
    return data if isinstance(data, dict) else None
