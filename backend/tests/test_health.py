"""Smoke test for the FastAPI app — verifies the health endpoint and error model.

Run with: ``uv run pytest``
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from app.errors import ApiError, ErrorCode
from app.main import app

if TYPE_CHECKING:
    pass


# ── Skip DB lifespan during pure unit tests by overriding the dependency ──
# We hit ``/api/v1/health`` directly without starting Mongo. The test client
# enters the app's lifespan automatically; we run the health test against a
# client that bypasses it by short-circuiting init.
@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    async def _noop() -> None:
        return None

    monkeypatch.setattr("app.main.init_db", _noop)
    monkeypatch.setattr("app.main.close_db", _noop)
    return TestClient(app)


def test_health(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "ardezan-api"}


def test_security_headers_present(client: TestClient) -> None:
    """Baseline security headers must be attached to every response.

    HSTS / CSP are production-only (dev runs with is_production=False), so we
    only assert the always-on headers here.
    """
    response = client.get("/api/v1/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["cross-origin-opener-policy"] == "same-origin"
    assert "camera=()" in response.headers["permissions-policy"]


def test_error_envelope_shape(client: TestClient) -> None:
    """Force-raise an ApiError on a temporary route and check the envelope."""

    @app.get("/__test__/error", include_in_schema=False)
    async def _raise() -> None:
        raise ApiError(
            ErrorCode.OUT_OF_STOCK,
            "This item just sold out.",
            http_status=409,
            details={"variant_id": "var_test"},
        )

    response = client.get("/__test__/error")
    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "OUT_OF_STOCK"
    assert body["error"]["message"] == "This item just sold out."
    assert body["error"]["details"] == {"variant_id": "var_test"}
    assert body["error"]["request_id"].startswith("req_")
