"""Consistent API error model (per ``API.md`` §4.4).

Every error response body has this shape::

    {
      "error": {
        "code": "OUT_OF_STOCK",
        "message": "...",
        "details": {...},
        "request_id": "req_..."
      }
    }

Raise ``ApiError`` from anywhere in the call stack; ``install_error_handlers``
turns it into a JSON response with the right shape and HTTP status.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.logging_setup import get_logger

log = get_logger(__name__)


# ── Canonical error codes (mirrors API.md §4.4) ─────────────────────
class ErrorCode:
    UNAUTHENTICATED = "UNAUTHENTICATED"
    FORBIDDEN = "FORBIDDEN"
    EMAIL_NOT_VERIFIED = "EMAIL_NOT_VERIFIED"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    PAYMENT_REQUIRED = "PAYMENT_REQUIRED"
    RATE_LIMITED = "RATE_LIMITED"
    AI_UNAVAILABLE = "AI_UNAVAILABLE"
    UPLOAD_REJECTED = "UPLOAD_REJECTED"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    WEBHOOK_INVALID_SIGNATURE = "WEBHOOK_INVALID_SIGNATURE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ApiError(Exception):
    """Raise from anywhere — the handler renders the standard JSON shape."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        http_status: int = status.HTTP_400_BAD_REQUEST,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.details = details or {}


def _error_body(
    code: str,
    message: str,
    request_id: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message, "request_id": request_id}
    if details:
        error["details"] = details
    return {"error": error}


def _request_id(request: Request) -> str:
    """Prefer the id the middleware bound for this request.

    Falls back to the incoming header or a fresh id so error responses still
    have *some* correlation key even if the middleware isn't installed (e.g.
    in tests that construct ``ApiError`` directly).
    """
    rid = getattr(request.state, "request_id", None)
    if rid:
        return str(rid)
    return request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:16]}"


def install_error_handlers(app: FastAPI) -> None:
    """Register handlers so every error response uses the same envelope."""

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        rid = _request_id(request)
        log.warning(
            "api.error",
            code=exc.code,
            message=exc.message,
            status=exc.http_status,
            request_id=rid,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=exc.http_status,
            content=_error_body(exc.code, exc.message, rid, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        rid = _request_id(request)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_body(
                ErrorCode.VALIDATION_ERROR,
                "Request failed validation.",
                rid,
                {"errors": exc.errors()},
            ),
        )

    @app.exception_handler(Exception)
    async def handle_uncaught(request: Request, exc: Exception) -> JSONResponse:
        rid = _request_id(request)
        log.exception("api.unhandled", error=str(exc), request_id=rid, path=request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_body(
                ErrorCode.INTERNAL_ERROR,
                "An unexpected error occurred.",
                rid,
            ),
        )
