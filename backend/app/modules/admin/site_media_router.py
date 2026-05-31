"""Admin endpoints for branded UI images.

Companion to ``app/modules/site/router.py`` — the public side. Here the
owner can replace any known slot's image with an AI-generated one. Each
replacement marks the prior media as deleted (retention sweeper cleans
storage) and writes an audit log entry.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.deps import DbDep
from app.modules.admin.deps import AdminDep
from app.modules.admin.media_service import AdminMediaService
from app.modules.site.router import KNOWN_SLOTS

router = APIRouter()


def get_media_service(db: DbDep) -> AdminMediaService:
    return AdminMediaService(db)


MediaServiceDep = Annotated[AdminMediaService, Depends(get_media_service)]


class SiteMediaGenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=20, max_length=4000)


class SiteMediaGenerateResponse(BaseModel):
    slot_name: str
    media_asset_id: str
    object_key: str


@router.post(
    "/site-media/{slot_name}/ai-generate",
    status_code=status.HTTP_201_CREATED,
    response_model=SiteMediaGenerateResponse,
    summary="Generate a branded image for a UI slot via Gemini and persist it",
)
async def ai_generate_site_media(
    slot_name: str,
    body: Annotated[SiteMediaGenerateRequest, Body()],
    media_service: MediaServiceDep,
    admin: AdminDep,
) -> SiteMediaGenerateResponse:
    if slot_name not in KNOWN_SLOTS:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": f"Unknown slot '{slot_name}'.",
                    "details": {"known_slots": list(KNOWN_SLOTS)},
                }
            },
        )
    result = await media_service.attach_site_media_ai(
        slot_name=slot_name,
        prompt=body.prompt,
        admin=admin,
    )
    return SiteMediaGenerateResponse(
        slot_name=slot_name,
        media_asset_id=result["media_asset_id"],
        object_key=result["storage"]["object_key"],
    )
