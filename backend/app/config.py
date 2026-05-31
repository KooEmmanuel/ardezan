"""Application settings loaded from environment variables.

Uses pydantic-settings so values are validated at boot. Secrets must be set in
``.env`` (local) or the platform's secret store (staging / prod). Defaults here
exist only so the service can boot in a fresh checkout — placeholder secrets are
flagged in ``app.main`` if still in use when ``APP_ENV != "development"``.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Single source of truth for runtime configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── App ──────────────────────────────────────────────────────────
    app_env: Literal["development", "staging", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "json"
    cors_allowed_origins: str = "http://localhost:3000"
    # Only trust ``X-Forwarded-For`` / ``X-Real-IP`` for the client IP when a
    # trusted reverse proxy (that overwrites these headers) sits in front of
    # the app. Left False, the socket peer is used so a client can't spoof its
    # IP to dodge IP-scoped rate limits or poison access logs. Set True in
    # production deployments behind a known proxy/load balancer.
    trust_forwarded_for: bool = False

    # ── Database ─────────────────────────────────────────────────────
    mongo_url: str = "mongodb://localhost:27017"
    mongo_db: str = "atelier_dev"

    # ── Agents (Google ADK + MongoDB MCP) ────────────────────────────
    # When False, agent data tools talk to Mongo directly via Motor.
    # When True, they route through the official mongodb-mcp-server.
    # Both modes reuse ``mongo_url`` above — one connection string,
    # local in dev, Atlas in prod, no second URL to keep in sync.
    mcp_enabled: bool = False

    # ── Queue ────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Auth / sessions ──────────────────────────────────────────────
    session_secret_customer: str = "change-me-customer-secret"
    session_secret_admin: str = "change-me-admin-secret"
    guest_token_secret: str = "change-me-guest-token-secret"

    # Optional: when the storefront and API are on different subdomains
    # of the same eTLD+1 (e.g. ``www.ardezan.com`` and ``api.ardezan.com``),
    # set this to ``.ardezan.com`` (note the leading dot — apex + all
    # subdomains). The session cookie is then sent by the browser to
    # both the storefront and the API, so SSR pages can read it on
    # Vercel and the API can read it on Railway.
    # Leave empty in dev (cookies stay host-scoped to localhost).
    session_cookie_domain: str = ""

    # First-admin bootstrap. If both are set on first boot and no admin with
    # this email exists yet, one is created with the ``owner`` role. Used to
    # avoid a chicken-and-egg problem on a fresh database. Idempotent.
    admin_bootstrap_email: str = ""
    admin_bootstrap_password: str = ""
    admin_bootstrap_name: str = "Owner"

    # ── AI ───────────────────────────────────────────────────────────
    gemini_api_key: str = ""
    gemini_model_analyzer: str = "gemini-2.5-flash"
    gemini_model_recommender: str = "gemini-2.5-flash"
    gemini_model_designer: str = "gemini-2.5-flash-image"
    gemini_model_safety: str = "gemini-2.5-flash"
    ai_kill_switch: bool = False
    ai_daily_spend_ceiling_usd: float = 75.0
    ai_anonymous_daily_limit: int = 3
    ai_registered_weekly_limit: int = 10
    # When True, a Gemini outage allows uploads through with a warning
    # log instead of returning 503. Useful in local dev without a key;
    # keep False in production so we never silently bypass moderation.
    ai_safety_fail_open: bool = False
    # Master switch — if False, the four AI-classifier gates are skipped
    # entirely (the Pillow file gate still runs). Reserve for emergencies.
    ai_safety_classifier_enabled: bool = True

    # ── Rate limits (M6.3, REQ-062) ──────────────────────────────────
    # Per-IP burst limit on the try-on upload endpoint. Protects from
    # automation; legit users won't hit this from a single browser.
    rate_limit_upload_ip_per_min: int = 6
    # Per-identity sustain limit (anonymous session id or customer cookie)
    # so shared-NAT scenarios don't trap a real customer behind one rogue
    # IP. ``ai_anonymous_daily_limit`` still applies as a deeper cap.
    rate_limit_upload_fingerprint_per_hour: int = 20
    # Login brute-force / credential-stuffing protection. Per-IP burst guards
    # against automated spraying; per-email (15-min window) guards a single
    # targeted account without locking it out permanently.
    # The per-email cap is intentionally loose enough for legitimate
    # forgot-my-password loops and demo/QA cycles. The per-IP cap is the
    # real defence against automated spraying — keep that one tight.
    rate_limit_login_ip_per_min: int = 10
    rate_limit_login_email_per_15min: int = 30

    # ── Inventory ────────────────────────────────────────────────────
    checkout_soft_hold_minutes: int = 10
    # Daily low-stock digest emailed to the operator. If the address is
    # empty the worker silently skips the send so dev environments don't
    # spam MailHog. The threshold check uses each variant's
    # ``low_stock_threshold`` field — set per product in admin.
    low_stock_alert_email: str = ""
    low_stock_alert_enabled: bool = True

    # ── Payments (OD-003 placeholder) ────────────────────────────────
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""

    # ── Storage backend (B2 cloud or local filesystem) ───────────────
    # ``local`` writes to ``storage_local_dir`` on the host machine and
    # serves files via ``/api/v1/storage/{path}``. Useful during dev to
    # avoid hitting B2's daily egress quota. ``b2`` is the production
    # backend.
    storage_backend: Literal["b2", "local"] = "b2"
    # Filesystem directory used when ``storage_backend=local``. Relative
    # paths resolve relative to the project root (parent of backend/).
    storage_local_dir: str = "storage"
    # Public URL the storefront uses to fetch local files. The path component
    # is appended verbatim. For dev this is the API server.
    storage_local_public_base_url: str = "http://localhost:8000"

    # B2 native API credentials (used when storage_backend=b2). The 12-char
    # ``keyID`` + 42-char ``applicationKey`` from B2's "App Keys" page work
    # directly without minting an S3-compatible key.
    b2_key_id: str = ""
    b2_application_key: str = ""
    b2_bucket_name: str = ""
    # All keys are prefixed with this so multiple projects can share a bucket
    # or directory without collisions.
    storage_key_prefix: str = "atelier/"

    # Backwards-compat read-only accessor for code that still references the
    # old name (e.g. logging). Always reads from ``b2_bucket_name``.
    @property
    def s3_bucket(self) -> str:
        return self.b2_bucket_name

    # ── Email (SMTP) ─────────────────────────────────────────────────
    # Local dev defaults point at the MailHog container in docker-compose.
    # For prod, swap to your real provider (Resend, Mailgun, SES, Postmark).
    # Accepts SMTP_HOST or SMTP_SERVER (common in tutorials).
    smtp_host: str = Field(
        default="localhost",
        validation_alias=AliasChoices("SMTP_HOST", "SMTP_SERVER"),
    )
    smtp_port: int = 1025
    smtp_username: str = ""
    smtp_password: str = ""
    # "none"     — plain SMTP, no encryption (MailHog dev)
    # "starttls" — STARTTLS upgrade after connect (typical for port 587)
    # "ssl"      — implicit TLS from the start (typical for port 465)
    smtp_tls_mode: Literal["none", "starttls", "ssl"] = "none"
    smtp_from_name: str = "Ardezan"
    smtp_from_email: str = "orders@ardezan.local"
    # Base URL used to build links inside emails (guest-claim, manage order, etc.)
    email_link_base_url: str = "http://localhost:3000"

    # ── Store / launch market (OD-011 placeholder) ───────────────────
    store_country: str = "US"
    store_currency: str = "USD"
    store_locale: str = "en-US"

    # ── Retention ────────────────────────────────────────────────────
    anonymous_upload_retention_minutes: int = 15
    anonymous_generated_retention_hours: int = 24

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """Memoised so settings are parsed once per process."""
    return Settings()
