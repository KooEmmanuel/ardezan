"""Async SMTP wrapper using aiosmtplib.

Three TLS modes covering the common provider patterns:
- ``none``      — plain SMTP (MailHog dev, port 1025)
- ``starttls``  — STARTTLS upgrade after CONNECT (port 587, most providers)
- ``ssl``       — implicit TLS from CONNECT (port 465)

Lazy-fails: boot doesn't break if SMTP settings are missing. The first
``send()`` call raises a clear ``INTERNAL_ERROR`` with a hint.
"""
from __future__ import annotations

from email.message import EmailMessage
from email.utils import formataddr

import aiosmtplib

from app.config import Settings, get_settings
from app.errors import ApiError, ErrorCode
from app.logging_setup import get_logger

log = get_logger(__name__)


class SmtpClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _require_configured(self) -> None:
        s = self.settings
        if not s.smtp_host:
            raise ApiError(
                ErrorCode.INTERNAL_ERROR,
                "SMTP not configured.",
                http_status=503,
                details={"hint": "Set SMTP_HOST and friends in .env"},
            )

    async def send(
        self,
        *,
        to: str,
        subject: str,
        text: str,
        html: str | None = None,
        reply_to: str | None = None,
    ) -> None:
        """Send a single transactional email. Multipart text+HTML when ``html``
        is provided so clients render whichever they prefer."""
        self._require_configured()
        s = self.settings

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = formataddr((s.smtp_from_name, s.smtp_from_email))
        msg["To"] = to
        if reply_to:
            msg["Reply-To"] = reply_to
        msg.set_content(text)
        if html:
            msg.add_alternative(html, subtype="html")

        send_kwargs: dict = {"hostname": s.smtp_host, "port": s.smtp_port}
        if s.smtp_username:
            send_kwargs["username"] = s.smtp_username
            send_kwargs["password"] = s.smtp_password
        if s.smtp_tls_mode == "ssl":
            send_kwargs["use_tls"] = True
        elif s.smtp_tls_mode == "starttls":
            send_kwargs["start_tls"] = True
        # mode == "none": leave both off (plain SMTP).

        try:
            await aiosmtplib.send(msg, **send_kwargs)
        except aiosmtplib.SMTPException as exc:
            log.warning(
                "smtp.send_failed",
                error=str(exc),
                host=s.smtp_host,
                port=s.smtp_port,
                to=to,
                subject=subject,
            )
            raise ApiError(
                ErrorCode.INTERNAL_ERROR,
                "Failed to send email.",
                http_status=502,
                details={"smtp_error": str(exc)[:200]},
            ) from exc

        log.info("smtp.sent", to=to, subject=subject, host=s.smtp_host)


_client: SmtpClient | None = None


def get_smtp_client() -> SmtpClient:
    global _client
    if _client is None:
        _client = SmtpClient()
    return _client
