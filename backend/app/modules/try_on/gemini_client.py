"""Google Gemini client — async wrapper over the ``google-genai`` SDK.

Used by:
- M4.2 Analyzer (multimodal call, structured output → BodyProfile)
- M4.3 Recommender (text call, function calling over CatalogContext)
- M4.4 Designer (image generation via gemini-2.5-flash-image)

Boot doesn't fail if ``GEMINI_API_KEY`` is missing — the first call raises a
clean ``AI_UNAVAILABLE`` with a hint. Same lazy-init pattern as Storage / Stripe.
"""
from __future__ import annotations

from typing import Any

from google import genai

from app.config import Settings, get_settings
from app.errors import ApiError, ErrorCode
from app.logging_setup import get_logger

log = get_logger(__name__)


class GeminiClient:
    """Thin async-friendly wrapper. One instance per process is fine."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client: Any | None = None

    def _require_configured(self) -> None:
        if not self.settings.gemini_api_key:
            raise ApiError(
                ErrorCode.AI_UNAVAILABLE,
                "Gemini API key not configured.",
                http_status=503,
                details={"hint": "Set GEMINI_API_KEY in .env"},
            )

    @property
    def client(self) -> Any:
        if self._client is None:
            self._require_configured()
            self._client = genai.Client(api_key=self.settings.gemini_api_key)
        return self._client

    @property
    def aio(self) -> Any:
        """Async sub-client. Use ``client.aio.models.generate_content(...)``."""
        return self.client.aio


_singleton: GeminiClient | None = None


def get_gemini_client() -> GeminiClient:
    global _singleton
    if _singleton is None:
        _singleton = GeminiClient()
    return _singleton
