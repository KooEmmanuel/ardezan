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
    FabricSwatch,
)
from app.storage import get_storage

router = APIRouter()


async def _list_active_fabrics(
    db: AsyncIOMotorDatabase[Any],
) -> list[dict[str, Any]]:
    cursor = db[C.fabrics].find(
        {"active": True}, projection={"_id": 0}
    ).sort("name", 1)
    return await cursor.to_list(None)


async def _hydrated_public_fabric(
    db: AsyncIOMotorDatabase[Any], doc: dict[str, Any]
) -> FabricPublic:
    """Build a ``FabricPublic`` with a signed swatch image URL (if any).

    Admin-uploaded swatches are stored as ``swatch.media_asset_id``;
    here we resolve them to a fresh signed URL so the frontend can
    render the real fabric photo. The CSS gradient stays as a fallback
    when no image is attached.
    """
    swatch_in = doc.get("swatch") or {}
    image_url: str | None = None
    media_asset_id = swatch_in.get("media_asset_id")
    if media_asset_id:
        media = await db[C.media_assets].find_one(
            {"media_asset_id": media_asset_id},
            projection={"storage": 1, "_id": 0},
        )
        key = (media or {}).get("storage", {}).get("object_key")
        if key:
            image_url = await get_storage().presigned_get_url(
                key, expires_in=3600
            )
    return FabricPublic(
        fabric_id=doc["fabric_id"],
        name=doc["name"],
        description=doc.get("description", ""),
        color_family=doc["color_family"],
        cost_per_yard_amount=int(doc["cost_per_yard_amount"]),
        currency=doc.get("currency", "USD"),
        suitable_for=doc.get("suitable_for", []),
        swatch=FabricSwatch(
            gradient=swatch_in.get("gradient"),
            image_url=image_url,
        ),
        weight=doc.get("weight", "medium"),
        finish=doc.get("finish"),
    )


@router.get(
    "/fabrics",
    response_model=FabricListResponse,
    summary="List active fabrics for the Design Me picker",
)
async def list_fabrics(db: DbDep) -> FabricListResponse:
    docs = await _list_active_fabrics(db)
    items = [await _hydrated_public_fabric(db, d) for d in docs]
    return FabricListResponse(items=items)


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
