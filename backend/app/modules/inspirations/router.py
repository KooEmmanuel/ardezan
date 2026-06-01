"""Public read-only inspirations route.

The customer-facing Bespoke grid and the Design Me inspiration row
both call ``GET /api/v1/inspirations``. Returned items are active
only, sorted by an admin-set ``sort_order`` then by name.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from app.db import C
from app.deps import DbDep
from app.modules.fabrics.pricing import Complexity
from app.modules.fabrics.schemas import PieceType
from app.storage import get_storage

router = APIRouter()


class InspirationPublic(BaseModel):
    inspiration_id: str
    fabric_id: str
    piece_type: PieceType
    complexity: Complexity
    title: str
    tagline: str
    brief: str
    fit_note: str | None = None
    # Either a signed URL to an uploaded hero photo OR a public path
    # to a static asset under ``frontend/public/bespoke/``.
    image_url: str | None = None
    gradient: str | None = None


class InspirationListResponse(BaseModel):
    items: list[InspirationPublic]


async def _to_public(
    db: AsyncIOMotorDatabase[Any], doc: dict[str, Any]
) -> InspirationPublic:
    image_url: str | None = doc.get("static_image_path")  # e.g. "/bespoke/x.png"
    media_asset_id = doc.get("image_media_asset_id")
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
    return InspirationPublic(
        inspiration_id=doc["inspiration_id"],
        fabric_id=doc["fabric_id"],
        piece_type=doc["piece_type"],
        complexity=doc["complexity"],
        title=doc["title"],
        tagline=doc.get("tagline", ""),
        brief=doc["brief"],
        fit_note=doc.get("fit_note"),
        image_url=image_url,
        gradient=doc.get("gradient"),
    )


@router.get(
    "/inspirations",
    response_model=InspirationListResponse,
    summary="List active design inspirations for Bespoke + Design Me",
)
async def list_inspirations(db: DbDep) -> InspirationListResponse:
    cursor = (
        db[C.design_inspirations]
        .find({"active": True}, projection={"_id": 0})
        .sort([("sort_order", 1), ("title", 1)])
    )
    docs = await cursor.to_list(None)
    items = [await _to_public(db, d) for d in docs]
    return InspirationListResponse(items=items)
