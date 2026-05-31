"""Fitting Room + saved-photo + body-profile routes (per API.md §10.4).

All endpoints require a customer session. Mounted at ``/api/v1`` so paths
read naturally: ``/account/fitting-room/...`` and ``/account/saved-photo``.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.deps import DbDep
from app.modules.customers.deps import CustomerDep, VerifiedCustomerDep
from app.modules.try_on.account_schemas import (
    BodyProfileOptInRequest,
    BodyProfileStatus,
    FittingRoomListResponse,
    FittingRoomResultCard,
    FittingRoomSessionDetail,
    FittingRoomSessionListItem,
    SavedPhotoOptInRequest,
    SavedPhotoStatus,
)
from app.modules.try_on.account_service import FittingRoomService

router = APIRouter()


def get_service(db: DbDep) -> FittingRoomService:
    return FittingRoomService(db)


ServiceDep = Annotated[FittingRoomService, Depends(get_service)]


# ── Fitting Room ────────────────────────────────────────────────────
@router.get(
    "/account/fitting-room",
    response_model=FittingRoomListResponse,
    summary="My past try-on sessions",
)
async def list_sessions(
    customer: CustomerDep,
    service: ServiceDep,
    limit: Annotated[int, Query(ge=1, le=60)] = 24,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> FittingRoomListResponse:
    items, total = await service.list_for_customer(
        customer["customer_id"], limit=limit, offset=offset
    )
    return FittingRoomListResponse(
        items=[FittingRoomSessionListItem(**i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/account/fitting-room/{try_on_session_id}",
    response_model=FittingRoomSessionDetail,
    summary="One past session in full — cards with fresh signed image URLs",
)
async def get_session(
    try_on_session_id: str,
    customer: CustomerDep,
    service: ServiceDep,
) -> FittingRoomSessionDetail:
    raw = await service.get_for_customer(try_on_session_id, customer["customer_id"])
    return FittingRoomSessionDetail(
        try_on_session_id=raw["try_on_session_id"],
        source=raw["source"],
        status=raw["status"],
        optional_inputs=raw.get("optional_inputs") or {},
        body_profile_snapshot=raw.get("body_profile_snapshot"),
        result_cards=[FittingRoomResultCard(**c) for c in raw.get("result_cards", [])],
        created_at=raw["created_at"],
        updated_at=raw["updated_at"],
    )


@router.delete(
    "/account/fitting-room/{try_on_session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a session and cascade to its generated images",
)
async def delete_session(
    try_on_session_id: str,
    customer: CustomerDep,
    service: ServiceDep,
) -> None:
    await service.delete_for_customer(try_on_session_id, customer["customer_id"])


# ── Saved photo ─────────────────────────────────────────────────────
@router.get(
    "/account/saved-photo",
    response_model=SavedPhotoStatus,
    summary="Current saved-photo status",
)
async def saved_photo_status(
    customer: CustomerDep,
    service: ServiceDep,
) -> SavedPhotoStatus:
    return SavedPhotoStatus(**await service.saved_photo_status(customer["customer_id"]))


@router.post(
    "/account/saved-photo",
    response_model=SavedPhotoStatus,
    status_code=status.HTTP_201_CREATED,
    summary="Opt in to keep a try-on session's photo for future try-ons",
)
async def opt_in_saved_photo(
    body: SavedPhotoOptInRequest,
    customer: VerifiedCustomerDep,
    service: ServiceDep,
) -> SavedPhotoStatus:
    return SavedPhotoStatus(
        **await service.opt_in_saved_photo(
            customer["customer_id"],
            try_on_session_id=body.try_on_session_id,
            consent_version=body.consent_version,
        )
    )


@router.delete(
    "/account/saved-photo",
    response_model=SavedPhotoStatus,
    summary="Withdraw saved-photo consent — flips retention back to disposable",
)
async def delete_saved_photo(
    customer: CustomerDep,
    service: ServiceDep,
) -> SavedPhotoStatus:
    return SavedPhotoStatus(
        **await service.delete_saved_photo(customer["customer_id"])
    )


# ── Body profile ────────────────────────────────────────────────────
@router.get(
    "/account/body-profile",
    response_model=BodyProfileStatus,
    summary="Current saved body-profile status",
)
async def body_profile_status(
    customer: CustomerDep,
    service: ServiceDep,
) -> BodyProfileStatus:
    return BodyProfileStatus(**await service.body_profile_status(customer["customer_id"]))


@router.post(
    "/account/body-profile",
    response_model=BodyProfileStatus,
    status_code=status.HTTP_201_CREATED,
    summary="Snapshot a session's BodyProfile onto the customer (opt-in)",
)
async def opt_in_body_profile(
    body: BodyProfileOptInRequest,
    customer: VerifiedCustomerDep,
    service: ServiceDep,
) -> BodyProfileStatus:
    return BodyProfileStatus(
        **await service.opt_in_body_profile(
            customer["customer_id"], try_on_session_id=body.try_on_session_id
        )
    )


@router.delete(
    "/account/body-profile",
    response_model=BodyProfileStatus,
    summary="Forget the saved body profile",
)
async def delete_body_profile(
    customer: CustomerDep,
    service: ServiceDep,
) -> BodyProfileStatus:
    return BodyProfileStatus(
        **await service.delete_body_profile(customer["customer_id"])
    )
