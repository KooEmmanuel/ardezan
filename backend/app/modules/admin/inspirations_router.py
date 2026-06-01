"""Admin inspirations CRUD + hero image upload.

Mounted at ``/api/v1/admin/inspirations``.
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
from app.modules.fabrics.schemas import PieceType
from app.storage import get_storage

router = APIRouter()


Complexity = Literal["simple", "standard", "intricate"]


class InspirationAdminPublic(BaseModel):
    inspiration_id: str
    fabric_id: str
    piece_type: PieceType
    complexity: Complexity
    title: str
    tagline: str
    brief: str
    fit_note: str | None = None
    image_url: str | None = None
    gradient: str | None = None
    active: bool = True
    sort_order: int = 100
    created_at: datetime
    updated_at: datetime


class InspirationListResponse(BaseModel):
    items: list[InspirationAdminPublic]


class InspirationUpdate(BaseModel):
    fabric_id: str | None = None
    piece_type: PieceType | None = None
    complexity: Complexity | None = None
    title: str | None = Field(default=None, min_length=1, max_length=120)
    tagline: str | None = Field(default=None, max_length=200)
    brief: str | None = Field(default=None, min_length=8, max_length=600)
    fit_note: str | None = Field(default=None, max_length=300)
    gradient: str | None = Field(default=None, max_length=400)
    active: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=10000)


def _inspiration_id() -> str:
    return f"ins_{secrets.token_hex(8)}"


def _media_id() -> str:
    return f"media_{secrets.token_hex(8)}"


def _now() -> datetime:
    return datetime.now(UTC)


def _guess_ext(content_type: str) -> str:
    ct = (content_type or "").lower()
    if "jpeg" in ct or "jpg" in ct:
        return ".jpg"
    if "png" in ct:
        return ".png"
    if "webp" in ct:
        return ".webp"
    return ".bin"


async def _hero_image_url(db: DbDep, doc: dict[str, Any]) -> str | None:
    if doc.get("static_image_path"):
        return doc["static_image_path"]
    media_asset_id = doc.get("image_media_asset_id")
    if not media_asset_id:
        return None
    media = await db[C.media_assets].find_one(
        {"media_asset_id": media_asset_id},
        projection={"storage": 1, "_id": 0},
    )
    key = (media or {}).get("storage", {}).get("object_key")
    if not key:
        return None
    return await get_storage().presigned_get_url(key, expires_in=3600)


async def _to_public(db: DbDep, doc: dict[str, Any]) -> InspirationAdminPublic:
    return InspirationAdminPublic(
        inspiration_id=doc["inspiration_id"],
        fabric_id=doc["fabric_id"],
        piece_type=doc["piece_type"],
        complexity=doc["complexity"],
        title=doc["title"],
        tagline=doc.get("tagline", ""),
        brief=doc["brief"],
        fit_note=doc.get("fit_note"),
        image_url=await _hero_image_url(db, doc),
        gradient=doc.get("gradient"),
        active=doc.get("active", True),
        sort_order=doc.get("sort_order", 100),
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )


@router.get(
    "/inspirations",
    response_model=InspirationListResponse,
    summary="List every inspiration (incl. inactive)",
)
async def list_inspirations(db: DbDep, admin: AdminDep) -> InspirationListResponse:
    cursor = (
        db[C.design_inspirations]
        .find({}, projection={"_id": 0})
        .sort([("sort_order", 1), ("title", 1)])
    )
    docs = await cursor.to_list(None)
    items = [await _to_public(db, d) for d in docs]
    return InspirationListResponse(items=items)


@router.get(
    "/inspirations/{inspiration_id}",
    response_model=InspirationAdminPublic,
    summary="Read one inspiration",
)
async def get_inspiration(
    inspiration_id: str, db: DbDep, admin: AdminDep
) -> InspirationAdminPublic:
    doc = await db[C.design_inspirations].find_one(
        {"inspiration_id": inspiration_id}, projection={"_id": 0}
    )
    if not doc:
        raise ApiError(
            ErrorCode.NOT_FOUND,
            f"Inspiration not found: {inspiration_id}",
            http_status=404,
        )
    return await _to_public(db, doc)


@router.post(
    "/inspirations",
    response_model=InspirationAdminPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new inspiration",
)
async def create_inspiration(
    db: DbDep,
    admin: AdminDep,
    fabric_id: Annotated[str, Form()],
    piece_type: Annotated[PieceType, Form()],
    complexity: Annotated[Complexity, Form()],
    title: Annotated[str, Form(min_length=1, max_length=120)],
    brief: Annotated[str, Form(min_length=8, max_length=600)],
    tagline: Annotated[str, Form(max_length=200)] = "",
    fit_note: Annotated[str | None, Form(max_length=300)] = None,
    gradient: Annotated[str | None, Form(max_length=400)] = None,
    sort_order: Annotated[int, Form(ge=0, le=10000)] = 100,
    active: Annotated[bool, Form()] = True,
    hero_image: Annotated[UploadFile | None, File()] = None,
) -> InspirationAdminPublic:
    # Verify the fabric exists.
    fabric = await db[C.fabrics].find_one({"fabric_id": fabric_id})
    if not fabric:
        raise ApiError(
            ErrorCode.VALIDATION_ERROR,
            f"Fabric not found: {fabric_id}",
            http_status=400,
        )

    inspiration_id = _inspiration_id()
    now = _now()
    image_media_asset_id: str | None = None

    if hero_image is not None and hero_image.filename:
        body = await hero_image.read()
        if len(body) > 8 * 1024 * 1024:
            raise ApiError(
                ErrorCode.VALIDATION_ERROR,
                "Hero image is too large (8 MB max).",
                http_status=400,
            )
        image_media_asset_id = _media_id()
        ext = _guess_ext(hero_image.content_type or "")
        key = f"inspirations/{image_media_asset_id}{ext}"
        written = await get_storage().put_object(
            key,
            body,
            content_type=hero_image.content_type or "application/octet-stream",
            metadata={"owner_type": "inspiration"},
        )
        await db[C.media_assets].insert_one(
            {
                "media_asset_id": image_media_asset_id,
                "owner_type": "inspiration",
                "owner_id": inspiration_id,
                "purpose": "inspiration_hero",
                "storage": {
                    "bucket": "",
                    "object_key": written,
                    "content_type": hero_image.content_type,
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

    doc = {
        "inspiration_id": inspiration_id,
        "fabric_id": fabric_id,
        "piece_type": piece_type,
        "complexity": complexity,
        "title": title.strip(),
        "tagline": tagline.strip(),
        "brief": brief.strip(),
        "fit_note": fit_note.strip() if fit_note else None,
        "gradient": gradient.strip() if gradient else None,
        "image_media_asset_id": image_media_asset_id,
        "static_image_path": None,
        "active": bool(active),
        "sort_order": int(sort_order),
        "created_at": now,
        "updated_at": now,
    }
    await db[C.design_inspirations].insert_one(doc)
    return await _to_public(db, doc)


@router.patch(
    "/inspirations/{inspiration_id}",
    response_model=InspirationAdminPublic,
    summary="Update an inspiration (partial)",
)
async def update_inspiration(
    inspiration_id: str,
    body: InspirationUpdate,
    db: DbDep,
    admin: AdminDep,
) -> InspirationAdminPublic:
    existing = await db[C.design_inspirations].find_one(
        {"inspiration_id": inspiration_id}, projection={"_id": 0}
    )
    if not existing:
        raise ApiError(
            ErrorCode.NOT_FOUND,
            f"Inspiration not found: {inspiration_id}",
            http_status=404,
        )

    updates: dict[str, Any] = {}
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        if isinstance(value, str):
            updates[field] = value.strip()
        else:
            updates[field] = value

    if updates.get("fabric_id"):
        fabric = await db[C.fabrics].find_one({"fabric_id": updates["fabric_id"]})
        if not fabric:
            raise ApiError(
                ErrorCode.VALIDATION_ERROR,
                f"Fabric not found: {updates['fabric_id']}",
                http_status=400,
            )

    updates["updated_at"] = _now()
    await db[C.design_inspirations].update_one(
        {"inspiration_id": inspiration_id}, {"$set": updates}
    )
    fresh = await db[C.design_inspirations].find_one(
        {"inspiration_id": inspiration_id}, projection={"_id": 0}
    )
    assert fresh is not None
    return await _to_public(db, fresh)


@router.post(
    "/inspirations/{inspiration_id}/hero-image",
    response_model=InspirationAdminPublic,
    summary="Upload or replace the inspiration's hero photo",
)
async def upload_hero_image(
    inspiration_id: str,
    db: DbDep,
    admin: AdminDep,
    hero_image: Annotated[UploadFile, File()],
) -> InspirationAdminPublic:
    existing = await db[C.design_inspirations].find_one(
        {"inspiration_id": inspiration_id}, projection={"_id": 0}
    )
    if not existing:
        raise ApiError(
            ErrorCode.NOT_FOUND,
            f"Inspiration not found: {inspiration_id}",
            http_status=404,
        )

    body = await hero_image.read()
    if len(body) > 8 * 1024 * 1024:
        raise ApiError(
            ErrorCode.VALIDATION_ERROR,
            "Hero image is too large (8 MB max).",
            http_status=400,
        )
    now = _now()
    media_asset_id = _media_id()
    ext = _guess_ext(hero_image.content_type or "")
    key = f"inspirations/{media_asset_id}{ext}"
    written = await get_storage().put_object(
        key,
        body,
        content_type=hero_image.content_type or "application/octet-stream",
        metadata={"owner_type": "inspiration"},
    )
    await db[C.media_assets].insert_one(
        {
            "media_asset_id": media_asset_id,
            "owner_type": "inspiration",
            "owner_id": inspiration_id,
            "purpose": "inspiration_hero",
            "storage": {
                "bucket": "",
                "object_key": written,
                "content_type": hero_image.content_type,
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
    await db[C.design_inspirations].update_one(
        {"inspiration_id": inspiration_id},
        {
            "$set": {
                "image_media_asset_id": media_asset_id,
                # Uploading a new photo overrides any static-path bundle.
                "static_image_path": None,
                "updated_at": now,
            }
        },
    )
    fresh = await db[C.design_inspirations].find_one(
        {"inspiration_id": inspiration_id}, projection={"_id": 0}
    )
    assert fresh is not None
    return await _to_public(db, fresh)


@router.delete(
    "/inspirations/{inspiration_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an inspiration",
)
async def delete_inspiration(
    inspiration_id: str, db: DbDep, admin: AdminDep
) -> None:
    r = await db[C.design_inspirations].delete_one(
        {"inspiration_id": inspiration_id}
    )
    if r.deleted_count == 0:
        raise ApiError(
            ErrorCode.NOT_FOUND,
            f"Inspiration not found: {inspiration_id}",
            http_status=404,
        )
