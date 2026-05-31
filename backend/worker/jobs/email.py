"""Email-send jobs (async via arq).

Sending email synchronously inside the API request would couple order
creation latency to the SMTP provider. We enqueue instead — the API returns
fast, the worker handles delivery with retries.
"""
from __future__ import annotations

from typing import Any

from app.db import get_db
from app.logging_setup import get_logger
from app.modules.emails.service import EmailService

log = get_logger("worker.jobs.email")


async def send_order_confirmation(
    ctx: dict[str, Any],
    order_id: str,
    raw_guest_token: str | None = None,
) -> dict[str, Any]:
    """Send the order confirmation email for ``order_id``.

    ``raw_guest_token`` is the one-time guest-claim token to embed in the
    email's manage-order link. It's transient (job lives in Redis briefly),
    not persisted in the order document — only the SHA-256 hash is stored.
    """
    db = get_db()
    service = EmailService(db)
    result = await service.send_order_confirmation_now(
        order_id,
        raw_guest_token=raw_guest_token,
    )
    log.info("email.order_confirmation_sent", order_id=order_id, result=result)
    return result


async def send_order_shipped(
    ctx: dict[str, Any],
    order_id: str,
) -> dict[str, Any]:
    """Send the 'your order shipped' email."""
    db = get_db()
    service = EmailService(db)
    result = await service.send_order_shipped_now(order_id)
    log.info("email.order_shipped_sent", order_id=order_id, result=result)
    return result


async def send_order_delivered(
    ctx: dict[str, Any],
    order_id: str,
) -> dict[str, Any]:
    """Send the 'your order arrived' email."""
    db = get_db()
    service = EmailService(db)
    result = await service.send_order_delivered_now(order_id)
    log.info("email.order_delivered_sent", order_id=order_id, result=result)
    return result


async def send_return_requested(
    ctx: dict[str, Any],
    order_id: str,
) -> dict[str, Any]:
    """Send the 'your return is being processed' email.

    Best-effort — if the email service can't reach SMTP, we log and
    move on. The return itself is recorded on the order regardless.
    """
    db = get_db()
    service = EmailService(db)
    sender = getattr(service, "send_return_requested_now", None)
    if sender is None:
        log.info(
            "email.return_requested_skipped",
            order_id=order_id,
            reason="template_not_implemented_yet",
        )
        return {"sent": False, "reason": "template_not_implemented_yet"}
    result = await sender(order_id)
    log.info("email.return_requested_sent", order_id=order_id, result=result)
    return result


async def send_email_verification(
    ctx: dict[str, Any],
    *,
    to: str,
    name: str | None,
    token: str,
) -> dict[str, Any]:
    """Send the post-signup verification email. Token lives in Redis only."""
    db = get_db()
    service = EmailService(db)
    result = await service.send_email_verification_now(to=to, name=name, token=token)
    log.info("email.verification_sent", to=to)
    return result


async def send_password_reset(
    ctx: dict[str, Any],
    *,
    to: str,
    name: str | None,
    token: str,
) -> dict[str, Any]:
    db = get_db()
    service = EmailService(db)
    result = await service.send_password_reset_now(to=to, name=name, token=token)
    log.info("email.password_reset_sent", to=to)
    return result
