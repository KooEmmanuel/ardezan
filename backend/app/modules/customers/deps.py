"""``require_customer`` + ``optional_customer`` FastAPI dependencies.

Customer sessions are signed with ``CUSTOMER_COOKIE_SALT`` so an admin token
can never be reinterpreted as a customer token (and vice versa). The customer
document is re-read on every request so disabling / deleting an account
invalidates every active session immediately.
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import Cookie, Depends, Request

from app.config import get_settings
from app.deps import DbDep
from app.errors import ApiError, ErrorCode
from app.modules.customers.repository import CustomerRepository
from app.security import CUSTOMER_COOKIE_SALT, CUSTOMER_SESSION_TTL, verify_session

CUSTOMER_COOKIE_NAME = "customer_session"


async def require_customer(
    db: DbDep,
    request: Request,
    customer_session: Annotated[
        str | None, Cookie(alias=CUSTOMER_COOKIE_NAME)
    ] = None,
) -> dict[str, Any]:
    if not customer_session:
        raise ApiError(
            ErrorCode.UNAUTHENTICATED, "Please sign in.", http_status=401
        )

    settings = get_settings()
    payload = verify_session(
        customer_session,
        settings.session_secret_customer,
        salt=CUSTOMER_COOKIE_SALT,
        max_age_seconds=CUSTOMER_SESSION_TTL,
    )
    customer_id = payload.get("customer_id") if payload else None
    if not customer_id:
        raise ApiError(
            ErrorCode.UNAUTHENTICATED,
            "Invalid or expired session.",
            http_status=401,
        )

    repo = CustomerRepository(db)
    customer = await repo.find_by_id(customer_id)
    if not customer:
        raise ApiError(
            ErrorCode.UNAUTHENTICATED, "Account is unavailable.", http_status=401
        )

    customer["_request_meta"] = {
        "ip": request.client.host if request.client else None,
        "ua": request.headers.get("user-agent"),
    }
    return customer


async def optional_customer(
    db: DbDep,
    request: Request,
    customer_session: Annotated[
        str | None, Cookie(alias=CUSTOMER_COOKIE_NAME)
    ] = None,
) -> dict[str, Any] | None:
    """Return the current customer if signed in, else ``None``.

    Used by endpoints that work for both anonymous and registered users —
    cart revalidation, product detail, try-on session creation.
    """
    if not customer_session:
        return None
    try:
        return await require_customer(db, request, customer_session)
    except ApiError:
        return None


def ensure_email_verified(customer: dict[str, Any]) -> None:
    """Raise ``EMAIL_NOT_VERIFIED`` (403) if the customer hasn't confirmed
    their email yet.

    Used to gate the trust-sensitive actions a registered customer can take —
    placing an order (order confirmations must reach a real, owned inbox) and
    persisting a photo / body profile (privacy). Browsing and try-on are
    intentionally left open. The error code lets the frontend prompt a resend.
    """
    if not customer.get("email_verified_at"):
        raise ApiError(
            ErrorCode.EMAIL_NOT_VERIFIED,
            "Please verify your email address to continue — check your inbox "
            "for the verification link.",
            http_status=403,
            details={"email": customer.get("email")},
        )


async def require_verified_customer(
    customer: Annotated[dict[str, Any], Depends(require_customer)],
) -> dict[str, Any]:
    """Like ``require_customer`` but also requires a verified email."""
    ensure_email_verified(customer)
    return customer


CustomerDep = Annotated[dict[str, Any], Depends(require_customer)]
OptionalCustomerDep = Annotated[
    "dict[str, Any] | None", Depends(optional_customer)
]
VerifiedCustomerDep = Annotated[dict[str, Any], Depends(require_verified_customer)]
