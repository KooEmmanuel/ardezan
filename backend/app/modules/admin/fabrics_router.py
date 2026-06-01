"""Admin fabric routes.

CRUD over the fabric library used by Design Me. Supports an optional
swatch image upload — when present, ``swatch.image_url`` is signed at
read time and the frontend renders the photo instead of the gradient.

Mounted at ``/api/v1/admin/fabrics``.
"""
from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Form, UploadFile, status
from pydantic import BaseModel, Field

from app.db import C
from app.deps import DbDep
from app.errors import ApiError, ErrorCode
from app.modules.admin.deps import AdminDep
from app.modules.fabrics.schemas import FabricPublic, FabricSwatch, PieceType
from app.storage import get_storage

router = APIRouter()


# ── Schemas ─────────────────────────────────────────────────────────
Weight = Literal["light", "medium", "heavy"]


class FabricAdminPublic(BaseModel):
    """Same as ``FabricPublic`` but with the ``active`` flag exposed and
    a freshly signed swatch image URL (if any)."""

    fabric_id: str
    name: str
    description: str
    color_family: str
    cost_per_yard_amount: int
    currency: str = "USD"
    suitable_for: list[PieceType] = Field(default_factory=list)
    swatch: FabricSwatch = Field(default_factory=FabricSwatch)
    weight: Weight = "medium"
    finish: str | None = None
    active: bool = True
    created_at: datetime
    updated_at: datetime


class FabricListResponse(BaseModel):
    items: list[FabricAdminPublic]


class FabricUpdate(BaseModel):
    """All fields optional — PATCH semantics."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, min_length=1, max_length=600)
    color_family: str | None = Field(default=None, min_length=1, max_length=60)
    cost_per_yard_amount: int | None = Field(default=None, ge=0, le=1_000_000)
    suitable_for: list[PieceType] | None = None
    weight: Weight | None = None
    finish: str | None = Field(default=None, max_length=60)
    gradient: str | None = Field(default=None, max_length=400)
    active: bool | None = None


# ── Helpers ─────────────────────────────────────────────────────────
def _fabric_id() -> str:
    return f"fab_{secrets.token_hex(8)}"


def _media_id() -> str:
    return f"media_{secrets.token_hex(8)}"


def _now() -> datetime:
    return datetime.now(UTC)


async def _signed_swatch_url(
    db: DbDep, fabric_doc: dict[str, Any]
) -> str | None:
    """If the fabric has an uploaded swatch image, return a fresh signed URL."""
    swatch = fabric_doc.get("swatch") or {}
    media_asset_id = swatch.get("media_asset_id")
    if not media_asset_id:
        return None
    media = await db[C.media_assets].find_one(
        {"media_asset_id": media_asset_id}, projection={"storage": 1, "_id": 0}
    )
    key = (media or {}).get("storage", {}).get("object_key")
    if not key:
        return None
    return await get_storage().presigned_get_url(key, expires_in=3600)


async def _to_admin_public(
    db: DbDep, fabric_doc: dict[str, Any]
) -> FabricAdminPublic:
    image_url = await _signed_swatch_url(db, fabric_doc)
    swatch_in = fabric_doc.get("swatch") or {}
    return FabricAdminPublic(
        fabric_id=fabric_doc["fabric_id"],
        name=fabric_doc["name"],
        description=fabric_doc.get("description", ""),
        color_family=fabric_doc["color_family"],
        cost_per_yard_amount=int(fabric_doc["cost_per_yard_amount"]),
        currency=fabric_doc.get("currency", "USD"),
        suitable_for=fabric_doc.get("suitable_for", []),
        swatch=FabricSwatch(
            gradient=swatch_in.get("gradient"),
            image_url=image_url,
        ),
        weight=fabric_doc.get("weight", "medium"),
        finish=fabric_doc.get("finish"),
        active=fabric_doc.get("active", True),
        created_at=fabric_doc["created_at"],
        updated_at=fabric_doc["updated_at"],
    )


# ── List ────────────────────────────────────────────────────────────
@router.get(
    "/fabrics",
    response_model=FabricListResponse,
    summary="List every fabric (including inactive ones)",
)
async def list_fabrics(
    db: DbDep,
    admin: AdminDep,
) -> FabricListResponse:
    cursor = db[C.fabrics].find({}, projection={"_id": 0}).sort("name", 1)
    docs = await cursor.to_list(None)
    items = [await _to_admin_public(db, d) for d in docs]
    return FabricListResponse(items=items)


# ── Read ────────────────────────────────────────────────────────────
@router.get(
    "/fabrics/{fabric_id}",
    response_model=FabricAdminPublic,
    summary="Read one fabric (admin shape)",
)
async def get_fabric(
    fabric_id: str,
    db: DbDep,
    admin: AdminDep,
) -> FabricAdminPublic:
    doc = await db[C.fabrics].find_one(
        {"fabric_id": fabric_id}, projection={"_id": 0}
    )
    if not doc:
        raise ApiError(
            ErrorCode.NOT_FOUND, f"Fabric not found: {fabric_id}", http_status=404
        )
    return await _to_admin_public(db, doc)


# ── Create ──────────────────────────────────────────────────────────
@router.post(
    "/fabrics",
    response_model=FabricAdminPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new fabric",
)
async def create_fabric(
    db: DbDep,
    admin: AdminDep,
    name: Annotated[str, Form(min_length=1, max_length=120)],
    description: Annotated[str, Form(min_length=1, max_length=600)],
    color_family: Annotated[str, Form(min_length=1, max_length=60)],
    cost_per_yard_amount: Annotated[int, Form(ge=0, le=1_000_000)],
    suitable_for: Annotated[
        str,
        Form(description="Comma-separated piece types: shirt,blouse,dress,..."),
    ],
    weight: Annotated[Weight, Form()] = "medium",
    finish: Annotated[str | None, Form(max_length=60)] = None,
    gradient: Annotated[str | None, Form(max_length=400)] = None,
    swatch_image: Annotated[UploadFile | None, File()] = None,
    active: Annotated[bool, Form()] = True,
) -> FabricAdminPublic:
    # Parse + validate piece list.
    pieces = [p.strip() for p in suitable_for.split(",") if p.strip()]
    if not pieces:
        raise ApiError(
            ErrorCode.VALIDATION_ERROR,
            "suitable_for must list at least one piece type.",
            http_status=400,
        )

    fabric_id = _fabric_id()
    now = _now()
    swatch_doc: dict[str, Any] = {}
    if gradient:
        swatch_doc["gradient"] = gradient

    # Optional swatch photo upload — stored under ``fabrics/swatches/``.
    if swatch_image is not None and swatch_image.filename:
        body = await swatch_image.read()
        if len(body) > 8 * 1024 * 1024:
            raise ApiError(
                ErrorCode.VALIDATION_ERROR,
                "Swatch image is too large (8 MB max).",
                http_status=400,
            )
        media_asset_id = _media_id()
        ext = _guess_ext(swatch_image.content_type or "")
        key = f"fabrics/swatches/{media_asset_id}{ext}"
        written = await get_storage().put_object(
            key,
            body,
            content_type=swatch_image.content_type or "application/octet-stream",
            metadata={"media_asset_id": media_asset_id, "owner_type": "fabric"},
        )
        await db[C.media_assets].insert_one(
            {
                "media_asset_id": media_asset_id,
                "owner_type": "fabric",
                "owner_id": fabric_id,
                "purpose": "fabric_swatch",
                "storage": {
                    "bucket": "",
                    "object_key": written,
                    "content_type": swatch_image.content_type,
                    "byte_size": len(body),
                },
                "access": {"visibility": "private", "signed_url_required": True},
                "retention": {
                    "policy": "registered_until_deleted",
                    "expires_at": None,
                    "deleted_at": None,
                },
                "provenance": {"ai_generated": False, "provider": None},
                "created_at": now,
                "updated_at": now,
            }
        )
        swatch_doc["media_asset_id"] = media_asset_id

    fabric_doc = {
        "fabric_id": fabric_id,
        "name": name.strip(),
        "description": description.strip(),
        "color_family": color_family.strip(),
        "cost_per_yard_amount": int(cost_per_yard_amount),
        "currency": "USD",
        "suitable_for": pieces,
        "swatch": swatch_doc,
        "weight": weight,
        "finish": (finish.strip() if finish else None),
        "active": bool(active),
        "created_at": now,
        "updated_at": now,
    }
    await db[C.fabrics].insert_one(fabric_doc)
    return await _to_admin_public(db, fabric_doc)


# ── Update ──────────────────────────────────────────────────────────
@router.patch(
    "/fabrics/{fabric_id}",
    response_model=FabricAdminPublic,
    summary="Update fabric fields (partial)",
)
async def update_fabric(
    fabric_id: str,
    body: FabricUpdate,
    db: DbDep,
    admin: AdminDep,
) -> FabricAdminPublic:
    existing = await db[C.fabrics].find_one(
        {"fabric_id": fabric_id}, projection={"_id": 0}
    )
    if not existing:
        raise ApiError(
            ErrorCode.NOT_FOUND, f"Fabric not found: {fabric_id}", http_status=404
        )

    updates: dict[str, Any] = {}
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        if field == "gradient":
            swatch = dict(existing.get("swatch") or {})
            swatch["gradient"] = value
            updates["swatch"] = swatch
        else:
            updates[field] = value
    if not updates:
        return await _to_admin_public(db, existing)

    updates["updated_at"] = _now()
    await db[C.fabrics].update_one(
        {"fabric_id": fabric_id}, {"$set": updates}
    )
    fresh = await db[C.fabrics].find_one(
        {"fabric_id": fabric_id}, projection={"_id": 0}
    )
    assert fresh is not None
    return await _to_admin_public(db, fresh)


# ── Replace swatch image ───────────────────────────────────────────
@router.post(
    "/fabrics/{fabric_id}/swatch-image",
    response_model=FabricAdminPublic,
    summary="Upload or replace the fabric's swatch image",
)
async def upload_swatch_image(
    fabric_id: str,
    db: DbDep,
    admin: AdminDep,
    swatch_image: Annotated[UploadFile, File()],
) -> FabricAdminPublic:
    existing = await db[C.fabrics].find_one(
        {"fabric_id": fabric_id}, projection={"_id": 0}
    )
    if not existing:
        raise ApiError(
            ErrorCode.NOT_FOUND, f"Fabric not found: {fabric_id}", http_status=404
        )

    body = await swatch_image.read()
    if len(body) > 8 * 1024 * 1024:
        raise ApiError(
            ErrorCode.VALIDATION_ERROR,
            "Swatch image is too large (8 MB max).",
            http_status=400,
        )

    now = _now()
    media_asset_id = _media_id()
    ext = _guess_ext(swatch_image.content_type or "")
    key = f"fabrics/swatches/{media_asset_id}{ext}"
    written = await get_storage().put_object(
        key,
        body,
        content_type=swatch_image.content_type or "application/octet-stream",
        metadata={"media_asset_id": media_asset_id, "owner_type": "fabric"},
    )
    await db[C.media_assets].insert_one(
        {
            "media_asset_id": media_asset_id,
            "owner_type": "fabric",
            "owner_id": fabric_id,
            "purpose": "fabric_swatch",
            "storage": {
                "bucket": "",
                "object_key": written,
                "content_type": swatch_image.content_type,
                "byte_size": len(body),
            },
            "access": {"visibility": "private", "signed_url_required": True},
            "retention": {
                "policy": "registered_until_deleted",
                "expires_at": None,
                "deleted_at": None,
            },
            "provenance": {"ai_generated": False, "provider": None},
            "created_at": now,
            "updated_at": now,
        }
    )
    swatch = dict(existing.get("swatch") or {})
    swatch["media_asset_id"] = media_asset_id
    await db[C.fabrics].update_one(
        {"fabric_id": fabric_id},
        {"$set": {"swatch": swatch, "updated_at": now}},
    )
    fresh = await db[C.fabrics].find_one(
        {"fabric_id": fabric_id}, projection={"_id": 0}
    )
    assert fresh is not None
    return await _to_admin_public(db, fresh)


# ── Delete ──────────────────────────────────────────────────────────
@router.delete(
    "/fabrics/{fabric_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a fabric (hard delete)",
)
async def delete_fabric(
    fabric_id: str,
    db: DbDep,
    admin: AdminDep,
) -> None:
    result = await db[C.fabrics].delete_one({"fabric_id": fabric_id})
    if result.deleted_count == 0:
        raise ApiError(
            ErrorCode.NOT_FOUND, f"Fabric not found: {fabric_id}", http_status=404
        )


def _guess_ext(content_type: str) -> str:
    ct = (content_type or "").lower()
    if "jpeg" in ct or "jpg" in ct:
        return ".jpg"
    if "png" in ct:
        return ".png"
    if "webp" in ct:
        return ".webp"
    if "heic" in ct or "heif" in ct:
        return ".heic"
    return ".bin"
