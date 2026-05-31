"""Customer auth + account routes (per API.md §5.1)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.config import get_settings
from app.deps import DbDep
from app.modules.customers.deps import (
    CUSTOMER_COOKIE_NAME,
    CustomerDep,
)
from app.modules.customers.schemas import (
    CustomerLoginRequest,
    CustomerLoginResponse,
    CustomerPublic,
    CustomerSignupRequest,
    CustomerUpdateRequest,
    EmailVerificationConfirmRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
)
from app.modules.customers.service import CustomerService
from app.rate_limit import (
    enforce_login_email,
    enforce_password_reset_email,
    rate_limit_login,
    rate_limit_password_reset,
)
from app.security import CUSTOMER_COOKIE_SALT, CUSTOMER_SESSION_TTL, sign_session

router = APIRouter()


def get_service(db: DbDep) -> CustomerService:
    return CustomerService(db)


ServiceDep = Annotated[CustomerService, Depends(get_service)]


def _customer_public(doc: dict) -> CustomerPublic:
    return CustomerPublic(
        customer_id=doc["customer_id"],
        email=doc["email"],
        name=doc.get("name", ""),
        email_verified_at=doc.get("email_verified_at"),
        addresses=doc.get("addresses", []),
        has_saved_photo=bool(
            (doc.get("saved_photo") or {}).get("opted_in", False)
            and (doc.get("saved_photo") or {}).get("media_asset_id")
        ),
        body_profile_opted_in=bool(
            (doc.get("body_profile") or {}).get("opted_in", False)
        ),
        last_login_at=doc.get("last_login_at"),
        created_at=doc["created_at"],
    )


def _set_customer_cookie(response: Response, customer_id: str) -> datetime:
    settings = get_settings()
    token = sign_session(
        {"customer_id": customer_id},
        settings.session_secret_customer,
        salt=CUSTOMER_COOKIE_SALT,
    )
    response.set_cookie(
        key=CUSTOMER_COOKIE_NAME,
        value=token,
        max_age=CUSTOMER_SESSION_TTL,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
        path="/",
    )
    return datetime.now(timezone.utc) + timedelta(seconds=CUSTOMER_SESSION_TTL)


# ── Auth ────────────────────────────────────────────────────────────
@router.post(
    "/auth/signup",
    response_model=CustomerLoginResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account and sign in (sets customer_session cookie)",
)
async def customer_signup(
    body: CustomerSignupRequest,
    response: Response,
    service: ServiceDep,
) -> CustomerLoginResponse:
    customer = await service.signup(
        email=body.email,
        password=body.password,
        name=body.name,
        accepts_marketing=body.accepts_marketing,
    )
    # Pull in any design / try-on sessions they created before signing
    # up so the activity hub isn't empty on first visit.
    await service.claim_anonymous_sessions(
        customer_id=customer["customer_id"],
        anonymous_session_id=body.anonymous_session_id,
    )
    expires_at = _set_customer_cookie(response, customer["customer_id"])
    return CustomerLoginResponse(
        customer=_customer_public(customer), expires_at=expires_at
    )


@router.post(
    "/auth/login",
    response_model=CustomerLoginResponse,
    summary="Sign in — sets customer_session cookie",
    dependencies=[Depends(rate_limit_login)],
)
async def customer_login(
    body: CustomerLoginRequest,
    request: Request,
    response: Response,
    service: ServiceDep,
) -> CustomerLoginResponse:
    # Second pass: per-email bucket so one account can't be sprayed via many IPs.
    await enforce_login_email(request, body.email)
    customer = await service.login(body.email, body.password)
    # Same as signup: if they did anything anonymously in this browser
    # before logging in, fold it into their account.
    await service.claim_anonymous_sessions(
        customer_id=customer["customer_id"],
        anonymous_session_id=body.anonymous_session_id,
    )
    expires_at = _set_customer_cookie(response, customer["customer_id"])
    return CustomerLoginResponse(
        customer=_customer_public(customer), expires_at=expires_at
    )


@router.post(
    "/auth/logout",
    summary="Clear the customer_session cookie",
)
async def customer_logout(
    response: Response,
    customer: CustomerDep,
) -> dict[str, str]:
    response.delete_cookie(CUSTOMER_COOKIE_NAME, path="/")
    return {"status": "ok"}


# ── Email verification (M6.4) ───────────────────────────────────────
@router.post(
    "/auth/verify-email/request",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Resend the email-verification link to the signed-in customer",
)
async def request_email_verification(
    customer: CustomerDep,
    service: ServiceDep,
) -> dict[str, object]:
    return await service.request_email_verification(customer["customer_id"])


@router.post(
    "/auth/verify-email/confirm",
    summary="Confirm an email-verification token (called by the frontend page)",
)
async def confirm_email_verification(
    body: EmailVerificationConfirmRequest,
    service: ServiceDep,
) -> dict[str, object]:
    return await service.confirm_email_verification(body.token)


# ── Password reset (M6.4) ───────────────────────────────────────────
@router.post(
    "/auth/password-reset",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Request a password-reset link (always 204 — no enumeration)",
    dependencies=[Depends(rate_limit_password_reset)],
)
async def request_password_reset(
    body: PasswordResetRequest,
    request: Request,
    service: ServiceDep,
) -> Response:
    # Second pass: per-email bucket so a single attacker can't burn an
    # account's quota across many IPs.
    await enforce_password_reset_email(request, body.email)
    await service.request_password_reset(body.email)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/auth/password-reset/confirm",
    summary="Consume a reset token and set a new password",
)
async def confirm_password_reset(
    body: PasswordResetConfirmRequest,
    service: ServiceDep,
) -> dict[str, object]:
    return await service.confirm_password_reset(body.token, body.new_password)


# ── Account ─────────────────────────────────────────────────────────
@router.get(
    "/account/me",
    response_model=CustomerPublic,
    summary="Current customer profile",
)
async def get_me(customer: CustomerDep) -> CustomerPublic:
    return _customer_public(customer)


@router.patch(
    "/account/me",
    response_model=CustomerPublic,
    summary="Update name / marketing-consent preferences",
)
async def update_me(
    body: CustomerUpdateRequest,
    service: ServiceDep,
    customer: CustomerDep,
) -> CustomerPublic:
    fields = body.model_dump(exclude_unset=True)
    updated = await service.update_profile(customer["customer_id"], fields)
    return _customer_public(updated or customer)
