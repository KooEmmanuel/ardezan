"""Stripe webhook handler.

Hardening rules (REQ-043, REQ-074):

1. **Signature verified before any state change.** Reject with 400 if the
   ``Stripe-Signature`` header is missing or invalid.
2. **Dedupe by event id.** Insert into ``payment_events`` with a unique index
   on ``(provider, provider_event_id)``. A duplicate insert means we've
   already processed this event — short-circuit and return 200.
3. **Always respond 200 fast** once the event is recorded, even if the side
   effect fails — Stripe will retry, and the second attempt will see the
   ``payment_events`` row in ``failed`` state and retry processing.
4. **Lock via state.** Order creation is idempotent at the orders collection
   level (unique sparse index on ``checkout_session_id``).

Phase 1 events handled:
- ``payment_intent.succeeded``    → create order (via OrdersService)
- ``payment_intent.payment_failed`` → release inventory holds
- ``charge.refunded`` / ``refund.created`` / ``refund.updated`` → log only
  (refund handling in M3 admin)
- everything else: logged + ignored (200 OK)
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Header, Request, status
from fastapi.responses import JSONResponse
from pymongo.errors import DuplicateKeyError

from app.db import C, get_db
from app.errors import ApiError, ErrorCode
from app.logging_setup import get_logger
from app.modules.checkout.repository import CheckoutRepository
from app.modules.checkout.stripe_client import get_stripe_client
from app.modules.inventory.service import InventoryService
from app.modules.orders.service import OrdersService

log = get_logger(__name__)

router = APIRouter()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _payevt_id() -> str:
    return f"payevt_{secrets.token_hex(8)}"


@router.post(
    "/stripe",
    summary="Stripe webhook receiver — signature-verified, idempotent",
    status_code=200,
)
async def stripe_webhook(
    request: Request,
    stripe_signature: Annotated[
        str | None, Header(alias="Stripe-Signature")
    ] = None,
) -> JSONResponse:
    if not stripe_signature:
        raise ApiError(
            ErrorCode.WEBHOOK_INVALID_SIGNATURE,
            "Missing Stripe-Signature header.",
            http_status=400,
        )

    raw_body = await request.body()
    stripe_client = get_stripe_client()
    event = stripe_client.verify_webhook(raw_body, stripe_signature)

    return await _process_event(event)


async def _process_event(event: dict[str, Any]) -> JSONResponse:
    """Idempotent processing path. Used by both the real webhook handler and
    the dev simulate endpoint."""
    db = get_db()
    event_id = event["id"]
    event_type = event["type"]
    now = _now()

    # 1. Claim this event by inserting into payment_events. The unique index
    # on (provider, provider_event_id) ensures we don't double-process.
    payevt_doc: dict[str, Any] = {
        "payment_event_id": _payevt_id(),
        "provider": "stripe",
        "provider_event_id": event_id,
        "event_type": event_type,
        "related_order_id": None,
        "related_payment_intent_id": _extract_payment_intent_id(event),
        "status": "received",
        "received_at": now,
        "processed_at": None,
        "failure_reason": None,
    }
    try:
        await db[C.payment_events].insert_one(payevt_doc)
    except DuplicateKeyError:
        # Already seen. If the previous attempt *failed*, atomically reclaim
        # the event (status failed → received) so this retry actually
        # reprocesses it. Without this, Stripe's retries would be swallowed
        # forever and a partially-fulfilled order would never converge.
        reclaimed = await db[C.payment_events].find_one_and_update(
            {
                "provider": "stripe",
                "provider_event_id": event_id,
                "status": "failed",
            },
            {
                "$set": {
                    "status": "received",
                    "received_at": now,
                    "processed_at": None,
                    "failure_reason": None,
                }
            },
        )
        if reclaimed is None:
            log.info(
                "webhook.duplicate_event",
                provider_event_id=event_id,
                event_type=event_type,
            )
            return JSONResponse({"status": "ok", "duplicate": True})
        log.info(
            "webhook.retrying_failed_event",
            provider_event_id=event_id,
            event_type=event_type,
            previous_failure=reclaimed.get("failure_reason"),
        )

    log.info("webhook.received", event_id=event_id, event_type=event_type)

    # 2. Route by event type and run the side effect.
    try:
        result = await _dispatch(event)
    except Exception as exc:  # noqa: BLE001
        log.exception(
            "webhook.processing_failed",
            event_id=event_id,
            event_type=event_type,
            error=str(exc),
        )
        await db[C.payment_events].update_one(
            {"provider_event_id": event_id},
            {
                "$set": {
                    "status": "failed",
                    "processed_at": _now(),
                    "failure_reason": str(exc)[:500],
                }
            },
        )
        # Re-raise so Stripe retries — they'll see the failure once it's
        # transient. The status flip above also tells us we can re-attempt.
        raise

    # 3. Mark processed.
    await db[C.payment_events].update_one(
        {"provider_event_id": event_id},
        {
            "$set": {
                "status": "processed",
                "processed_at": _now(),
                "related_order_id": result.get("order_id"),
            }
        },
    )
    return JSONResponse({"status": "ok", **result})


# ── Dispatch ────────────────────────────────────────────────────────
async def _dispatch(event: dict[str, Any]) -> dict[str, Any]:
    event_type = event["type"]
    data_object = event.get("data", {}).get("object", {})

    if event_type == "payment_intent.succeeded":
        return await _handle_payment_succeeded(data_object)
    if event_type == "payment_intent.payment_failed":
        return await _handle_payment_failed(data_object)
    if event_type in {"charge.refunded", "refund.created", "refund.updated"}:
        return _handle_refund_event(event_type, data_object)

    log.info("webhook.ignored", event_type=event_type)
    return {"handled": False, "event_type": event_type}


# ── Handlers ────────────────────────────────────────────────────────
async def _handle_payment_succeeded(intent: dict[str, Any]) -> dict[str, Any]:
    db = get_db()
    payment_intent_id = intent["id"]
    metadata = intent.get("metadata", {}) or {}
    checkout_session_id = metadata.get("checkout_session_id")

    if not checkout_session_id:
        log.warning(
            "webhook.no_checkout_session",
            payment_intent_id=payment_intent_id,
            reason="payment_intent has no checkout_session_id metadata",
        )
        return {"handled": False, "reason": "no_checkout_session_id_in_metadata"}

    service = OrdersService(db)
    order = await service.create_from_checkout(
        checkout_session_id,
        stripe_payment_intent_id=payment_intent_id,
        paid_amount=intent.get("amount_received") or intent.get("amount"),
        paid_currency=intent.get("currency"),
    )
    return {
        "handled": True,
        "order_id": order.order_id,
        "order_number": order.order_number,
        "checkout_session_id": checkout_session_id,
    }


async def _handle_payment_failed(intent: dict[str, Any]) -> dict[str, Any]:
    db = get_db()
    payment_intent_id = intent["id"]
    metadata = intent.get("metadata", {}) or {}
    checkout_session_id = metadata.get("checkout_session_id")

    if not checkout_session_id:
        log.warning(
            "webhook.payment_failed_no_session",
            payment_intent_id=payment_intent_id,
        )
        return {"handled": False, "reason": "no_checkout_session_id_in_metadata"}

    # Guard against out-of-order delivery: a late failure event from an
    # earlier card attempt must not clobber a session that has since been
    # paid (or otherwise closed).
    checkout_repo = CheckoutRepository(db)
    session = await checkout_repo.find_by_id(checkout_session_id)
    if session and session.get("status") not in {"open", "failed"}:
        log.info(
            "webhook.payment_failed_ignored",
            checkout_session_id=checkout_session_id,
            payment_intent_id=payment_intent_id,
            session_status=session.get("status"),
        )
        return {
            "handled": False,
            "reason": f"session_status_{session.get('status')}",
        }

    # Release inventory holds and mark the session failed so the customer can
    # retry. Repeated failures are safe — release_checkout only acts on active
    # holds.
    inv_service = InventoryService(db)
    released = await inv_service.release_checkout(checkout_session_id)

    await checkout_repo.update_status(
        checkout_session_id, status="failed", now=_now()
    )

    log.info(
        "webhook.payment_failed",
        checkout_session_id=checkout_session_id,
        payment_intent_id=payment_intent_id,
        holds_released=released,
    )
    return {
        "handled": True,
        "checkout_session_id": checkout_session_id,
        "holds_released": released,
    }


def _handle_refund_event(event_type: str, data: dict[str, Any]) -> dict[str, Any]:
    # Refund logic lives in the M3 Admin module. We acknowledge the event so
    # Stripe stops retrying; full handling lands when refunds are admin-driven.
    log.info(
        "webhook.refund_event_logged_only",
        event_type=event_type,
        id=data.get("id"),
        amount=data.get("amount"),
    )
    return {"handled": False, "event_type": event_type, "reason": "deferred_to_m3"}


def _extract_payment_intent_id(event: dict[str, Any]) -> str | None:
    obj = event.get("data", {}).get("object", {}) or {}
    if event["type"].startswith("payment_intent."):
        return obj.get("id")
    if event["type"].startswith("charge.") or event["type"].startswith("refund."):
        return obj.get("payment_intent")
    return None


# Re-exported for the dev simulate endpoint in app.main.
process_event = _process_event
