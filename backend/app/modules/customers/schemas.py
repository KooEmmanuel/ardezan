"""Customer schemas. Mirrors DATA_MODEL §6.1."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.modules.checkout.schemas import Address


# ── Auth requests ───────────────────────────────────────────────────
class CustomerSignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=200)
    name: str = Field(..., min_length=1, max_length=120)
    accepts_marketing: bool = False
    # When set, design / try-on sessions created under this anonymous id
    # before the customer signed up are claimed onto the new account.
    anonymous_session_id: str | None = Field(default=None, max_length=64)


class CustomerLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=200)
    # Same claim-on-login behaviour as signup — useful when a customer
    # designed something anonymously, then logged in to check out.
    anonymous_session_id: str | None = Field(default=None, max_length=64)


class CustomerUpdateRequest(BaseModel):
    """PATCH /account/me. Email + password changes get their own endpoints."""

    name: str | None = Field(None, min_length=1, max_length=120)
    accepts_marketing: bool | None = None


# ── Response shapes ─────────────────────────────────────────────────
class CustomerPublic(BaseModel):
    """Never exposes the password hash. Aggregates ``has_saved_photo`` and
    ``body_profile_opted_in`` so the frontend can render the privacy controls
    without a second request."""

    customer_id: str
    email: str
    name: str
    email_verified_at: datetime | None = None
    addresses: list[Address] = Field(default_factory=list)
    has_saved_photo: bool = False
    body_profile_opted_in: bool = False
    last_login_at: datetime | None = None
    created_at: datetime


class CustomerLoginResponse(BaseModel):
    customer: CustomerPublic
    expires_at: datetime


# ── Email verification (M6.4) ───────────────────────────────────────
class EmailVerificationConfirmRequest(BaseModel):
    token: str = Field(..., min_length=1)


# ── Password reset (M6.4) ───────────────────────────────────────────
class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=200)
