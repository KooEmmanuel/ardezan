"""Fitting Room + saved-photo + body-profile schemas (per API.md §10.4)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ── Fitting Room list ───────────────────────────────────────────────
class FittingRoomSessionListItem(BaseModel):
    """One past session as shown in the Fitting Room grid."""

    try_on_session_id: str
    source: str
    status: str
    created_at: datetime
    result_card_count: int
    representative_image_url: str | None = None
    representative_outfit_name: str | None = None


class FittingRoomListResponse(BaseModel):
    items: list[FittingRoomSessionListItem]
    total: int
    limit: int
    offset: int


# ── Single session detail ───────────────────────────────────────────
class FittingRoomResultCard(BaseModel):
    """A result card, including a freshly signed image URL."""

    card_id: str
    outfit_name: str | None = None
    rationale: str | None = None
    generated_image_id: str | None = None
    image_url: str | None = None
    total_amount: int
    currency: str
    status: str
    items: list[dict[str, Any]] = Field(default_factory=list)


class FittingRoomSessionDetail(BaseModel):
    try_on_session_id: str
    source: str
    status: str
    optional_inputs: dict[str, Any] = Field(default_factory=dict)
    body_profile_snapshot: dict[str, Any] | None = None
    result_cards: list[FittingRoomResultCard] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


# ── Saved photo ─────────────────────────────────────────────────────
class SavedPhotoOptInRequest(BaseModel):
    """Promote a session's uploaded photo to a saved-photo on the customer."""

    try_on_session_id: str
    consent_version: str = Field("v1", min_length=1, max_length=20)


class SavedPhotoStatus(BaseModel):
    opted_in: bool
    has_photo: bool
    photo_url: str | None = None
    photo_uploaded_at: datetime | None = None
    photo_consent_version: str | None = None


# ── Body profile opt-in ─────────────────────────────────────────────
class BodyProfileOptInRequest(BaseModel):
    """Snapshot the BodyProfile from this session onto the customer."""

    try_on_session_id: str


class BodyProfileStatus(BaseModel):
    opted_in: bool
    source_try_on_session_id: str | None = None
    measurements_estimate: dict[str, Any] | None = None
    fit_preference: str | None = None
    updated_at: datetime | None = None
