"""FastAPI application factory.

Wires the modular monolith: logging, MongoDB lifecycle, CORS, the canonical
error envelope, and the v1 API router.

Per ``ARCHITECTURE.md`` §4.2 the app is a modular monolith — module routers are
mounted under ``/api/v1`` as they're built milestone-by-milestone.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import close_db, init_db
from app.errors import install_error_handlers
from app.logging_setup import configure_logging, get_logger
from app.observability import install_observability
from app.queue import close_queue, init_queue
from app.modules.admin.router import router as admin_router
from app.modules.cart.router import router as cart_router
from app.modules.catalog.router import router as catalog_router
from app.modules.checkout.router import router as checkout_router
from app.modules.customers.router import router as customers_router
from app.modules.design.router import router as design_router
from app.modules.fabrics.router import router as fabrics_router
from app.modules.orders.router import router as orders_router
from app.modules.site.router import router as site_router
from app.modules.storage_files.router import router as storage_files_router
from app.modules.try_on.account_router import router as fitting_room_router
from app.modules.try_on.router import router as try_on_router
from app.modules.webhooks.router import router as webhooks_router

settings = get_settings()
configure_logging(settings.log_level, settings.log_format)
log = get_logger("app.main")


# ── Production safety: refuse to boot with placeholder secrets ──────
_PLACEHOLDER_SECRETS = {
    "change-me-customer-secret",
    "change-me-admin-secret",
    "change-me-guest-token-secret",
}


def _assert_safe_runtime() -> None:
    """Fail fast on insecure production configuration."""
    if not settings.is_production:
        return
    placeholders_in_use = [
        name
        for name, value in (
            ("SESSION_SECRET_CUSTOMER", settings.session_secret_customer),
            ("SESSION_SECRET_ADMIN", settings.session_secret_admin),
            ("GUEST_TOKEN_SECRET", settings.guest_token_secret),
        )
        if value in _PLACEHOLDER_SECRETS
    ]
    if placeholders_in_use:
        raise RuntimeError(
            "Refusing to start in production with placeholder secrets: "
            + ", ".join(placeholders_in_use)
        )
    # The local filesystem storage backend serves files with no signature or
    # expiry — fine for dev, unacceptable for a public production deploy where
    # user photos must be access-controlled. Force B2 (or another signed backend).
    if settings.storage_backend == "local":
        raise RuntimeError(
            "Refusing to start in production with STORAGE_BACKEND=local — "
            "use a signed backend (b2) so private media isn't world-readable."
        )


def _warn_on_misconfig() -> None:
    """Non-fatal boot-time sanity checks for easy-to-miss security config."""
    secret = settings.stripe_webhook_secret
    if secret and not secret.startswith("whsec_"):
        log.warning(
            "config.stripe_webhook_secret_malformed",
            hint=(
                "STRIPE_WEBHOOK_SECRET should start with 'whsec_'. The current "
                "value won't verify live Stripe webhook signatures."
            ),
        )
    if settings.is_production and not settings.trust_forwarded_for:
        log.warning(
            "config.trust_forwarded_for_disabled",
            hint=(
                "Running in production with TRUST_FORWARDED_FOR=false. If the "
                "app is behind a proxy/LB, client IPs (and IP rate limits) will "
                "all collapse to the proxy address. Enable it behind a trusted proxy."
            ),
        )


async def _bootstrap_first_admin() -> None:
    """Create the initial owner admin if env vars are set and no match exists.

    Lets a fresh deployment have its first administrator without an out-of-band
    seed step. Safe to leave configured — idempotent on every restart.
    """
    if not settings.admin_bootstrap_email or not settings.admin_bootstrap_password:
        return
    from app.db import get_db
    from app.modules.admin.service import AdminService

    service = AdminService(get_db())
    _, created = await service.create_owner_if_missing(
        email=settings.admin_bootstrap_email,
        password=settings.admin_bootstrap_password,
        name=settings.admin_bootstrap_name,
    )
    if created:
        log.info("admin.bootstrap_first_admin", email=settings.admin_bootstrap_email)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Startup and shutdown hooks for the API process."""
    log.info("startup.begin", env=settings.app_env)
    _assert_safe_runtime()
    _warn_on_misconfig()
    await init_db()
    await init_queue()
    await _bootstrap_first_admin()
    log.info("startup.done")
    try:
        yield
    finally:
        log.info("shutdown.begin")
        await close_queue()
        await close_db()
        log.info("shutdown.done")


# Interactive docs + the OpenAPI schema publish the full API surface, so they
# are disabled in production and available only in dev/staging.
_docs_enabled = not settings.is_production

app = FastAPI(
    title="Ardezan API",
    version="0.1.0",
    description="AI-native clothing store backend",
    lifespan=lifespan,
    openapi_url="/openapi.json" if _docs_enabled else None,
    docs_url="/docs" if _docs_enabled else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Observability — request-id middleware, per-request access log, and
# liveness/readiness probes. Must be installed *after* CORS so the request
# id is bound even on CORS preflight requests (handy when debugging).
install_observability(app)

install_error_handlers(app)


# ── Module routers ───────────────────────────────────────────────────
app.include_router(catalog_router, prefix="/api/v1/catalog", tags=["catalog"])
app.include_router(cart_router, prefix="/api/v1/cart", tags=["cart"])
# Customer auth and account routes live directly under /api/v1 because the
# routes themselves span /auth/* and /account/* (per API.md §5.1 + §10.4).
app.include_router(customers_router, prefix="/api/v1", tags=["customers"])
app.include_router(checkout_router, prefix="/api/v1/checkout", tags=["checkout"])
app.include_router(fabrics_router, prefix="/api/v1", tags=["fabrics"])
app.include_router(design_router, prefix="/api/v1", tags=["design-me"])
app.include_router(orders_router, prefix="/api/v1/orders", tags=["orders"])
app.include_router(try_on_router, prefix="/api/v1/try-on", tags=["try-on"])
# Fitting Room + saved-photo + body-profile (per API.md §10.4) under /api/v1.
app.include_router(fitting_room_router, prefix="/api/v1", tags=["fitting-room"])
app.include_router(webhooks_router, prefix="/api/v1/webhooks", tags=["webhooks"])
app.include_router(site_router, prefix="/api/v1/site", tags=["site"])
app.include_router(admin_router, prefix="/api/v1/admin", tags=["admin"])

# Local-filesystem storage backend serves files at /api/v1/storage/<path>.
# Only mounted when the backend is configured for local storage; B2 callers
# would never hit this route.
if settings.storage_backend == "local":
    app.include_router(storage_files_router, prefix="/api/v1/storage", tags=["storage"])


# ── Health endpoint ──────────────────────────────────────────────────
# Lightweight — used by infrastructure liveness/readiness probes and CI.
@app.get("/api/v1/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "ardezan-api"}

