"""Request-id propagation, access logging, readiness probe (M6.5).

Three concerns, one module:

1. ``RequestIDMiddleware`` — extracts/generates a request id, binds it to
   structlog ``contextvars`` so every log line emitted during the request
   carries ``request_id``, and echoes it as ``X-Request-ID`` on the response
   so callers can correlate.

2. ``AccessLogMiddleware`` — one structured log line per request, after the
   response is fully formed. Includes method, path, status, duration, and
   client IP. Skipped on the health/readiness endpoints to keep noise down.

3. ``register_readiness_routes`` — mounts ``/healthz`` (liveness) and
   ``/readyz`` (deep readiness: MongoDB ping + Redis PING). Liveness stays
   shallow on purpose: if the process is up enough to answer, it's alive.
"""
from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING

import structlog
from fastapi import FastAPI, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.config import get_settings
from app.db import get_db
from app.logging_setup import get_logger
from app.queue import get_queue

if TYPE_CHECKING:
    from starlette.types import ASGIApp

log = get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"

# Health endpoints get a lot of traffic from probes; skip the access log
# for them so the signal-to-noise stays useful.
_QUIET_PATHS = {
    "/healthz",
    "/readyz",
    "/api/v1/health",
}


def _new_request_id() -> str:
    return f"req_{uuid.uuid4().hex[:16]}"


def _client_ip(request: Request) -> str:
    # Mirror app.rate_limit._client_ip: only trust forwarded headers behind a
    # configured proxy, else use the socket peer (un-spoofable for logging).
    if get_settings().trust_forwarded_for:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
        xri = request.headers.get("x-real-ip")
        if xri:
            return xri.strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Bind a request id for the lifetime of one request.

    Reuses an incoming ``X-Request-ID`` if it's present and reasonably shaped
    (we don't trust arbitrary user input as a log key — cap length, ascii-ish).
    Otherwise mints a fresh ``req_<hex>`` id.
    """

    MAX_INCOMING_LENGTH = 128

    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get(REQUEST_ID_HEADER)
        if (
            incoming
            and 1 <= len(incoming) <= self.MAX_INCOMING_LENGTH
            and incoming.isprintable()
        ):
            request_id = incoming
        else:
            request_id = _new_request_id()

        structlog.contextvars.bind_contextvars(request_id=request_id)
        # Stash on request.state so handlers (e.g. error responses) can read
        # it without touching contextvars.
        request.state.request_id = request_id

        try:
            response: Response = await call_next(request)
        finally:
            # Always clear so the next request on this asyncio task starts
            # with a clean contextvars snapshot.
            structlog.contextvars.clear_contextvars()

        response.headers[REQUEST_ID_HEADER] = request_id
        return response


class AccessLogMiddleware(BaseHTTPMiddleware):
    """One log line per request after the response is built."""

    def __init__(self, app: "ASGIApp", quiet_paths: set[str] | None = None) -> None:
        super().__init__(app)
        self._quiet = quiet_paths or _QUIET_PATHS

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self._quiet:
            return await call_next(request)

        started = time.perf_counter()
        try:
            response: Response = await call_next(request)
        except Exception:
            # Re-raise so FastAPI's exception handlers run; the access log
            # for this case is emitted by the error handler instead.
            duration_ms = int((time.perf_counter() - started) * 1000)
            log.warning(
                "http.request_unhandled",
                method=request.method,
                path=request.url.path,
                duration_ms=duration_ms,
                client_ip=_client_ip(request),
            )
            raise

        duration_ms = int((time.perf_counter() - started) * 1000)
        # ``info`` for normal traffic; ``warning`` for 4xx; ``error`` for 5xx
        # so log filters can sort severity without re-parsing status.
        status = response.status_code
        if status >= 500:
            level = log.error
        elif status >= 400:
            level = log.warning
        else:
            level = log.info
        level(
            "http.request",
            method=request.method,
            path=request.url.path,
            status=status,
            duration_ms=duration_ms,
            client_ip=_client_ip(request),
        )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach baseline security headers to every response.

    - ``X-Content-Type-Options: nosniff`` — stop MIME sniffing.
    - ``X-Frame-Options: DENY`` — clickjacking protection (the API is never
      meant to be framed).
    - ``Referrer-Policy`` — don't leak full URLs cross-origin.
    - ``Cross-Origin-Opener-Policy`` / ``Permissions-Policy`` — lock down
      ambient capabilities the API never uses.
    - ``Strict-Transport-Security`` and a strict ``Content-Security-Policy``
      are added **only in production**, where Swagger UI (which needs a CDN +
      inline scripts) is disabled, so they can't break the dev ``/docs`` page.
    """

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        if get_settings().is_production:
            headers.setdefault(
                "Strict-Transport-Security",
                "max-age=63072000; includeSubDomains; preload",
            )
            headers.setdefault(
                "Content-Security-Policy",
                "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
            )
        return response


# ── Readiness ───────────────────────────────────────────────────────
async def _check_mongo() -> tuple[bool, str | None]:
    try:
        await get_db().command("ping")
        return True, None
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:200]


async def _check_redis() -> tuple[bool, str | None]:
    try:
        pool = get_queue()
        await pool.ping()
        return True, None
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:200]


def register_readiness_routes(app: FastAPI) -> None:
    """Mount ``/healthz`` (liveness) + ``/readyz`` (deep readiness).

    Liveness exists so the orchestrator can tell the process is up at all
    — it must never depend on external systems, else a Mongo blip restarts
    the API. Readiness *should* exercise dependencies so traffic only routes
    to instances that can actually serve.
    """

    @app.get("/healthz", tags=["health"], include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", tags=["health"], include_in_schema=False)
    async def readyz(response: Response) -> dict[str, object]:
        mongo_ok, mongo_err = await _check_mongo()
        redis_ok, redis_err = await _check_redis()
        ready = mongo_ok and redis_ok
        if not ready:
            response.status_code = 503
        body: dict[str, object] = {
            "status": "ready" if ready else "not_ready",
            "checks": {
                "mongo": {"ok": mongo_ok, "error": mongo_err},
                "redis": {"ok": redis_ok, "error": redis_err},
            },
        }
        return body


def install_observability(app: FastAPI) -> None:
    """One-call wiring used by ``app.main``.

    Order matters: ``RequestIDMiddleware`` runs first (outermost) so the
    contextvars binding is alive for the access log too.
    """
    # FastAPI middleware execution is reverse of registration order —
    # adding access log first, then request id, makes request id outermost.
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RequestIDMiddleware)
    register_readiness_routes(app)


__all__ = [
    "RequestIDMiddleware",
    "AccessLogMiddleware",
    "SecurityHeadersMiddleware",
    "install_observability",
    "register_readiness_routes",
    "REQUEST_ID_HEADER",
]
