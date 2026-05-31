"""Admin auth routes (per API.md §5.2).

- ``POST /admin/auth/login`` — sets the ``admin_session`` cookie.
- ``POST /admin/auth/logout`` — clears the cookie + audit logs.
- ``GET /admin/me`` — current admin (used by the admin shell on every page load).

Future M3 routes (products, orders, refunds, AI controls, audit log viewer)
mount under the same prefix.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.config import get_settings
from app.deps import DbDep
from app.modules.admin.ai_router import router as ai_router
from app.modules.admin.audit_logs_router import router as audit_logs_router
from app.modules.admin.customers_router import router as customers_router
from app.modules.admin.dashboard_router import router as dashboard_router
from app.modules.admin.deps import ADMIN_COOKIE_NAME, AdminDep
from app.modules.admin.orders_router import router as orders_router
from app.modules.admin.products_router import router as products_router
from app.modules.admin.schemas import (
    AdminLoginRequest,
    AdminLoginResponse,
    AdminPublic,
)
from app.modules.admin.service import AdminService
from app.modules.admin.site_media_router import router as site_media_router
from app.rate_limit import enforce_login_email, rate_limit_login
from app.security import ADMIN_COOKIE_SALT, ADMIN_SESSION_TTL, sign_session

router = APIRouter()

# Mount sub-routers under /admin/*.
router.include_router(products_router)
router.include_router(orders_router)
router.include_router(ai_router)
router.include_router(audit_logs_router)
router.include_router(site_media_router)
router.include_router(dashboard_router)
router.include_router(customers_router)


def get_service(db: DbDep) -> AdminService:
    return AdminService(db)


ServiceDep = Annotated[AdminService, Depends(get_service)]


def _admin_public(admin: dict) -> AdminPublic:
    return AdminPublic(
        admin_id=admin["admin_id"],
        email=admin["email"],
        name=admin.get("name", ""),
        role=admin["role"],
        scopes=admin.get("scopes", []),
        status=admin.get("status", "active"),
        last_login_at=admin.get("last_login_at"),
        mfa_enabled=bool((admin.get("mfa") or {}).get("enabled", False)),
    )


def _set_admin_cookie(response: Response, admin_id: str, role: str) -> datetime:
    """Sign + set the admin session cookie. Returns the expiry timestamp."""
    settings = get_settings()
    token = sign_session(
        {"admin_id": admin_id, "role": role},
        settings.session_secret_admin,
        salt=ADMIN_COOKIE_SALT,
    )
    # Same first-party cookie pattern as the customer cookie — see
    # _set_customer_cookie for the rationale.
    response.set_cookie(
        key=ADMIN_COOKIE_NAME,
        value=token,
        max_age=ADMIN_SESSION_TTL,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
        path="/",
    )
    return datetime.now(timezone.utc) + timedelta(seconds=ADMIN_SESSION_TTL)


@router.post(
    "/auth/login",
    response_model=AdminLoginResponse,
    summary="Admin login — sets the admin_session cookie",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(rate_limit_login)],
)
async def admin_login(
    body: AdminLoginRequest,
    request: Request,
    response: Response,
    service: ServiceDep,
) -> AdminLoginResponse:
    await enforce_login_email(request, body.email)
    admin = await service.login(
        body.email,
        body.password,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    expires_at = _set_admin_cookie(response, admin["admin_id"], admin["role"])
    return AdminLoginResponse(admin=_admin_public(admin), expires_at=expires_at)


@router.post(
    "/auth/logout",
    summary="Clear the admin session cookie",
    status_code=status.HTTP_200_OK,
)
async def admin_logout(
    response: Response,
    request: Request,
    service: ServiceDep,
    admin: AdminDep,
) -> dict[str, str]:
    meta = admin.get("_request_meta", {})
    await service.logout(
        admin["admin_id"],
        ip_address=meta.get("ip"),
        user_agent=meta.get("ua"),
    )
    response.delete_cookie(ADMIN_COOKIE_NAME, path="/")
    return {"status": "ok"}


@router.get(
    "/me",
    response_model=AdminPublic,
    summary="Current admin (used by the admin shell)",
)
async def admin_me(admin: AdminDep) -> AdminPublic:
    return _admin_public(admin)
