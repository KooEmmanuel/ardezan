"""Redis-backed rate limiter (M6.3, REQ-062).

Fixed-window counter per ``(scope, key)`` pair: cheaper and clearer than a
sliding-log implementation, accurate enough for abuse prevention. Uses the
same Redis instance as the arq job queue — the existing ``init_queue`` pool
is reused so we don't need a second connection.

Atomicity: a Lua script does ``INCR`` + conditional ``PEXPIRE`` in one
round-trip so two concurrent requests can't both observe a counter at 0.

Usage::

    @router.post("/something", dependencies=[Depends(rate_limit_upload)])

The dependency raises :class:`ApiError(RATE_LIMITED)` (HTTP 429) with a
``Retry-After`` header so the frontend can show a clean "try again in N
seconds" message rather than a generic failure.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import Request

from app.config import get_settings
from app.errors import ApiError, ErrorCode
from app.logging_setup import get_logger
from app.queue import get_queue

if TYPE_CHECKING:
    from arq.connections import ArqRedis

log = get_logger(__name__)


# INCR the key; if it's the first hit (returned == 1), set the expiry.
# Returns {count, ttl_ms}.
_LIMIT_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('PEXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('PTTL', KEYS[1])
return {current, ttl}
"""


@dataclass(frozen=True)
class RateLimit:
    """One rule. ``limit`` requests per ``window_seconds``."""

    name: str
    limit: int
    window_seconds: int


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    count: int
    limit: int
    retry_after_seconds: int


async def _check(
    redis: "ArqRedis",
    *,
    scope: str,
    key: str,
    rule: RateLimit,
) -> RateLimitDecision:
    redis_key = f"ratelimit:{scope}:{key}"
    result = await redis.eval(
        _LIMIT_SCRIPT, 1, redis_key, rule.window_seconds * 1000
    )
    count = int(result[0])
    ttl_ms = int(result[1]) if result[1] and int(result[1]) > 0 else rule.window_seconds * 1000
    retry_after = max(1, (ttl_ms + 999) // 1000)
    return RateLimitDecision(
        allowed=count <= rule.limit,
        count=count,
        limit=rule.limit,
        retry_after_seconds=retry_after,
    )


def _client_ip(request: Request) -> str:
    """Extract the caller's IP for rate-limit bucketing.

    Forwarded headers (``X-Forwarded-For`` first hop → ``X-Real-IP``) are
    trusted **only** when ``trust_forwarded_for`` is enabled, i.e. a known
    proxy that overwrites them sits in front. Otherwise we use the socket
    peer so a client can't spoof ``X-Forwarded-For`` to dodge IP limits.
    """
    if get_settings().trust_forwarded_for:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
        xri = request.headers.get("x-real-ip")
        if xri:
            return xri.strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


async def _enforce_rules(
    request: Request,
    rules: list[tuple[RateLimit, str]],
) -> None:
    """Apply each rule and raise on the first that's exceeded.

    ``rules`` is a list of ``(rule, key)`` pairs. ``key`` is the per-rule
    identifier (e.g. the IP, the anonymous session id).
    """
    if not rules:
        return
    redis = get_queue()  # same Redis instance as the arq pool
    for rule, key in rules:
        if not key:
            continue
        decision = await _check(redis, scope=rule.name, key=key, rule=rule)
        if not decision.allowed:
            log.warning(
                "rate_limit.exceeded",
                rule=rule.name,
                key=key[:32],
                count=decision.count,
                limit=decision.limit,
                retry_after=decision.retry_after_seconds,
                path=request.url.path,
            )
            raise ApiError(
                ErrorCode.RATE_LIMITED,
                "Too many requests. Please slow down and try again shortly.",
                http_status=429,
                details={
                    "rule": rule.name,
                    "retry_after_seconds": decision.retry_after_seconds,
                },
            )


# ── Concrete rules ──────────────────────────────────────────────────
def _upload_rules() -> tuple[RateLimit, RateLimit]:
    """Try-on upload limits. Two windows per identity for burst + sustain.

    The IP rule guards against scraping/automation; the fingerprint rule
    (anonymous_session_id or customer_id) makes the IP-tax shared-NAT
    failure mode survivable for legit users.
    """
    s = get_settings()
    ip_rule = RateLimit(
        name="upload_ip",
        limit=s.rate_limit_upload_ip_per_min,
        window_seconds=60,
    )
    fp_rule = RateLimit(
        name="upload_fingerprint",
        limit=s.rate_limit_upload_fingerprint_per_hour,
        window_seconds=3600,
    )
    return ip_rule, fp_rule


async def rate_limit_try_on_upload(
    request: Request,
) -> None:
    """FastAPI dependency for ``POST /try-on/sessions``.

    Reads identity off the request: the IP plus whichever of
    ``anonymous_session_id`` (form field) or the customer session cookie is
    present. If neither identity is on the request we still enforce IP-only.
    """
    ip_rule, fp_rule = _upload_rules()
    ip = _client_ip(request)

    fingerprint = ""
    # multipart form values aren't easy to read in a dep without re-parsing,
    # so we use a lighter signal here: a header the frontend can send, or
    # cookie-derived identity. The router itself also passes the form's
    # anonymous_session_id when present (via a second enforce call below).
    cookie_fp = request.cookies.get("aid") or request.cookies.get("session")
    if cookie_fp:
        fingerprint = cookie_fp

    await _enforce_rules(
        request,
        [
            (ip_rule, ip),
            (fp_rule, fingerprint),
        ],
    )


# ── Password reset (M6.4) ───────────────────────────────────────────
def _password_reset_rules() -> tuple[RateLimit, RateLimit]:
    """5 requests per hour per IP + 3 per hour per email. Prevents both
    blanket spam and targeted account harassment."""
    return (
        RateLimit(name="pwreset_ip", limit=5, window_seconds=3600),
        RateLimit(name="pwreset_email", limit=3, window_seconds=3600),
    )


async def rate_limit_password_reset(request: Request) -> None:
    """Dep wrapper — applies the IP-only rule. The route handler does a
    second pass with the (normalised) email once the body is parsed."""
    ip_rule, _ = _password_reset_rules()
    await _enforce_rules(request, [(ip_rule, _client_ip(request))])


async def enforce_password_reset_email(request: Request, email: str) -> None:
    if not email:
        return
    _, email_rule = _password_reset_rules()
    await _enforce_rules(request, [(email_rule, email.lower().strip())])


# ── Login (brute-force / credential stuffing) ───────────────────────
def _login_rules() -> tuple[RateLimit, RateLimit]:
    """Per-IP (1-min burst) + per-email (15-min targeted) login limits."""
    s = get_settings()
    return (
        RateLimit(
            name="login_ip",
            limit=s.rate_limit_login_ip_per_min,
            window_seconds=60,
        ),
        RateLimit(
            name="login_email",
            limit=s.rate_limit_login_email_per_15min,
            window_seconds=15 * 60,
        ),
    )


async def rate_limit_login(request: Request) -> None:
    """Dep wrapper applied to login routes — IP-only pre-check. The handler
    does a second pass with the submitted email once the body is parsed."""
    ip_rule, _ = _login_rules()
    await _enforce_rules(request, [(ip_rule, _client_ip(request))])


async def enforce_login_email(request: Request, email: str) -> None:
    """Second login pass keyed on the (normalised) email, so a single
    account can't be sprayed across many IPs."""
    if not email:
        return
    _, email_rule = _login_rules()
    await _enforce_rules(request, [(email_rule, email.lower().strip())])


async def enforce_upload_fingerprint(request: Request, fingerprint: str) -> None:
    """Second enforcement pass once the route handler knows the form-supplied
    ``anonymous_session_id``. Idempotent w.r.t. the dep above — the IP rule
    will already have been checked, this one only re-checks the fingerprint
    bucket with the precise identifier.
    """
    if not fingerprint:
        return
    _, fp_rule = _upload_rules()
    await _enforce_rules(request, [(fp_rule, fingerprint)])


__all__ = [
    "RateLimit",
    "RateLimitDecision",
    "rate_limit_try_on_upload",
    "enforce_upload_fingerprint",
    "rate_limit_password_reset",
    "enforce_password_reset_email",
    "rate_limit_login",
    "enforce_login_email",
]
