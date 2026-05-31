"""Public site-media endpoint.

Returns the currently-active image for each known UI slot (hero cards,
category tiles, editorial photo, etc.) as a ``{slot_name: signed_url}`` map.
The storefront calls this once on mount and uses the URLs in ``<img src>``.

Slot definitions live in ``KNOWN_SLOTS`` — the source of truth the admin
endpoints in ``app/modules/admin/site_media_router.py`` validate against.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.db import C
from app.deps import DbDep
from app.logging_setup import get_logger
from app.storage import get_storage

log = get_logger(__name__)

# Source of truth — all UI slots the storefront knows about. Frontend reads
# these names verbatim. Adding a new slot is a one-line change here.
KNOWN_SLOTS: tuple[str, ...] = (
    # Hero cascade pool — three positions on the page rotate through the
    # pool every few seconds. Order matters: the storefront treats them as
    # a circular array. Adding hero_look_07 etc. lengthens the cycle.
    "hero_look_01",
    "hero_look_02",
    "hero_look_03",
    "hero_look_04",
    "hero_look_05",
    "hero_look_06",
    "hero_mobile",       # mobile-only hero card (single image, no cycle)
    "category_women",
    "category_men",
    "category_new",
    "category_accessories",
    "editorial_no_01",
)


class SiteMediaResponse(BaseModel):
    slots: dict[str, str | None]


router = APIRouter()

_URL_TTL_SECONDS = 60 * 60 * 24  # 24h — site media is cacheable per browser session.


async def _signed_for_slot(db: Any, slot: str) -> str | None:
    media = await db[C.media_assets].find_one(
        {
            "owner_type": "site_media",
            "owner_id": slot,
            "retention.deleted_at": None,
        },
        sort=[("created_at", -1)],
    )
    if not media:
        return None
    key = (media.get("storage") or {}).get("object_key")
    if not key:
        return None
    try:
        return await get_storage().presigned_get_url(key, expires_in=_URL_TTL_SECONDS)
    except Exception as exc:  # noqa: BLE001
        log.warning("site.sign_failed", slot=slot, error=str(exc))
        return None


@router.get(
    "/media",
    response_model=SiteMediaResponse,
    summary="Branded UI images keyed by slot name",
)
async def list_site_media(db: DbDep) -> SiteMediaResponse:
    slots: dict[str, str | None] = {}
    for slot in KNOWN_SLOTS:
        slots[slot] = await _signed_for_slot(db, slot)
    return SiteMediaResponse(slots=slots)


__all__ = ["router", "KNOWN_SLOTS"]
