"""Order routes — customer-facing (M5.3) + guest order management.

Two audiences share this surface:

- **Registered customers** carry the ``customer_session`` cookie. They get
  ``GET /orders``, ``GET /orders/{id}`` (ownership-enforced), cancel,
  edit-address, and ``POST /orders/guest/{id}/claim`` (links a prior guest
  order into their account).
- **Guests** carry the signed claim token issued in the confirmation email
  (M2). They reach the same single-order surface under ``/orders/guest/``.

Admin endpoints (list-all, refunds, status transitions) live in
``app/modules/admin/orders_router.py`` and are auth-gated separately.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query

from app.deps import DbDep
from app.errors import ApiError, ErrorCode
from app.modules.checkout.schemas import Address
from app.modules.customers.deps import CustomerDep, OptionalCustomerDep
from app.modules.orders.schemas import OrderPublic
from app.modules.orders.service import OrdersService
from pydantic import BaseModel, Field

router = APIRouter()


def get_service(db: DbDep) -> OrdersService:
    return OrdersService(db)


ServiceDep = Annotated[OrdersService, Depends(get_service)]


# ── Customer order list response ─────────────────────────────────────
class OrderListResponse(BaseModel):
    items: list[OrderPublic]
    total: int
    limit: int
    offset: int


class AddressUpdateRequest(BaseModel):
    address: Address


class ClaimGuestOrderRequest(BaseModel):
    token: str = Field(..., min_length=1, max_length=1024)


# ── Customer endpoints (require customer_session) ───────────────────
@router.get(
    "",
    response_model=OrderListResponse,
    summary="My order history",
)
async def list_my_orders(
    customer: CustomerDep,
    service: ServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OrderListResponse:
    items, total = await service.list_for_customer(
        customer["customer_id"], limit=limit, offset=offset
    )
    return OrderListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post(
    "/{order_id}/cancel",
    response_model=OrderPublic,
    summary="Cancel my order pre-pack (customer or guest with claim token) — issues refund + restocks inventory",
)
async def customer_cancel_order(
    order_id: str,
    service: ServiceDep,
    customer: OptionalCustomerDep,
    token: Annotated[str | None, Query(max_length=1024)] = None,
) -> OrderPublic:
    return await service.cancel_order(
        order_id,
        customer_id=(customer or {}).get("customer_id"),
        guest_token=token,
    )


class ReturnRequestBody(BaseModel):
    reason: str = Field(..., min_length=2, max_length=400)
    line_ids: list[str] = Field(default_factory=list)


@router.post(
    "/{order_id}/return-request",
    response_model=OrderPublic,
    summary="Open a return request (customer or guest with claim token)",
)
async def customer_request_return(
    order_id: str,
    body: ReturnRequestBody,
    service: ServiceDep,
    customer: OptionalCustomerDep,
    token: Annotated[str | None, Query(max_length=1024)] = None,
) -> OrderPublic:
    return await service.request_return(
        order_id,
        reason=body.reason,
        line_ids=body.line_ids,
        customer_id=(customer or {}).get("customer_id"),
        guest_token=token,
    )


@router.patch(
    "/{order_id}/shipping-address",
    response_model=OrderPublic,
    summary="Update shipping address pre-shipment",
)
async def customer_update_shipping_address(
    order_id: str,
    body: AddressUpdateRequest,
    customer: CustomerDep,
    service: ServiceDep,
) -> OrderPublic:
    return await service.update_shipping_address_for_customer(
        order_id, customer["customer_id"], body.address
    )


# ── Single-order read — accepts either auth audience ────────────────
@router.get(
    "/{order_id}",
    response_model=OrderPublic,
    summary="Read an order (ownership-enforced if signed in; guest token otherwise)",
)
async def get_order(
    order_id: str,
    service: ServiceDep,
    customer: OptionalCustomerDep,
    token: Annotated[str | None, Query(max_length=1024)] = None,
) -> OrderPublic:
    if customer:
        return await service.get_for_customer(order_id, customer["customer_id"])
    if token:
        return await service.get_for_guest(order_id, token)
    raise ApiError(
        ErrorCode.UNAUTHENTICATED,
        "Sign in or provide a guest claim token.",
        http_status=401,
    )


# ── Lookup-by-payment-intent (post-Stripe-redirect resolution) ─────
@router.get(
    "/by-payment-intent/{payment_intent_id}",
    summary="Resolve an order by Stripe payment_intent; 404 while webhook still pending",
)
async def get_order_by_payment_intent(
    payment_intent_id: str,
    service: ServiceDep,
    customer: OptionalCustomerDep,
    token: Annotated[str | None, Query(max_length=1024)] = None,
) -> dict[str, str | None]:
    """Resolve an order by Stripe ``payment_intent_id``.

    Returns ``{order_id, status, guest_token?}`` so the pending page can
    redirect (and pass through the guest token for the confirmation
    page, when needed).

    Authorization: the ``payment_intent_id`` is itself one-shot proof of
    purchase — only the buyer sees it in the post-redirect URL Stripe
    hands back. The response is minimal (no PII, no line items); the
    detailed ``/orders/{id}`` endpoint still requires a customer cookie
    or guest token.

    Fallback: if the order hasn't materialized yet (webhook not fired —
    e.g. local dev without ``stripe listen``), pull the PaymentIntent
    from Stripe directly and run the idempotent ``create_from_checkout``
    path inline. For just-materialized guest orders, the raw guest
    token is returned in the response so the customer can navigate
    straight into ``/order-confirmation/{order_id}?token=…``.
    """
    raw_token: str | None = None
    doc = await service.find_by_payment_intent(payment_intent_id)
    if not doc:
        # Webhook hasn't (yet) fired — try to materialize from Stripe directly.
        doc, raw_token = await service.materialize_from_payment_intent(
            payment_intent_id
        )
    if not doc:
        raise ApiError(
            ErrorCode.NOT_FOUND,
            f"Order for payment_intent {payment_intent_id} not materialized yet.",
            http_status=404,
        )

    # Optional: if the caller passed a token, verify it for parity with the
    # rest of the API. Failure here is silent (we still respond) since the
    # PI ID already authorizes this minimal handshake. ``customer`` cookie
    # would be the second authentication path.
    _ = customer
    _ = token

    return {
        "order_id": doc["order_id"],
        "status": doc.get("status", "unknown"),
        "guest_token": raw_token,
    }


# ── Guest endpoints ────────────────────────────────────────────────
@router.get(
    "/guest/{order_id}",
    response_model=OrderPublic,
    summary="Guest order detail — signed token required",
)
async def get_order_guest(
    order_id: str,
    service: ServiceDep,
    token: Annotated[str, Query(min_length=1, max_length=1024)],
) -> OrderPublic:
    return await service.get_for_guest(order_id, token)


@router.post(
    "/guest/{order_id}/claim",
    response_model=OrderPublic,
    summary="Claim a guest order into the signed-in customer account",
)
async def claim_guest_order(
    order_id: str,
    body: ClaimGuestOrderRequest,
    customer: CustomerDep,
    service: ServiceDep,
) -> OrderPublic:
    return await service.claim_guest_order(
        order_id, body.token, customer["customer_id"]
    )
