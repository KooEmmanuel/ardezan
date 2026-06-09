"""Cart routes (per API.md §7).

Phase 1: stateless validation only. Anonymous carts live in the browser; the
backend re-checks price, availability, and stock. Server-side cart CRUD lands
in M5 with auth.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.deps import DbDep
from app.modules.cart.schemas import (
    FullLookAddRequest,
    FullLookAddResponse,
    RevalidateRequest,
    RevalidateResponse,
)
from app.modules.cart.service import CartService
from app.modules.customers.deps import OptionalCustomerDep

router = APIRouter()


def get_service(db: DbDep) -> CartService:
    return CartService(db)


ServiceDep = Annotated[CartService, Depends(get_service)]


@router.post(
    "/revalidate",
    response_model=RevalidateResponse,
    summary="Refresh prices, availability, and stock for an anonymous cart",
)
async def revalidate(
    body: RevalidateRequest,
    service: ServiceDep,
    customer: OptionalCustomerDep,
) -> RevalidateResponse:
    """Stateless. Called by the storefront before showing the cart or starting
    checkout. The response carries a ``status`` per line and a top-level
    ``blocks_checkout`` flag the UI uses to gate the Checkout button."""
    return await service.revalidate(
        body.lines,
        customer_id=(customer or {}).get("customer_id"),
        anonymous_session_id=body.anonymous_session_id,
    )


@router.post(
    "/full-look",
    response_model=FullLookAddResponse,
    summary="Validate a try-on full-look bundle for cart addition",
)
async def add_full_look(
    body: FullLookAddRequest,
    service: ServiceDep,
) -> FullLookAddResponse:
    """Rechecks stock at this moment (never trusting generation-time inventory
    per REQ-055). Returns lines split into ``added_lines`` (available, ready to
    merge into local cart) and ``unavailable_lines`` (UI shows swap prompt)."""
    return await service.add_full_look(
        body.items,
        try_on_session_id=body.try_on_session_id,
        card_id=body.card_id,
    )


# ── Server-side cart (M5.2 — requires customer auth) ────────────────
from app.modules.cart.schemas import (
    AddLineRequest,
    MergeCartRequest,
    ServerCart,
    UpdateLineRequest,
)
from app.modules.customers.deps import CustomerDep


@router.get(
    "",
    response_model=ServerCart,
    summary="Get the current customer's server cart (created lazily if missing)",
)
async def get_cart(
    customer: CustomerDep,
    service: ServiceDep,
) -> ServerCart:
    cart = await service.get_or_create_cart(customer["customer_id"])
    return await service.hydrate_server_cart(cart)


@router.post(
    "/lines",
    response_model=ServerCart,
    status_code=201,
    summary="Add a line to the server cart",
)
async def add_line(
    body: AddLineRequest,
    customer: CustomerDep,
    service: ServiceDep,
) -> ServerCart:
    cart = await service.add_line_to_cart(customer["customer_id"], body)
    return await service.hydrate_server_cart(cart)


@router.patch(
    "/lines/{line_id}",
    response_model=ServerCart,
    summary="Update the quantity on a cart line",
)
async def update_line(
    line_id: str,
    body: UpdateLineRequest,
    customer: CustomerDep,
    service: ServiceDep,
) -> ServerCart:
    cart = await service.update_cart_line(
        customer["customer_id"], line_id, body.quantity
    )
    return await service.hydrate_server_cart(cart)


@router.delete(
    "/lines/{line_id}",
    response_model=ServerCart,
    summary="Remove a line from the server cart",
)
async def remove_line(
    line_id: str,
    customer: CustomerDep,
    service: ServiceDep,
) -> ServerCart:
    cart = await service.remove_cart_line(customer["customer_id"], line_id)
    return await service.hydrate_server_cart(cart)


@router.post(
    "/merge",
    response_model=ServerCart,
    summary="Merge an anonymous local cart into the server cart on login (REQ-044)",
)
async def merge_cart(
    body: MergeCartRequest,
    customer: CustomerDep,
    service: ServiceDep,
) -> ServerCart:
    cart = await service.merge_anonymous_into_server(
        customer["customer_id"], body.lines
    )
    return await service.hydrate_server_cart(cart)
