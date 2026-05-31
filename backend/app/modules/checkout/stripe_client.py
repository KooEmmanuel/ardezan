"""Thin async wrapper around the Stripe Python SDK.

We use the official ``stripe-python`` package's ``_async`` method variants
(supported from v8+). Lazy-failing — boot doesn't break if the Stripe key is
missing; the first call returns a clear ``AI_UNAVAILABLE``-style error.

The webhook signature verification helper also lives here so the webhook
handler doesn't have to import ``stripe`` directly.
"""
from __future__ import annotations

from typing import Any

import stripe

from app.config import Settings, get_settings
from app.errors import ApiError, ErrorCode
from app.logging_setup import get_logger

log = get_logger(__name__)


class StripeClient:
    """Async-friendly Stripe wrapper. One instance per process is fine."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _require_configured(self) -> None:
        if not self.settings.stripe_secret_key:
            raise ApiError(
                ErrorCode.PAYMENT_REQUIRED,
                "Payments are not configured.",
                http_status=503,
                details={"hint": "Set STRIPE_SECRET_KEY in .env"},
            )

    @property
    def publishable_key(self) -> str:
        return self.settings.stripe_publishable_key

    # ── Payment intents ────────────────────────────────────────
    async def create_payment_intent(
        self,
        *,
        amount: int,
        currency: str,
        idempotency_key: str,
        metadata: dict[str, str],
        customer_email: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Create a Stripe PaymentIntent. Returns the raw Stripe object as a dict.

        ``idempotency_key`` is passed to Stripe so a retried request returns the
        same intent without double-charging.
        """
        self._require_configured()

        params: dict[str, Any] = {
            "amount": amount,
            "currency": currency.lower(),
            "automatic_payment_methods": {"enabled": True},
            "metadata": metadata,
        }
        if customer_email:
            params["receipt_email"] = customer_email
        if description:
            params["description"] = description

        try:
            intent = await stripe.PaymentIntent.create_async(
                api_key=self.settings.stripe_secret_key,
                idempotency_key=idempotency_key,
                **params,
            )
        except stripe.StripeError as exc:
            log.warning(
                "stripe.payment_intent_failed",
                error=str(exc),
                code=getattr(exc, "code", None),
                http_status=getattr(exc, "http_status", None),
            )
            raise ApiError(
                ErrorCode.PAYMENT_REQUIRED,
                "Payment provider rejected the request.",
                http_status=502,
                details={"stripe_code": getattr(exc, "code", None) or ""},
            ) from exc

        # Stripe 15+ removed ``dict(StripeObject)``. ``to_dict()`` walks
        # nested StripeObjects by default (recursive=True).
        return intent.to_dict()

    async def retrieve_payment_intent(self, payment_intent_id: str) -> dict[str, Any] | None:
        """Fetch a PaymentIntent by id. Returns ``None`` if Stripe says
        it doesn't exist (404). Used by the order lookup fallback so the
        frontend's polling can recover when the webhook hasn't fired yet
        (notably in local dev without ``stripe listen``).
        """
        self._require_configured()
        try:
            intent = await stripe.PaymentIntent.retrieve_async(
                payment_intent_id,
                api_key=self.settings.stripe_secret_key,
            )
        except stripe.InvalidRequestError as exc:
            log.info(
                "stripe.payment_intent_not_found",
                payment_intent_id=payment_intent_id,
                error=str(exc),
            )
            return None
        except stripe.StripeError as exc:
            log.warning(
                "stripe.payment_intent_retrieve_failed",
                payment_intent_id=payment_intent_id,
                error=str(exc),
            )
            raise ApiError(
                ErrorCode.INTERNAL_ERROR,
                "Payment provider could not be reached.",
                http_status=502,
            ) from exc
        return intent.to_dict()

    async def create_refund(
        self,
        *,
        payment_intent_id: str,
        amount: int,
        idempotency_key: str,
        reason: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Create a Stripe Refund on a successful PaymentIntent.

        ``reason`` is the Stripe-defined enum: ``"duplicate"``, ``"fraudulent"``,
        or ``"requested_by_customer"``. Free-form reasons should go in
        ``metadata`` instead. Idempotency-Key ensures retries don't double-refund.
        """
        self._require_configured()

        params: dict[str, Any] = {
            "payment_intent": payment_intent_id,
            "amount": amount,
        }
        if reason in {"duplicate", "fraudulent", "requested_by_customer"}:
            params["reason"] = reason
        if metadata:
            params["metadata"] = metadata

        try:
            refund = await stripe.Refund.create_async(
                api_key=self.settings.stripe_secret_key,
                idempotency_key=idempotency_key,
                **params,
            )
        except stripe.StripeError as exc:
            log.warning(
                "stripe.refund_failed",
                error=str(exc),
                payment_intent_id=payment_intent_id,
                amount=amount,
                code=getattr(exc, "code", None),
            )
            raise ApiError(
                ErrorCode.PAYMENT_REQUIRED,
                "Payment provider rejected the refund.",
                http_status=502,
                details={"stripe_code": getattr(exc, "code", None) or ""},
            ) from exc

        return refund.to_dict()

    async def cancel_payment_intent(self, payment_intent_id: str) -> None:
        """Cancel an open PaymentIntent (e.g. user abandoned checkout)."""
        self._require_configured()
        try:
            await stripe.PaymentIntent.cancel_async(
                payment_intent_id,
                api_key=self.settings.stripe_secret_key,
            )
        except stripe.StripeError as exc:
            # Cancellation is best-effort — log and move on. The hold expiry
            # sweeper will clean up if Stripe state is already final.
            log.warning(
                "stripe.cancel_failed",
                payment_intent_id=payment_intent_id,
                error=str(exc),
            )

    # ── Webhook verification (used by the webhook handler) ─────
    def verify_webhook(self, payload: bytes, signature: str) -> dict[str, Any]:
        """Verify the Stripe signature on a raw webhook body. Returns the
        parsed event. Raises ``WEBHOOK_INVALID_SIGNATURE`` on failure."""
        if not self.settings.stripe_webhook_secret:
            raise ApiError(
                ErrorCode.WEBHOOK_INVALID_SIGNATURE,
                "Webhook secret not configured.",
                http_status=503,
            )
        try:
            event = stripe.Webhook.construct_event(
                payload=payload,
                sig_header=signature,
                secret=self.settings.stripe_webhook_secret,
            )
        except (stripe.SignatureVerificationError, ValueError) as exc:
            log.warning("stripe.webhook_invalid_signature", error=str(exc))
            raise ApiError(
                ErrorCode.WEBHOOK_INVALID_SIGNATURE,
                "Webhook signature verification failed.",
                http_status=400,
            ) from exc
        return event.to_dict()


_client: StripeClient | None = None


def get_stripe_client() -> StripeClient:
    global _client
    if _client is None:
        _client = StripeClient()
    return _client
