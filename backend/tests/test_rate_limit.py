"""Rate-limit helper tests — client-IP resolution + login rule wiring.

These are pure-function tests (no Redis): the enforcement round-trip needs a
live Redis, but the IP-resolution policy and rule construction are the
security-critical bits that must hold regardless of the backend.
"""
from __future__ import annotations

import types

import pytest

from app import rate_limit


def _fake_request(headers: dict[str, str], peer: str | None = "203.0.113.9"):
    client = types.SimpleNamespace(host=peer) if peer is not None else None
    return types.SimpleNamespace(headers=headers, client=client)


def _patch_trust(monkeypatch: pytest.MonkeyPatch, *, trust: bool) -> None:
    monkeypatch.setattr(
        rate_limit,
        "get_settings",
        lambda: types.SimpleNamespace(trust_forwarded_for=trust),
    )


def test_client_ip_ignores_forwarded_header_when_untrusted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Default posture: a spoofed X-Forwarded-For must NOT be honoured — the
    # socket peer wins, so an attacker can't rotate IPs to dodge limits.
    _patch_trust(monkeypatch, trust=False)
    req = _fake_request(
        {"x-forwarded-for": "1.1.1.1", "x-real-ip": "2.2.2.2"}, peer="203.0.113.9"
    )
    assert rate_limit._client_ip(req) == "203.0.113.9"


def test_client_ip_trusts_forwarded_header_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Behind a trusted proxy we take the first XFF hop (the real client).
    _patch_trust(monkeypatch, trust=True)
    req = _fake_request(
        {"x-forwarded-for": "1.1.1.1, 10.0.0.1", "x-real-ip": "2.2.2.2"},
        peer="10.0.0.1",
    )
    assert rate_limit._client_ip(req) == "1.1.1.1"


def test_client_ip_falls_back_to_real_ip_when_trusted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_trust(monkeypatch, trust=True)
    req = _fake_request({"x-real-ip": "2.2.2.2"}, peer="10.0.0.1")
    assert rate_limit._client_ip(req) == "2.2.2.2"


def test_client_ip_unknown_when_no_peer(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_trust(monkeypatch, trust=False)
    req = _fake_request({}, peer=None)
    assert rate_limit._client_ip(req) == "unknown"


def test_login_rules_built_from_settings() -> None:
    ip_rule, email_rule = rate_limit._login_rules()
    assert ip_rule.name == "login_ip"
    assert ip_rule.window_seconds == 60
    assert ip_rule.limit > 0
    assert email_rule.name == "login_email"
    assert email_rule.window_seconds == 15 * 60
    assert email_rule.limit > 0
