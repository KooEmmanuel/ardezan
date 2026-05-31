"""Admin AI controls + analytics schemas.

Money is integer minor units throughout (per DATA_MODEL §2.4). The settings
in the ``settings`` collection are stored under keys ``ai.kill_switch``,
``ai.daily_spend_ceiling_amount``, ``ai.anonymous_daily_limit``,
``ai.registered_weekly_limit``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ── AI settings ─────────────────────────────────────────────────────
class AiSettings(BaseModel):
    """Resolved settings — falls back to .env defaults if no DB row yet."""

    kill_switch_enabled: bool
    daily_spend_ceiling_amount: int = Field(..., ge=0)
    anonymous_daily_limit: int = Field(..., ge=0)
    registered_weekly_limit: int = Field(..., ge=0)
    currency: str = "USD"


class AiSettingsUpdate(BaseModel):
    """Partial update — only fields sent are changed."""

    kill_switch_enabled: bool | None = None
    daily_spend_ceiling_amount: int | None = Field(None, ge=0)
    anonymous_daily_limit: int | None = Field(None, ge=0)
    registered_weekly_limit: int | None = Field(None, ge=0)


# ── Analytics overview ──────────────────────────────────────────────
class TopProduct(BaseModel):
    product_id: str
    title: str
    quantity_sold: int
    revenue_amount: int


class LowStockVariant(BaseModel):
    variant_id: str
    product_id: str
    sku: str
    size: str
    color: str
    available_for_sale: int
    low_stock_threshold: int


class AnalyticsOverview(BaseModel):
    revenue_total_amount: int
    revenue_currency: str
    orders_total: int
    orders_today: int
    orders_last_7_days: int
    top_products: list[TopProduct]
    low_stock_variants: list[LowStockVariant]


# ── Analytics AI ────────────────────────────────────────────────────
class FailedJobSummary(BaseModel):
    job_id: str
    status: str
    failed_stage: str | None = None
    failure_reason: str | None = None
    customer_or_session_id: str | None = None
    created_at: datetime


class AnalyticsAi(BaseModel):
    today_spend_amount: int
    today_spend_ceiling_amount: int
    daily_spend_pct: float
    kill_switch_enabled: bool
    try_on_starts_7d: int
    try_on_completed_7d: int
    try_on_partial_7d: int
    try_on_failed_7d: int
    failed_jobs_recent: list[FailedJobSummary]
    currency: str = "USD"


# ── AI jobs reads ───────────────────────────────────────────────────
class AiJobListItem(BaseModel):
    job_id: str
    try_on_session_id: str | None = None
    customer_id: str | None = None
    anonymous_session_id: str | None = None
    status: str
    current_stage: str | None = None
    estimated_cost_amount: int | None = None
    failure_reason: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class AiJobListResponse(BaseModel):
    items: list[AiJobListItem]
    total: int
    limit: int
    offset: int


class AiJobDetail(BaseModel):
    """Full ai_jobs document for admin inspection / debugging."""

    job_id: str
    try_on_session_id: str | None = None
    customer_id: str | None = None
    anonymous_session_id: str | None = None
    status: str
    current_stage: str | None = None
    input: dict[str, Any] = Field(default_factory=dict)
    progress_events: list[dict[str, Any]] = Field(default_factory=list)
    provider_calls: list[dict[str, Any]] = Field(default_factory=list)
    cost: dict[str, Any] = Field(default_factory=dict)
    failure: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    expires_at: datetime | None = None
