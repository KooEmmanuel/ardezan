"""Auth primitive tests — password hashing, session cookies, signed tokens.

These are pure-function tests (no DB). They protect the security-critical
invariants: passwords verify only against their own hash, a session token
signed for one audience never validates for another, expiry is enforced,
and email-verify vs password-reset tokens are not interchangeable.
"""
from __future__ import annotations

import time

from app import security
from app.modules.customers import tokens


# ── Passwords ───────────────────────────────────────────────────────
def test_password_hash_roundtrip() -> None:
    hashed = security.hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"  # never stored in clear
    assert security.verify_password("correct horse battery staple", hashed) is True


def test_password_wrong_rejected() -> None:
    hashed = security.hash_password("s3cret-value")
    assert security.verify_password("not-the-password", hashed) is False


def test_password_verify_handles_garbage_hash() -> None:
    # A malformed stored hash must fail closed, not raise.
    assert security.verify_password("anything", "not-a-real-argon2-hash") is False


def test_password_hashes_are_salted() -> None:
    # Same input, different hashes — confirms a random salt per hash.
    a = security.hash_password("same-input")
    b = security.hash_password("same-input")
    assert a != b


def test_equalize_login_timing_never_raises() -> None:
    # Used on the "no such account" login branch to keep timing constant — it
    # must always return cleanly (the mismatch against the decoy hash is
    # expected and swallowed).
    assert security.equalize_login_timing() is None


# ── Session cookies ─────────────────────────────────────────────────
def test_session_roundtrip() -> None:
    token = security.sign_session(
        {"admin_id": "adm_1", "role": "owner"},
        "secret-A",
        salt=security.ADMIN_COOKIE_SALT,
    )
    payload = security.verify_session(
        token, "secret-A", salt=security.ADMIN_COOKIE_SALT, max_age_seconds=3600
    )
    assert payload == {"admin_id": "adm_1", "role": "owner"}


def test_session_wrong_secret_rejected() -> None:
    token = security.sign_session(
        {"admin_id": "adm_1"}, "secret-A", salt=security.ADMIN_COOKIE_SALT
    )
    assert (
        security.verify_session(
            token, "different-secret", salt=security.ADMIN_COOKIE_SALT, max_age_seconds=3600
        )
        is None
    )


def test_session_cross_audience_rejected() -> None:
    # A customer-salted token must not validate as an admin token, even with
    # the same secret. This is the privilege-separation guarantee.
    token = security.sign_session(
        {"customer_id": "cus_1"}, "shared-secret", salt=security.CUSTOMER_COOKIE_SALT
    )
    assert (
        security.verify_session(
            token, "shared-secret", salt=security.ADMIN_COOKIE_SALT, max_age_seconds=3600
        )
        is None
    )


def test_session_expiry_enforced() -> None:
    token = security.sign_session(
        {"admin_id": "adm_1"}, "secret-A", salt=security.ADMIN_COOKIE_SALT
    )
    # itsdangerous timestamps have whole-second resolution; sleep past the
    # boundary so age is unambiguously > max_age.
    time.sleep(2.1)
    assert (
        security.verify_session(
            token, "secret-A", salt=security.ADMIN_COOKIE_SALT, max_age_seconds=1
        )
        is None
    )


# ── Signed email/reset tokens ───────────────────────────────────────
def test_email_verification_roundtrip() -> None:
    token = tokens.sign_email_verification(customer_id="cus_1", email="A@Example.com ")
    payload = tokens.verify_email_verification(token)
    assert payload is not None
    assert payload["customer_id"] == "cus_1"
    # Email is normalised (lowercased + trimmed) at signing time.
    assert payload["email"] == "a@example.com"


def test_password_reset_roundtrip() -> None:
    token = tokens.sign_password_reset(customer_id="cus_1")
    payload = tokens.verify_password_reset(token)
    assert payload is not None
    assert payload["customer_id"] == "cus_1"


def test_verify_and_reset_tokens_not_interchangeable() -> None:
    # An email-verification token must not be accepted by the reset verifier
    # (and vice versa), because they use distinct salts.
    verify_token = tokens.sign_email_verification(customer_id="cus_1", email="a@b.com")
    reset_token = tokens.sign_password_reset(customer_id="cus_1")
    assert tokens.verify_password_reset(verify_token) is None
    assert tokens.verify_email_verification(reset_token) is None


def test_reset_token_hash_is_stable_and_opaque() -> None:
    token = tokens.sign_password_reset(customer_id="cus_1")
    h1 = tokens.hash_token(token)
    h2 = tokens.hash_token(token)
    assert h1 == h2  # stable — lets us match a presented token to stored hash
    assert h1 != token  # opaque — a DB leak doesn't expose the live token
    assert len(h1) == 64  # SHA-256 hex digest
