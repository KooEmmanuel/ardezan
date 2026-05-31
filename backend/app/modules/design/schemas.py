"""Design Me schemas.

A ``DesignSession`` is the record of one custom-design request: the
photo, the chosen fabric, the piece type + brief, the generated image,
and the locked-in estimate. It's the unit the tailor queue consumes
after checkout.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.modules.fabrics.pricing import Complexity, CostBreakdown
from app.modules.fabrics.schemas import PieceType


DesignStatus = Literal["draft", "ready", "failed"]


# Inputs the customer sends with ``POST /design-sessions``. The photo
# rides as a separate multipart field — see the router.
class DesignInputs(BaseModel):
    fabric_id: str
    piece_type: PieceType
    complexity: Complexity = "standard"
    brief: str = Field(
        ...,
        min_length=8,
        max_length=600,
        description=(
            "Free-text description of the piece. Fed into the AI prompt and "
            "shown to the tailor verbatim — short, specific phrasings work best."
        ),
    )
    fit_note: str | None = Field(
        default=None,
        max_length=300,
        description="Optional fit guidance (e.g. 'relaxed', 'tailored at the waist').",
    )


# Snapshot of the fabric at the moment the session was created. We
# duplicate this onto the session doc so a later price change on the
# fabric library doesn't retroactively re-quote in-flight designs.
class FabricSnapshot(BaseModel):
    fabric_id: str
    name: str
    color_family: str
    cost_per_yard_amount: int
    currency: str = "USD"
    weight: str
    finish: str | None = None


class DesignSessionPublic(BaseModel):
    design_session_id: str
    status: DesignStatus
    fabric: FabricSnapshot
    piece_type: PieceType
    complexity: Complexity
    brief: str
    fit_note: str | None = None
    estimate: CostBreakdown
    image_url: str | None = None  # signed URL for the generated render
    failure_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class DesignSessionCreateResponse(BaseModel):
    """What the customer's browser gets after the synchronous create call.

    For the hackathon we keep this fully synchronous — the customer
    waits ~10-15s while the image renders. If we later move to a queue,
    we'd return a job id here instead.
    """

    design_session_id: str
    status: DesignStatus
    estimate: CostBreakdown
    image_url: str | None = None
    failure_reason: str | None = None


class DesignSessionListItem(BaseModel):
    """Compact shape used by ``GET /account/designs``.

    The activity hub renders one tile per design — title, fabric name,
    estimate, and a freshly-signed image URL so the grid can drop the
    image straight into ``<img src=>``.
    """

    design_session_id: str
    status: DesignStatus
    title: str  # synthesised: "Custom <piece> in <fabric>"
    fabric_name: str
    piece_type: PieceType
    image_url: str | None = None
    total_amount: int
    currency: str
    created_at: datetime


class DesignSessionListResponse(BaseModel):
    items: list[DesignSessionListItem]
    total: int
    limit: int
    offset: int
