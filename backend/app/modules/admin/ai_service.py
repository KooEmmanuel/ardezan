"""Admin AI controls + analytics orchestration."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.errors import ApiError, ErrorCode
from app.logging_setup import get_logger
from app.modules.admin.ai_repository import (
    SETTINGS_KEY_MAP,
    AiJobsRepository,
    AiSettingsRepository,
    AnalyticsRepository,
)
from app.modules.admin.ai_schemas import AiSettingsUpdate
from app.modules.admin.repository import AdminRepository

log = get_logger(__name__)

_COMPLETED_ORDER_STATUSES = ["paid", "packed", "shipped", "delivered"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _start_of_today() -> datetime:
    n = _now()
    return n.replace(hour=0, minute=0, second=0, microsecond=0)


class AdminAiService:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self.db = db
        self.settings_repo = AiSettingsRepository(db)
        self.jobs_repo = AiJobsRepository(db)
        self.analytics_repo = AnalyticsRepository(db)
        self.admin_repo = AdminRepository(db)

    # ── Settings ───────────────────────────────────────────────
    async def get_settings(self) -> dict[str, Any]:
        return await self.settings_repo.get_resolved()

    async def update_settings(
        self,
        body: AiSettingsUpdate,
        admin: dict[str, Any],
    ) -> dict[str, Any]:
        fields = body.model_dump(exclude_unset=True, exclude_none=True)
        if not fields:
            return await self.settings_repo.get_resolved()

        before = await self.settings_repo.get_resolved()

        for ui_key, value in fields.items():
            settings_key = SETTINGS_KEY_MAP.get(ui_key)
            if not settings_key:
                continue
            await self.settings_repo.set_value(settings_key, value, admin["admin_id"])

        after = await self.settings_repo.get_resolved()
        await self._audit(
            admin,
            action="ai.settings_updated",
            target_id="ai",
            before={k: before[k] for k in fields},
            after={k: after[k] for k in fields},
        )
        log.info(
            "admin.ai_settings_updated",
            fields=list(fields),
            kill_switch=after.get("kill_switch_enabled"),
        )
        return after

    # ── AI jobs ────────────────────────────────────────────────
    async def list_jobs(
        self,
        *,
        status: str | None,
        customer_id: str | None,
        anonymous_session_id: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        return await self.jobs_repo.list(
            status=status,
            customer_id=customer_id,
            anonymous_session_id=anonymous_session_id,
            limit=limit,
            offset=offset,
        )

    async def get_job(self, job_id: str) -> dict[str, Any]:
        doc = await self.jobs_repo.find_by_id(job_id)
        if not doc:
            raise ApiError(
                ErrorCode.NOT_FOUND, f"AI job not found: {job_id}", http_status=404
            )
        return doc

    # ── Analytics ──────────────────────────────────────────────
    async def overview(self) -> dict[str, Any]:
        today = _start_of_today()
        seven_days_ago = _now() - timedelta(days=7)

        rev = await self.analytics_repo.revenue_and_orders(
            _COMPLETED_ORDER_STATUSES,
            today_start=today,
            seven_days_ago=seven_days_ago,
        )
        top = await self.analytics_repo.top_products(
            _COMPLETED_ORDER_STATUSES, limit=5
        )
        low = await self.analytics_repo.low_stock_variants(limit=20)

        return {
            "revenue_total_amount": rev["revenue_amount"],
            "revenue_currency": rev["revenue_currency"],
            "orders_total": rev["orders_total"],
            "orders_today": rev["orders_today"],
            "orders_last_7_days": rev["orders_7d"],
            "top_products": top,
            "low_stock_variants": low,
        }

    async def ai_analytics(self) -> dict[str, Any]:
        today = _start_of_today()
        seven_days_ago = _now() - timedelta(days=7)

        settings = await self.settings_repo.get_resolved()
        today_spend = await self.analytics_repo.ai_today_spend(today)
        counts = await self.analytics_repo.ai_status_counts(seven_days_ago)
        failed_jobs = await self.analytics_repo.ai_recent_failed(limit=10)

        ceiling = int(settings["daily_spend_ceiling_amount"])
        pct = (today_spend / ceiling) if ceiling > 0 else 0.0

        return {
            "today_spend_amount": today_spend,
            "today_spend_ceiling_amount": ceiling,
            "daily_spend_pct": round(pct, 4),
            "kill_switch_enabled": bool(settings["kill_switch_enabled"]),
            "try_on_starts_7d": sum(counts.values()),
            "try_on_completed_7d": counts.get("completed", 0),
            "try_on_partial_7d": counts.get("completed_partial", 0),
            "try_on_failed_7d": (
                counts.get("failed", 0)
                + counts.get("expired", 0)
                + counts.get("cancelled", 0)
            ),
            "failed_jobs_recent": [
                {
                    "job_id": j["job_id"],
                    "status": j["status"],
                    "failed_stage": (j.get("failure") or {}).get("failed_stage"),
                    "failure_reason": (j.get("failure") or {}).get("reason"),
                    "customer_or_session_id": (
                        j.get("customer_id") or j.get("anonymous_session_id")
                    ),
                    "created_at": j["created_at"],
                }
                for j in failed_jobs
            ],
            "currency": settings["currency"],
        }

    # ── Audit helper ───────────────────────────────────────────
    async def _audit(
        self,
        admin: dict[str, Any],
        *,
        action: str,
        target_id: str,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> None:
        meta = admin.get("_request_meta", {})
        await self.admin_repo.write_audit(
            actor_id=admin["admin_id"],
            action=action,
            target_type="settings",
            target_id=target_id,
            before=before,
            after=after,
            ip_address=meta.get("ip"),
            user_agent=meta.get("ua"),
        )
