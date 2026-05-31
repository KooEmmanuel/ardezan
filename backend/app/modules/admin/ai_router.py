"""Admin AI controls + analytics routes (per API.md §12.5)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.deps import DbDep
from app.modules.admin.ai_schemas import (
    AiJobDetail,
    AiJobListItem,
    AiJobListResponse,
    AiSettings,
    AiSettingsUpdate,
    AnalyticsAi,
    AnalyticsOverview,
)
from app.modules.admin.ai_service import AdminAiService
from app.modules.admin.deps import AdminDep

router = APIRouter()


def get_service(db: DbDep) -> AdminAiService:
    return AdminAiService(db)


ServiceDep = Annotated[AdminAiService, Depends(get_service)]


# ── Analytics ───────────────────────────────────────────────────────
@router.get(
    "/analytics/overview",
    response_model=AnalyticsOverview,
    summary="Revenue, orders, top products, low stock",
)
async def analytics_overview(
    service: ServiceDep,
    admin: AdminDep,
) -> AnalyticsOverview:
    return AnalyticsOverview(**await service.overview())


@router.get(
    "/analytics/ai",
    response_model=AnalyticsAi,
    summary="AI spend vs ceiling, try-on volume + failures",
)
async def analytics_ai(
    service: ServiceDep,
    admin: AdminDep,
) -> AnalyticsAi:
    return AnalyticsAi(**await service.ai_analytics())


# ── AI settings ─────────────────────────────────────────────────────
@router.get(
    "/settings/ai",
    response_model=AiSettings,
    summary="Read current AI runtime settings",
)
async def get_ai_settings(
    service: ServiceDep,
    admin: AdminDep,
) -> AiSettings:
    return AiSettings(**await service.get_settings())


@router.patch(
    "/settings/ai",
    response_model=AiSettings,
    summary="Update AI controls — kill switch, spend ceiling, quotas",
)
async def update_ai_settings(
    body: AiSettingsUpdate,
    service: ServiceDep,
    admin: AdminDep,
) -> AiSettings:
    return AiSettings(**await service.update_settings(body, admin))


# ── AI jobs ─────────────────────────────────────────────────────────
@router.get(
    "/ai/jobs",
    response_model=AiJobListResponse,
    summary="List AI try-on jobs (status, customer, session filters)",
)
async def list_ai_jobs(
    service: ServiceDep,
    admin: AdminDep,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    customer_id: Annotated[str | None, Query()] = None,
    anonymous_session_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AiJobListResponse:
    items, total = await service.list_jobs(
        status=status_filter,
        customer_id=customer_id,
        anonymous_session_id=anonymous_session_id,
        limit=limit,
        offset=offset,
    )
    return AiJobListResponse(
        items=[
            AiJobListItem(
                job_id=j["job_id"],
                try_on_session_id=j.get("try_on_session_id"),
                customer_id=j.get("customer_id"),
                anonymous_session_id=j.get("anonymous_session_id"),
                status=j["status"],
                current_stage=j.get("current_stage"),
                estimated_cost_amount=(j.get("cost") or {}).get(
                    "estimated_total_amount"
                ),
                failure_reason=(j.get("failure") or {}).get("reason"),
                created_at=j["created_at"],
                completed_at=j.get("completed_at"),
            )
            for j in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/ai/jobs/{job_id}",
    response_model=AiJobDetail,
    summary="Full AI job detail — progress events, provider calls, costs",
)
async def get_ai_job(
    job_id: str,
    service: ServiceDep,
    admin: AdminDep,
) -> AiJobDetail:
    doc = await service.get_job(job_id)
    return AiJobDetail(
        job_id=doc["job_id"],
        try_on_session_id=doc.get("try_on_session_id"),
        customer_id=doc.get("customer_id"),
        anonymous_session_id=doc.get("anonymous_session_id"),
        status=doc["status"],
        current_stage=doc.get("current_stage"),
        input=doc.get("input") or {},
        progress_events=doc.get("progress_events") or [],
        provider_calls=doc.get("provider_calls") or [],
        cost=doc.get("cost") or {},
        failure=doc.get("failure"),
        created_at=doc["created_at"],
        updated_at=doc.get("updated_at", doc["created_at"]),
        completed_at=doc.get("completed_at"),
        expires_at=doc.get("expires_at"),
    )
