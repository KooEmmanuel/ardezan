"""Design Me routes.

- ``POST /design-sessions``  — multipart upload, renders synchronously.
- ``GET  /design-sessions/{id}`` — read with a fresh signed image URL.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile

from app.deps import DbDep
from app.modules.customers.deps import CustomerDep, OptionalCustomerDep
from app.modules.design.schemas import (
    DesignInputs,
    DesignSessionCreateResponse,
    DesignSessionListItem,
    DesignSessionListResponse,
    DesignSessionPublic,
)
from app.modules.design.service import DesignService
from app.modules.fabrics.pricing import CostBreakdown
from app.modules.fabrics.schemas import PieceType
from app.rate_limit import enforce_upload_fingerprint, rate_limit_try_on_upload

router = APIRouter()


def get_service(db: DbDep) -> DesignService:
    return DesignService(db)


ServiceDep = Annotated[DesignService, Depends(get_service)]


@router.post(
    "/design-sessions",
    response_model=DesignSessionCreateResponse,
    summary="Create a custom-design session — uploads a photo and renders it",
    status_code=201,
    dependencies=[Depends(rate_limit_try_on_upload)],
)
async def create_design_session(
    request: Request,
    service: ServiceDep,
    customer: OptionalCustomerDep,
    photo: Annotated[UploadFile, File(description="Full-body photo (JPEG/PNG/WebP/HEIC)")],
    fabric_id: Annotated[str, Form()],
    piece_type: Annotated[str, Form()],
    brief: Annotated[str, Form()],
    complexity: Annotated[str, Form()] = "standard",
    fit_note: Annotated[str | None, Form()] = None,
    age_confirmed: Annotated[bool, Form()] = False,
    anonymous_session_id: Annotated[str | None, Form()] = None,
) -> DesignSessionCreateResponse:
    if anonymous_session_id:
        await enforce_upload_fingerprint(request, anonymous_session_id)

    body = await photo.read()
    inputs = DesignInputs(
        fabric_id=fabric_id,
        piece_type=piece_type,  # type: ignore[arg-type]
        complexity=complexity,  # type: ignore[arg-type]
        brief=brief,
        fit_note=fit_note,
    )
    return await service.create_session(
        photo_bytes=body,
        content_type=photo.content_type or "application/octet-stream",
        inputs=inputs,
        customer_id=(customer or {}).get("customer_id"),
        anonymous_session_id=anonymous_session_id,
        age_confirmed=age_confirmed,
    )


@router.get(
    "/account/designs",
    response_model=DesignSessionListResponse,
    summary="The signed-in customer's design sessions, newest first",
)
async def list_my_designs(
    customer: CustomerDep,
    service: ServiceDep,
    limit: Annotated[int, Query(ge=1, le=60)] = 24,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DesignSessionListResponse:
    items, total = await service.list_for_customer(
        customer["customer_id"], limit=limit, offset=offset
    )
    return DesignSessionListResponse(
        items=[DesignSessionListItem(**i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/design-sessions/{design_session_id}",
    response_model=DesignSessionPublic,
    summary="Read a design session with a freshly signed image URL",
)
async def read_design_session(
    design_session_id: str,
    service: ServiceDep,
) -> DesignSessionPublic:
    raw = await service.get_public(design_session_id)
    return DesignSessionPublic(
        design_session_id=raw["design_session_id"],
        status=raw["status"],
        fabric=raw["fabric_snapshot"],
        piece_type=raw["piece_type"],
        complexity=raw["complexity"],
        brief=raw["brief"],
        fit_note=raw.get("fit_note"),
        estimate=CostBreakdown(**raw["estimate"]),
        image_url=raw.get("image_url"),
        failure_reason=raw.get("failure_reason"),
        created_at=raw["created_at"],
        updated_at=raw["updated_at"],
    )
