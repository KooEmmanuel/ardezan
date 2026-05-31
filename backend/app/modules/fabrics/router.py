"""Public read-only fabric routes.

Customers hit ``GET /fabrics`` to render the swatch picker on the
Design Me page. ``GET /fabrics/{id}/estimate`` returns a cost
breakdown for a (fabric, piece_type, complexity) combination — the
Design Me page calls it to show the live estimate as the customer
picks options.
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db import C
from app.deps import DbDep
from app.errors import ApiError, ErrorCode
from app.modules.fabrics.pricing import CostBreakdown, estimate_cost
from app.modules.fabrics.schemas import (
    FabricListResponse,
    FabricPublic,
)

router = APIRouter()


async def _list_active_fabrics(
    db: AsyncIOMotorDatabase[Any],
) -> list[dict[str, Any]]:
    cursor = db[C.fabrics].find(
        {"active": True}, projection={"_id": 0}
    ).sort("name", 1)
    return await cursor.to_list(None)


@router.get(
    "/fabrics",
    response_model=FabricListResponse,
    summary="List active fabrics for the Design Me picker",
)
async def list_fabrics(db: DbDep) -> FabricListResponse:
    docs = await _list_active_fabrics(db)
    return FabricListResponse(items=[FabricPublic(**d) for d in docs])


@router.get(
    "/fabrics/{fabric_id}/estimate",
    response_model=CostBreakdown,
    summary="Estimate the total cost for a piece in this fabric",
)
async def estimate_for_fabric(
    fabric_id: str,
    db: DbDep,
    piece_type: Annotated[str, Query()],
    complexity: Annotated[str, Query()] = "standard",
) -> CostBreakdown:
    fabric = await db[C.fabrics].find_one(
        {"fabric_id": fabric_id, "active": True}, projection={"_id": 0}
    )
    if not fabric:
        raise ApiError(
            ErrorCode.NOT_FOUND,
            f"Fabric not found: {fabric_id}",
            http_status=404,
        )
    if piece_type not in fabric.get("suitable_for", []):
        raise ApiError(
            ErrorCode.VALIDATION_ERROR,
            f"This fabric isn't a good fit for a {piece_type}.",
            http_status=400,
            details={
                "fabric_id": fabric_id,
                "suitable_for": fabric.get("suitable_for", []),
            },
        )
    try:
        return estimate_cost(
            fabric_id=fabric_id,
            cost_per_yard_amount=int(fabric["cost_per_yard_amount"]),
            currency=fabric.get("currency", "USD"),
            piece_type=piece_type,  # type: ignore[arg-type]
            complexity=complexity,  # type: ignore[arg-type]
        )
    except KeyError as exc:
        raise ApiError(
            ErrorCode.VALIDATION_ERROR,
            f"Unknown piece_type or complexity: {exc}",
            http_status=400,
        ) from exc
