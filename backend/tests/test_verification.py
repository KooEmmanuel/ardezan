"""Email-verification gate tests.

The balanced policy: browsing/try-on stay open, but a registered customer
must have a verified email before placing an order or saving a photo /
body profile. ``ensure_email_verified`` is the shared guard behind both the
checkout (logged-in) path and the saved-photo / body-profile opt-ins.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.errors import ApiError, ErrorCode
from app.modules.customers.deps import ensure_email_verified


def test_unverified_customer_is_blocked() -> None:
    with pytest.raises(ApiError) as exc_info:
        ensure_email_verified({"email": "shopper@example.com", "email_verified_at": None})
    err = exc_info.value
    assert err.code == ErrorCode.EMAIL_NOT_VERIFIED
    assert err.http_status == 403
    # The email is echoed back so the frontend can offer a one-click resend.
    assert err.details.get("email") == "shopper@example.com"


def test_missing_verified_field_is_blocked() -> None:
    # A customer doc with no verification field at all must fail closed.
    with pytest.raises(ApiError) as exc_info:
        ensure_email_verified({"email": "shopper@example.com"})
    assert exc_info.value.code == ErrorCode.EMAIL_NOT_VERIFIED


def test_verified_customer_passes() -> None:
    # A set timestamp means verified — must not raise.
    ensure_email_verified(
        {"email": "shopper@example.com", "email_verified_at": datetime.now(UTC)}
    )
