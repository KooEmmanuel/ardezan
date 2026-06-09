"""Stripe webhook tests (REQ-043, REQ-074).

The webhook must be idempotent (Stripe retries aggressively) and must verify
the signature before any state change. These tests cover:
- the dedupe-by-event-id path (a replayed event is a no-op),
- processed/failed state recording on the payment_events ledger,
- the missing-signature rejection on the HTTP route,
- the payment-intent-id extraction helper.
"""
from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

import app.modules.webhooks.router as wh
from app.db import C
from app.modules.webhooks.router import _extract_payment_intent_id, process_event


def _event(event_id: str = "evt_1", event_type: str = "customer.created") -> dict[str, Any]:
    # An intentionally "ignored" event type so dispatch is a no-op and we can
    # isolate the dedupe/ledger behaviour from order-creation side effects.
    return {"id": event_id, "type": event_type, "data": {"object": {"id": "obj_1"}}}


async def test_duplicate_event_is_idempotent(mock_db: Any) -> None:
    first = await process_event(_event("evt_dupe"))
    second = await process_event(_event("evt_dupe"))

    assert first.body  # processed normally
    body2 = bytes(second.body).decode()
    assert '"duplicate":true' in body2.replace(" ", "")

    # Exactly one ledger row exists for the event.
    count = await mock_db[C.payment_events].count_documents(
        {"provider_event_id": "evt_dupe"}
    )
    assert count == 1


async def test_processed_event_marked_processed(mock_db: Any) -> None:
    await process_event(_event("evt_ok"))
    doc = await mock_db[C.payment_events].find_one({"provider_event_id": "evt_ok"})
    assert doc is not None
    assert doc["status"] == "processed"
    assert doc["processed_at"] is not None


async def test_failed_dispatch_marks_failed_and_reraises(
    mock_db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _boom(_event: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("simulated side-effect failure")

    monkeypatch.setattr(wh, "_dispatch", _boom)

    with pytest.raises(RuntimeError):
        await process_event(_event("evt_fail"))

    doc = await mock_db[C.payment_events].find_one({"provider_event_id": "evt_fail"})
    assert doc is not None
    assert doc["status"] == "failed"
    assert "simulated side-effect failure" in doc["failure_reason"]


async def test_failed_event_is_reprocessed_on_retry(
    mock_db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stripe retries a failed delivery with the *same* event id. The retry
    must reclaim the failed ledger row and reprocess instead of being
    swallowed as a duplicate."""

    async def _boom(_event: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("transient failure")

    monkeypatch.setattr(wh, "_dispatch", _boom)
    with pytest.raises(RuntimeError):
        await process_event(_event("evt_retry"))

    doc = await mock_db[C.payment_events].find_one({"provider_event_id": "evt_retry"})
    assert doc["status"] == "failed"

    # Second delivery: dispatch now succeeds → event ends up processed.
    monkeypatch.undo()
    result = await process_event(_event("evt_retry"))
    body = bytes(result.body).decode()
    assert '"duplicate":true' not in body.replace(" ", "")

    doc = await mock_db[C.payment_events].find_one({"provider_event_id": "evt_retry"})
    assert doc["status"] == "processed"
    assert doc["failure_reason"] is None

    # Still exactly one ledger row.
    count = await mock_db[C.payment_events].count_documents(
        {"provider_event_id": "evt_retry"}
    )
    assert count == 1


async def test_webhook_route_rejects_missing_signature(mock_db: Any) -> None:
    # Hits the real route; no Stripe-Signature header → 400 before any work.
    from app.main import app

    client = TestClient(app)
    resp = client.post("/api/v1/webhooks/stripe", content=b"{}")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "WEBHOOK_INVALID_SIGNATURE"


# ── Pure helper ─────────────────────────────────────────────────────
def test_extract_payment_intent_id() -> None:
    pi = {
        "id": "evt",
        "type": "payment_intent.succeeded",
        "data": {"object": {"id": "pi_123"}},
    }
    assert _extract_payment_intent_id(pi) == "pi_123"

    charge = {
        "id": "evt",
        "type": "charge.refunded",
        "data": {"object": {"id": "ch_1", "payment_intent": "pi_456"}},
    }
    assert _extract_payment_intent_id(charge) == "pi_456"

    other = {"id": "evt", "type": "customer.created", "data": {"object": {}}}
    assert _extract_payment_intent_id(other) is None
