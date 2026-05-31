"""Admin audit log viewer (per API.md §12.6).

Read-only. Audit log writes are append-only and live in every other admin
service. This router exposes the timeline to admins for incident review,
compliance, and operational debugging.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.deps import DbDep
from app.modules.admin.deps import AdminDep
from app.modules.admin.repository import AdminRepository
from app.modules.admin.schemas import AuditLogEntry

router = APIRouter()


def get_repo(db: DbDep) -> AdminRepository:
    return AdminRepository(db)


RepoDep = Annotated[AdminRepository, Depends(get_repo)]


# ── Response shapes ─────────────────────────────────────────────────
class AuditLogListResponse(BaseModel):
    items: list[AuditLogEntry]
    total: int
    limit: int
    offset: int


class DistinctValuesResponse(BaseModel):
    values: list[str] = Field(default_factory=list)


# ── Routes ──────────────────────────────────────────────────────────
@router.get(
    "/audit-logs",
    response_model=AuditLogListResponse,
    summary="List audit log entries with filters (sorted newest-first)",
)
async def list_audit_logs(
    repo: RepoDep,
    admin: AdminDep,
    actor_type: Annotated[str | None, Query(description="admin | system | customer")] = None,
    actor_id: Annotated[str | None, Query()] = None,
    action: Annotated[str | None, Query(description="e.g. order.refund_issued")] = None,
    target_type: Annotated[str | None, Query(description="product | variant | order | settings | admin | size_chart")] = None,
    target_id: Annotated[str | None, Query()] = None,
    created_after: Annotated[datetime | None, Query()] = None,
    created_before: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditLogListResponse:
    items, total = await repo.list_audit_logs(
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        created_after=created_after,
        created_before=created_before,
        limit=limit,
        offset=offset,
    )
    return AuditLogListResponse(
        items=[
            AuditLogEntry(
                audit_log_id=d["audit_log_id"],
                actor_type=d["actor_type"],
                actor_id=d.get("actor_id"),
                action=d["action"],
                target_type=d.get("target_type"),
                target_id=d.get("target_id"),
                before_summary=d.get("before_summary"),
                after_summary=d.get("after_summary"),
                ip_address=d.get("ip_address"),
                user_agent=d.get("user_agent"),
                created_at=d["created_at"],
            )
            for d in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/audit-logs/actions",
    response_model=DistinctValuesResponse,
    summary="Distinct ``action`` values ever recorded — populates the filter dropdown",
)
async def distinct_actions(
    repo: RepoDep,
    admin: AdminDep,
) -> DistinctValuesResponse:
    return DistinctValuesResponse(values=await repo.distinct_audit_actions())


@router.get(
    "/audit-logs/target-types",
    response_model=DistinctValuesResponse,
    summary="Distinct ``target_type`` values — populates the filter dropdown",
)
async def distinct_target_types(
    repo: RepoDep,
    admin: AdminDep,
) -> DistinctValuesResponse:
    return DistinctValuesResponse(values=await repo.distinct_audit_target_types())
