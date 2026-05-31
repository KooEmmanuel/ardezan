"""``require_admin`` dependency — verifies the signed cookie + DB status.

The cookie payload is just an admin id; we re-read ``admin_users`` every
request so disabling an account invalidates every active session
immediately. Cost is one indexed read per admin request — fine for
admin-volume traffic.
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import Cookie, Depends, Request

from app.config import get_settings
from app.deps import DbDep
from app.errors import ApiError, ErrorCode
from app.modules.admin.repository import AdminRepository
from app.security import ADMIN_COOKIE_SALT, ADMIN_SESSION_TTL, verify_session

ADMIN_COOKIE_NAME = "admin_session"


async def require_admin(
    db: DbDep,
    request: Request,
    admin_session: Annotated[str | None, Cookie(alias=ADMIN_COOKIE_NAME)] = None,
) -> dict[str, Any]:
    """Resolve the current admin or raise UNAUTHENTICATED.

    The ``request`` parameter is unused in the auth check itself, but it
    propagates IP / user-agent into downstream audit writes via the service
    layer if needed.
    """
    if not admin_session:
        raise ApiError(
            ErrorCode.UNAUTHENTICATED,
            "Admin session required.",
            http_status=401,
        )

    settings = get_settings()
    payload = verify_session(
        admin_session,
        settings.session_secret_admin,
        salt=ADMIN_COOKIE_SALT,
        max_age_seconds=ADMIN_SESSION_TTL,
    )
    admin_id = payload.get("admin_id") if payload else None
    if not admin_id:
        raise ApiError(
            ErrorCode.UNAUTHENTICATED,
            "Invalid or expired session.",
            http_status=401,
        )

    repo = AdminRepository(db)
    admin = await repo.find_by_id(admin_id)
    if not admin or admin.get("status") != "active":
        raise ApiError(
            ErrorCode.UNAUTHENTICATED,
            "Admin account is disabled.",
            http_status=401,
        )
    # Stash the request on the admin dict so handlers can pull ip/ua for audit
    # writes without re-introspecting the Request object.
    admin["_request_meta"] = {
        "ip": request.client.host if request.client else None,
        "ua": request.headers.get("user-agent"),
    }
    return admin


AdminDep = Annotated[dict[str, Any], Depends(require_admin)]
