"""Checkout routes (per API.md §8)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header

from app.deps import DbDep
from app.errors import ApiError, ErrorCode
from app.modules.checkout.schemas import (
    CheckoutSessionPublic,
    CreateCheckoutSessionRequest,
)
from app.modules.checkout.service import CheckoutService
from app.modules.customers.deps import OptionalCustomerDep, ensure_email_verified

router = APIRouter()


def get_service(db: DbDep) -> CheckoutService:
    return CheckoutService(db)


ServiceDep = Annotated[CheckoutService, Depends(get_service)]
IdempotencyKey = Annotated[
    str | None,
    Header(alias="Idempotency-Key", description="Required client-generated dedup key"),
]


@router.post(
    "/sessions",
    response_model=CheckoutSessionPublic,
    summary="Create a checkout session and a Stripe PaymentIntent",
    status_code=201,
)
async def create_session(
    body: CreateCheckoutSessionRequest,
    service: ServiceDep,
    customer: OptionalCustomerDep,
    idempotency_key: IdempotencyKey = None,
) -> CheckoutSessionPublic:
    """Required ``Idempotency-Key`` header per API.md §4.2.

    Revalidates the cart, reserves inventory atomically, creates the Stripe
    PaymentIntent, and persists the checkout session. The same idempotency
    key returns the same session (and the same Stripe PaymentIntent) — safe
    to retry from the browser.

    A signed-in customer must have a verified email before checking out; the
    resulting order is linked to their account. Guests (no session) check out
    with the ``guest_email`` on the request body and are unaffected.
    """
    if not idempotency_key:
        raise ApiError(
            ErrorCode.VALIDATION_ERROR,
            "Missing required Idempotency-Key header.",
            http_status=400,
        )
    customer_id: str | None = None
    if customer is not None:
        ensure_email_verified(customer)
        customer_id = customer["customer_id"]
    return await service.create_session(
        body, idempotency_key=idempotency_key, customer_id=customer_id
    )


@router.get(
    "/sessions/{checkout_session_id}",
    response_model=CheckoutSessionPublic,
    summary="Read a checkout session (without re-issuing the client secret)",
)
async def get_session(
    checkout_session_id: str,
    service: ServiceDep,
) -> CheckoutSessionPublic:
    return await service.get_session(checkout_session_id)


@router.post(
    "/sessions/{checkout_session_id}/cancel",
    response_model=CheckoutSessionPublic,
    summary="Cancel an open checkout session — releases inventory holds",
)
async def cancel_session(
    checkout_session_id: str,
    service: ServiceDep,
) -> CheckoutSessionPublic:
    return await service.cancel_session(checkout_session_id)
