"""Email service — composition + dispatch.

Two execution modes:

- **Async via the queue** (default): ``OrdersService.create_from_checkout``
  enqueues ``send_order_confirmation`` so a slow SMTP send can't block order
  creation. The arq worker picks it up.
- **Synchronous**: the dev smoke endpoint and tests can call
  ``send_order_confirmation_now`` to send inline and get errors back directly.
"""
from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import get_settings
from app.db import C
from app.errors import ApiError, ErrorCode
from app.logging_setup import get_logger
from app.modules.emails.smtp_client import SmtpClient, get_smtp_client
from app.modules.emails.templates import (
    render_email_verification,
    render_order_confirmation,
    render_order_delivered,
    render_order_shipped,
    render_password_reset,
    render_return_requested,
)

log = get_logger(__name__)


class EmailService:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self.db = db
        self.settings = get_settings()
        self.smtp: SmtpClient = get_smtp_client()

    async def send_order_confirmation_now(
        self,
        order_id: str,
        *,
        raw_guest_token: str | None = None,
    ) -> dict[str, Any]:
        """Look up the order and send the confirmation email immediately.

        Sync version — raises ``NOT_FOUND`` if the order doesn't exist and the
        SMTP error if delivery fails. Used by the dev smoke endpoint and by the
        async worker job.
        """
        order = await self.db[C.orders].find_one({"order_id": order_id})
        if not order:
            raise ApiError(
                ErrorCode.NOT_FOUND,
                f"Order not found: {order_id}",
                http_status=404,
            )

        recipient = order.get("guest_email") or _customer_email(self.db, order)
        if not recipient:
            log.warning(
                "email.no_recipient",
                order_id=order_id,
                reason="order has neither guest_email nor a resolvable customer email",
            )
            return {"sent": False, "reason": "no_recipient"}

        subject, text, html = render_order_confirmation(
            order,
            raw_guest_token=raw_guest_token,
            link_base_url=self.settings.email_link_base_url,
        )
        await self.smtp.send(to=recipient, subject=subject, text=text, html=html)
        return {
            "sent": True,
            "order_id": order_id,
            "order_number": order["order_number"],
            "to": recipient,
        }

    # ── Verification / password reset (M6.4) ──────────────────────
    async def send_email_verification_now(
        self,
        *,
        to: str,
        name: str | None,
        token: str,
    ) -> dict[str, Any]:
        """Send the click-to-verify email. ``token`` is embedded in a URL
        pointing at the frontend's confirm route."""
        base = self.settings.email_link_base_url.rstrip("/")
        verify_url = f"{base}/auth/verify-email?token={token}"
        subject, text, html = render_email_verification(
            name=name, verify_url=verify_url
        )
        await self.smtp.send(to=to, subject=subject, text=text, html=html)
        return {"sent": True, "to": to, "kind": "email_verification"}

    async def send_order_shipped_now(self, order_id: str) -> dict[str, Any]:
        """Send the 'your order shipped' email. Sync version used by the worker."""
        order = await self.db[C.orders].find_one({"order_id": order_id})
        if not order:
            raise ApiError(
                ErrorCode.NOT_FOUND,
                f"Order not found: {order_id}",
                http_status=404,
            )
        recipient = order.get("guest_email") or await _customer_email(self.db, order)
        if not recipient:
            log.warning(
                "email.no_recipient",
                order_id=order_id,
                kind="order_shipped",
            )
            return {"sent": False, "reason": "no_recipient"}
        subject, text, html = render_order_shipped(
            order, link_base_url=self.settings.email_link_base_url
        )
        await self.smtp.send(to=recipient, subject=subject, text=text, html=html)
        return {"sent": True, "order_id": order_id, "kind": "order_shipped"}

    async def send_order_delivered_now(self, order_id: str) -> dict[str, Any]:
        """Send the 'your order arrived' email. Sync version used by the worker."""
        order = await self.db[C.orders].find_one({"order_id": order_id})
        if not order:
            raise ApiError(
                ErrorCode.NOT_FOUND,
                f"Order not found: {order_id}",
                http_status=404,
            )
        recipient = order.get("guest_email") or await _customer_email(self.db, order)
        if not recipient:
            log.warning(
                "email.no_recipient",
                order_id=order_id,
                kind="order_delivered",
            )
            return {"sent": False, "reason": "no_recipient"}
        subject, text, html = render_order_delivered(
            order, link_base_url=self.settings.email_link_base_url
        )
        await self.smtp.send(to=recipient, subject=subject, text=text, html=html)
        return {"sent": True, "order_id": order_id, "kind": "order_delivered"}

    async def send_return_requested_now(self, order_id: str) -> dict[str, Any]:
        """Send the 'we got your return request' email."""
        order = await self.db[C.orders].find_one({"order_id": order_id})
        if not order:
            raise ApiError(
                ErrorCode.NOT_FOUND,
                f"Order not found: {order_id}",
                http_status=404,
            )
        if not order.get("return_request"):
            log.info(
                "email.return_no_request",
                order_id=order_id,
                reason="no_return_request_on_order",
            )
            return {"sent": False, "reason": "no_return_request"}
        recipient = order.get("guest_email") or await _customer_email(self.db, order)
        if not recipient:
            log.warning(
                "email.no_recipient",
                order_id=order_id,
                kind="return_requested",
            )
            return {"sent": False, "reason": "no_recipient"}
        subject, text, html = render_return_requested(
            order, link_base_url=self.settings.email_link_base_url
        )
        await self.smtp.send(to=recipient, subject=subject, text=text, html=html)
        return {"sent": True, "order_id": order_id, "kind": "return_requested"}

    async def send_password_reset_now(
        self,
        *,
        to: str,
        name: str | None,
        token: str,
    ) -> dict[str, Any]:
        base = self.settings.email_link_base_url.rstrip("/")
        reset_url = f"{base}/auth/reset-password?token={token}"
        subject, text, html = render_password_reset(name=name, reset_url=reset_url)
        await self.smtp.send(to=to, subject=subject, text=text, html=html)
        return {"sent": True, "to": to, "kind": "password_reset"}


# Hook for the M5 customer lookup. For now (no customer email lookup yet) just
# return None — orders without ``guest_email`` won't have their confirmation sent.
async def _customer_email(
    db: AsyncIOMotorDatabase[Any],
    order: dict[str, Any],
) -> str | None:
    customer_id = order.get("customer_id")
    if not customer_id:
        return None
    customer = await db[C.customers].find_one({"customer_id": customer_id})
    return customer.get("email") if customer else None
