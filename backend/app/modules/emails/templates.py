"""Email template rendering.

Phase 1 keeps templates inline so we don't need Jinja2 or a template directory.
The render functions take an order document and return ``(subject, text, html)``.
Both ``text`` and ``html`` are returned — multipart messages let the receiving
client render whichever it prefers.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlencode


def _money(amount_minor: int, currency: str) -> str:
    sign = "$" if currency.upper() == "USD" else ""
    return f"{sign}{amount_minor / 100:.2f} {currency.upper() if not sign else ''}".strip()


def _addr(addr: dict[str, Any]) -> str:
    parts = [
        addr.get("name", ""),
        addr.get("line1", ""),
        addr.get("line2", "") or "",
        f"{addr.get('city', '')}, {addr.get('region') or ''} {addr.get('postal_code', '')}".strip(),
        addr.get("country", ""),
    ]
    return "\n".join(p for p in parts if p)


def _first_name(name: str | None) -> str:
    if not name:
        return "there"
    return name.split()[0]


def render_email_verification(
    *,
    name: str | None,
    verify_url: str,
    ttl_hours: int = 24,
) -> tuple[str, str, str]:
    """Welcome + click-to-verify email sent after signup."""
    subject = "Confirm your email for Ardezan"
    first = _first_name(name)

    text = (
        f"Welcome, {first}.\n"
        "\n"
        f"Confirm your email to finish setting up your Ardezan account:\n"
        f"{verify_url}\n"
        f"\n"
        f"This link is valid for {ttl_hours} hours.\n"
        "\n"
        "If you didn't sign up, you can ignore this email.\n"
        "\n"
        "— Ardezan"
    )
    html = f"""<!doctype html>
<html><body style="margin:0;padding:24px;background:#f6f4ef;font-family:ui-sans-serif,system-ui,-apple-system,sans-serif;color:#0a0a0b;">
  <div style="max-width:520px;margin:0 auto;background:#fff;border-radius:12px;padding:32px;">
    <h1 style="font-family:Georgia,serif;font-weight:500;font-size:24px;margin:0 0 4px;">Welcome, {first}.</h1>
    <p style="color:#555;margin:0 0 24px;font-size:14px;">Confirm your email to finish setting up your account.</p>
    <p style="margin:0 0 24px;">
      <a href="{verify_url}" style="display:inline-block;padding:12px 20px;background:#0a0a0b;color:#fff;text-decoration:none;border-radius:6px;font-size:14px;">Confirm email</a>
    </p>
    <p style="margin:0 0 16px;font-size:12px;color:#888;">Link valid for {ttl_hours} hours.</p>
    <p style="margin:0;font-size:12px;color:#888;">Or copy this URL:<br><span style="word-break:break-all;color:#555;">{verify_url}</span></p>
    <p style="margin:32px 0 0;color:#888;font-size:12px;">If you didn't sign up, you can ignore this email.</p>
  </div>
</body></html>"""
    return subject, text, html


def render_password_reset(
    *,
    name: str | None,
    reset_url: str,
    ttl_minutes: int = 60,
) -> tuple[str, str, str]:
    """Password-reset email. Subject is intentionally generic — providers
    sometimes flag "password" but ``account access`` looks normal."""
    subject = "Reset your Ardezan password"
    first = _first_name(name)
    text = (
        f"Hi {first},\n"
        "\n"
        "You (or someone using your email) asked to reset your Ardezan password.\n"
        f"To set a new one, open this link within {ttl_minutes} minutes:\n"
        f"{reset_url}\n"
        "\n"
        "If you didn't ask for a reset, you can ignore this — your password\n"
        "stays the same.\n"
        "\n"
        "— Ardezan"
    )
    html = f"""<!doctype html>
<html><body style="margin:0;padding:24px;background:#f6f4ef;font-family:ui-sans-serif,system-ui,-apple-system,sans-serif;color:#0a0a0b;">
  <div style="max-width:520px;margin:0 auto;background:#fff;border-radius:12px;padding:32px;">
    <h1 style="font-family:Georgia,serif;font-weight:500;font-size:24px;margin:0 0 4px;">Reset your password</h1>
    <p style="color:#555;margin:0 0 24px;font-size:14px;">Hi {first} — choose a new password by following the link below.</p>
    <p style="margin:0 0 24px;">
      <a href="{reset_url}" style="display:inline-block;padding:12px 20px;background:#0a0a0b;color:#fff;text-decoration:none;border-radius:6px;font-size:14px;">Set a new password</a>
    </p>
    <p style="margin:0 0 16px;font-size:12px;color:#888;">Link valid for {ttl_minutes} minutes.</p>
    <p style="margin:0;font-size:12px;color:#888;">Or copy this URL:<br><span style="word-break:break-all;color:#555;">{reset_url}</span></p>
    <p style="margin:32px 0 0;color:#888;font-size:12px;">If you didn't ask for this, you can ignore the email — your password stays the same.</p>
  </div>
</body></html>"""
    return subject, text, html


def _carrier_tracking_url(carrier: str | None, number: str) -> str | None:
    if not number:
        return None
    if not carrier:
        return None
    base = {
        "USPS": "https://tools.usps.com/go/TrackConfirmAction?qtc_tLabels1=",
        "FedEx": "https://www.fedex.com/fedextrack/?tracknumbers=",
        "UPS": "https://www.ups.com/track?tracknum=",
        "DHL": "https://www.dhl.com/global-en/home/tracking/tracking-express.html?submit=1&tracking-id=",
        "Royal Mail": "https://www.royalmail.com/track-your-item#/tracking-results/",
    }.get(carrier)
    return f"{base}{number}" if base else None


def render_low_stock_digest(
    items: list[dict[str, Any]],
    *,
    link_base_url: str = "http://localhost:3000",
) -> tuple[str, str, str]:
    """Internal operator email: today's low-stock variants.

    Each item dict should carry: ``product_title``, ``sku``, ``size``,
    ``color``, ``quantity`` (effective: ``stock_on_hand - held_units``),
    ``threshold``.
    """
    n = len(items)
    subject = (
        f"Ardezan — {n} variant{'s' if n != 1 else ''} below low-stock threshold"
    )
    admin_url = f"{link_base_url.rstrip('/')}/admin/products"

    rows_text = "\n".join(
        f"  • {it['product_title']} [{it['size']}/{it['color']}] · "
        f"SKU {it['sku']} · {it['quantity']} left (threshold {it['threshold']})"
        for it in items
    )
    text = (
        f"Daily low-stock summary — {n} variants need restocking.\n\n"
        f"{rows_text}\n\n"
        f"Manage stock: {admin_url}\n\n"
        "— Ardezan ops"
    )

    rows_html = "".join(
        f"<tr>"
        f'<td style="padding:6px 0;">{it["product_title"]}<br>'
        f'<span style="color:#888;font-size:12px;">'
        f"SKU {it['sku']} · {it['size']} · {it['color']}</span></td>"
        f'<td style="padding:6px 0;text-align:right;white-space:nowrap;">'
        f'<strong style="color:#8d1717;">{it["quantity"]}</strong>'
        f'<br><span style="color:#888;font-size:11px;">'
        f"threshold {it['threshold']}</span></td>"
        f"</tr>"
        for it in items
    )
    html = f"""<!doctype html>
<html><body style="margin:0;padding:24px;background:#fafafa;font-family:ui-sans-serif,system-ui,-apple-system,sans-serif;color:#0a0a0b;">
  <div style="max-width:560px;margin:0 auto;background:#fff;border-radius:12px;padding:32px;">
    <h1 style="font-family:Georgia,serif;font-weight:500;font-size:24px;margin:0 0 4px;">Low-stock digest</h1>
    <p style="color:#666;margin:0 0 24px;font-size:14px;">{n} variant{'s' if n != 1 else ''} below threshold today.</p>
    <table style="width:100%;border-collapse:collapse;font-size:14px;">{rows_html}</table>
    <p style="margin:24px 0 0;font-size:12px;">
      <a href="{admin_url}" style="color:#0a0a0b;text-decoration:underline;">Manage stock →</a>
    </p>
    <p style="margin:32px 0 0;color:#888;font-size:12px;">— Ardezan ops</p>
  </div>
</body></html>"""
    return subject, text, html


def render_order_shipped(
    order: dict[str, Any],
    *,
    link_base_url: str = "http://localhost:3000",
) -> tuple[str, str, str]:
    """Subject/text/HTML for the 'your order shipped' email."""
    order_number = order["order_number"]
    shipping = order.get("shipping_address") or {}
    name = shipping.get("name") if shipping else None
    first = _first_name(name)

    fulfillment = order.get("fulfillment") or {}
    carrier = fulfillment.get("carrier") or "your carrier"
    tracking_number = fulfillment.get("tracking_number") or ""
    tracking_url = (
        fulfillment.get("tracking_url")
        or _carrier_tracking_url(fulfillment.get("carrier"), tracking_number)
    )

    manage_url = (
        f"{link_base_url.rstrip('/')}/order-confirmation/{order['order_id']}"
    )

    subject = f"Ardezan — order {order_number} is on its way"

    text_lines = [
        f"Hi {first},",
        "",
        f"Your order {order_number} just shipped via {carrier}.",
    ]
    if tracking_number:
        text_lines.append(f"Tracking: {tracking_number}")
    if tracking_url:
        text_lines.append(f"Track it: {tracking_url}")
    text_lines += [
        "",
        f"Order details: {manage_url}",
        "",
        "— Ardezan",
    ]
    text = "\n".join(text_lines)

    track_block = ""
    if tracking_url:
        track_block = (
            f'<p style="margin:8px 0;">'
            f'<a href="{tracking_url}" '
            f'style="color:#0a0a0b;text-decoration:underline;">Track shipment →</a>'
            f"</p>"
        )

    html = f"""<!doctype html>
<html><body style="margin:0;padding:24px;background:#fafafa;font-family:ui-sans-serif,system-ui,-apple-system,sans-serif;color:#0a0a0b;">
  <div style="max-width:520px;margin:0 auto;background:#fff;border-radius:12px;padding:32px;">
    <h1 style="font-family:Georgia,serif;font-weight:500;font-size:24px;margin:0 0 4px;">It's on its way, {first}.</h1>
    <p style="color:#555;margin:0 0 24px;font-size:14px;">Order <strong>{order_number}</strong> shipped via {carrier}.</p>
    <p style="margin:8px 0;font-size:14px;">Tracking number:<br><span style="font-family:ui-monospace,monospace;">{tracking_number}</span></p>
    {track_block}
    <p style="margin:16px 0 0;font-size:12px;color:#888;">
      View the order:<br>
      <a href="{manage_url}" style="color:#0a0a0b;">{manage_url}</a>
    </p>
    <p style="margin:32px 0 0;color:#888;font-size:12px;">— Ardezan</p>
  </div>
</body></html>"""

    return subject, text, html


def render_order_delivered(
    order: dict[str, Any],
    *,
    link_base_url: str = "http://localhost:3000",
) -> tuple[str, str, str]:
    """Subject/text/HTML for the 'your order arrived' email."""
    order_number = order["order_number"]
    shipping = order.get("shipping_address") or {}
    name = shipping.get("name") if shipping else None
    first = _first_name(name)

    manage_url = (
        f"{link_base_url.rstrip('/')}/order-confirmation/{order['order_id']}"
    )

    subject = f"Ardezan — order {order_number} arrived"

    text = "\n".join(
        [
            f"Hi {first},",
            "",
            f"Your order {order_number} was delivered. Hope it lands well.",
            "",
            f"View the order: {manage_url}",
            "",
            "If anything isn't right, just reply to this email — we read every message.",
            "",
            "— Ardezan",
        ]
    )

    html = f"""<!doctype html>
<html><body style="margin:0;padding:24px;background:#fafafa;font-family:ui-sans-serif,system-ui,-apple-system,sans-serif;color:#0a0a0b;">
  <div style="max-width:520px;margin:0 auto;background:#fff;border-radius:12px;padding:32px;">
    <h1 style="font-family:Georgia,serif;font-weight:500;font-size:24px;margin:0 0 4px;">It landed, {first}.</h1>
    <p style="color:#555;margin:0 0 24px;font-size:14px;">Order <strong>{order_number}</strong> was delivered.</p>
    <p style="margin:0 0 16px;font-size:14px;">Hope everything fits well. If you need to swap something or anything isn't right, reply to this email and we'll sort it.</p>
    <p style="margin:16px 0 0;font-size:12px;color:#888;">
      View the order:<br>
      <a href="{manage_url}" style="color:#0a0a0b;">{manage_url}</a>
    </p>
    <p style="margin:32px 0 0;color:#888;font-size:12px;">— Ardezan</p>
  </div>
</body></html>"""

    return subject, text, html


def render_order_confirmation(
    order: dict[str, Any],
    *,
    raw_guest_token: str | None = None,
    link_base_url: str = "http://localhost:3000",
) -> tuple[str, str, str]:
    """Return ``(subject, text, html)`` for an order confirmation email."""
    order_number = order["order_number"]
    shipping = order["shipping_address"]
    name = shipping.get("name") if shipping else None
    currency = order["totals"]["currency"]

    # Build the guest claim/manage link if applicable.
    manage_url: str | None = None
    if raw_guest_token:
        qs = urlencode({"token": raw_guest_token})
        manage_url = f"{link_base_url.rstrip('/')}/order-confirmation/{order['order_id']}?{qs}"

    subject = f"Ardezan — order {order_number} confirmed"

    # ── Plain text ─────────────────────────────────────────────
    text_lines: list[str] = [
        f"Thank you, {_first_name(name)}.",
        "",
        f"Your order {order_number} has been placed.",
        "",
        "Items",
        "─────",
    ]
    for item in order.get("lines", []):
        text_lines.append(
            f"  • {item['title_snapshot']} — {item['size']} {item['color']}  "
            f"× {item['quantity']}   {_money(item['line_total_amount'], currency)}"
        )
    text_lines.extend(
        [
            "",
            "Summary",
            "───────",
            f"  Subtotal  {_money(order['totals']['subtotal_amount'], currency)}",
            f"  Shipping  {_money(order['totals']['shipping_amount'], currency)}",
            f"  Tax       {_money(order['totals']['tax_amount'], currency)}",
            f"  Total     {_money(order['totals']['total_amount'], currency)}",
            "",
            "Shipping to",
            "───────────",
            _addr(shipping),
            "",
        ]
    )
    if manage_url:
        text_lines.extend(
            [
                "Manage your order or save it to a new account:",
                manage_url,
                "(Link valid for 7 days.)",
                "",
            ]
        )
    text_lines.append("— Ardezan")
    text = "\n".join(text_lines)

    # ── HTML ───────────────────────────────────────────────────
    rows_html = "".join(
        f"<tr>"
        f'<td style="padding:6px 0;">{item["title_snapshot"]}'
        f"<br><span style=\"color:#888;font-size:12px;\">"
        f"{item['size']} · {item['color']} · × {item['quantity']}</span></td>"
        f'<td style="padding:6px 0;text-align:right;white-space:nowrap;">'
        f"{_money(item['line_total_amount'], currency)}</td>"
        f"</tr>"
        for item in order.get("lines", [])
    )
    manage_block = ""
    if manage_url:
        manage_block = (
            f'<div style="margin-top:24px;padding:16px;background:#f6f4ef;border-radius:8px;">'
            f'<p style="margin:0 0 8px;font-size:14px;">Manage your order or save it to a new account:</p>'
            f'<a href="{manage_url}" style="color:#0f5f5b;text-decoration:underline;">'
            f"{manage_url}</a>"
            f'<p style="margin:8px 0 0;font-size:12px;color:#888;">'
            f"Link valid for 7 days.</p>"
            f"</div>"
        )

    html = f"""<!doctype html>
<html><body style="margin:0;padding:24px;background:#f6f4ef;font-family:ui-sans-serif,system-ui,-apple-system,sans-serif;color:#0a0a0b;">
  <div style="max-width:560px;margin:0 auto;background:#fff;border-radius:12px;padding:32px;">
    <h1 style="font-family:Georgia,serif;font-weight:500;font-size:28px;margin:0 0 4px;">Thank you, {_first_name(name)}.</h1>
    <p style="color:#666;margin:0 0 24px;font-size:14px;">Order <strong style="color:#0a0a0b;">{order_number}</strong> has been placed.</p>

    <h2 style="font-family:Georgia,serif;font-size:16px;font-weight:500;margin:24px 0 8px;border-bottom:1px solid #eee;padding-bottom:8px;">Items</h2>
    <table style="width:100%;border-collapse:collapse;font-size:14px;">{rows_html}</table>

    <h2 style="font-family:Georgia,serif;font-size:16px;font-weight:500;margin:24px 0 8px;border-bottom:1px solid #eee;padding-bottom:8px;">Summary</h2>
    <table style="width:100%;border-collapse:collapse;font-size:14px;">
      <tr><td style="padding:4px 0;color:#666;">Subtotal</td><td style="text-align:right;padding:4px 0;">{_money(order['totals']['subtotal_amount'], currency)}</td></tr>
      <tr><td style="padding:4px 0;color:#666;">Shipping</td><td style="text-align:right;padding:4px 0;">{_money(order['totals']['shipping_amount'], currency)}</td></tr>
      <tr><td style="padding:4px 0;color:#666;">Tax</td><td style="text-align:right;padding:4px 0;">{_money(order['totals']['tax_amount'], currency)}</td></tr>
      <tr><td style="padding:8px 0 0;font-weight:500;border-top:1px solid #eee;">Total</td><td style="text-align:right;padding:8px 0 0;font-weight:500;border-top:1px solid #eee;">{_money(order['totals']['total_amount'], currency)}</td></tr>
    </table>

    <h2 style="font-family:Georgia,serif;font-size:16px;font-weight:500;margin:24px 0 8px;border-bottom:1px solid #eee;padding-bottom:8px;">Shipping to</h2>
    <pre style="font-family:inherit;font-size:14px;margin:0;white-space:pre-wrap;">{_addr(shipping)}</pre>

    {manage_block}

    <p style="margin:32px 0 0;color:#888;font-size:12px;">— Ardezan</p>
  </div>
</body></html>"""

    return subject, text, html


def render_return_requested(
    order: dict[str, Any],
    *,
    link_base_url: str = "http://localhost:3000",
) -> tuple[str, str, str]:
    """Subject/text/HTML for the "your return is being processed" email.

    Sent to the customer the moment they open a return — confirms we got
    the request, lists the items, sets expectations for the refund timeline.
    """
    order_number = order["order_number"]
    shipping = order.get("shipping_address") or {}
    name = shipping.get("name") if shipping else None
    first = _first_name(name)

    return_request = order.get("return_request") or {}
    reason = return_request.get("reason") or "your request"
    requested_line_ids = set(return_request.get("line_ids") or [])
    lines = order.get("lines") or []
    if requested_line_ids:
        scoped = [li for li in lines if li.get("line_id") in requested_line_ids]
    else:
        scoped = lines

    manage_url = (
        f"{link_base_url.rstrip('/')}/order-confirmation/{order['order_id']}"
    )

    subject = f"Ardezan — return for order {order_number} received"

    items_text = "\n".join(
        f"  · {li.get('title_snapshot','Item')} ({li.get('size') or '—'} · {li.get('color') or '—'} × {li.get('quantity',1)})"
        for li in scoped
    )
    text = (
        f"Hi {first},\n\n"
        f"We've received your return request for order {order_number}.\n\n"
        f"Reason: {reason}\n\n"
        f"Items:\n{items_text}\n\n"
        "What happens next:\n"
        "  1. We'll email you a prepaid return label within 24 hours.\n"
        "  2. Drop the parcel with any participating carrier location.\n"
        "  3. Once we receive and inspect the items, we'll issue your\n"
        "     refund to your original payment method. Refunds typically\n"
        "     post 5-10 business days after we receive the parcel.\n\n"
        f"Track this order: {manage_url}\n\n"
        "— Ardezan\n"
    )

    items_html = "".join(
        f"<li style='margin:4px 0;'>"
        f"<strong>{li.get('title_snapshot','Item')}</strong> "
        f"<span style='color:#666;'>{li.get('size') or '—'} · {li.get('color') or '—'} × {li.get('quantity',1)}</span>"
        f"</li>"
        for li in scoped
    )

    html = f"""<!doctype html>
<html><body style="margin:0;padding:24px;background:#fafafa;font-family:ui-sans-serif,system-ui,-apple-system,sans-serif;color:#0a0a0b;">
  <div style="max-width:540px;margin:0 auto;background:#fff;border-radius:12px;padding:32px;">
    <h1 style="font-family:Georgia,serif;font-weight:500;font-size:24px;margin:0 0 4px;">Got it, {first}.</h1>
    <p style="color:#555;margin:0 0 16px;font-size:14px;">
      We've received your return request for order <strong>{order_number}</strong>.
    </p>

    <div style="background:#f5f4ef;border-radius:8px;padding:14px 16px;margin:12px 0;font-size:13px;color:#444;">
      <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.12em;color:#888;margin-bottom:4px;">Reason</div>
      {reason}
    </div>

    <h2 style="font-family:Georgia,serif;font-size:16px;font-weight:500;margin:24px 0 8px;border-bottom:1px solid #eee;padding-bottom:8px;">Items being returned</h2>
    <ul style="list-style:none;padding:0;margin:0;font-size:14px;">{items_html}</ul>

    <h2 style="font-family:Georgia,serif;font-size:16px;font-weight:500;margin:24px 0 8px;border-bottom:1px solid #eee;padding-bottom:8px;">What happens next</h2>
    <ol style="padding-left:18px;margin:8px 0;font-size:14px;color:#444;">
      <li style="margin:4px 0;">We'll email a prepaid return label within 24 hours.</li>
      <li style="margin:4px 0;">Drop the parcel at any participating carrier location.</li>
      <li style="margin:4px 0;">We'll refund your original payment method 5-10 business days after the parcel arrives.</li>
    </ol>

    <p style="margin:24px 0 0;font-size:13px;">
      <a href="{manage_url}" style="color:#0a0a0b;text-decoration:underline;">View order details →</a>
    </p>
    <p style="margin:32px 0 0;color:#888;font-size:12px;">— Ardezan</p>
  </div>
</body></html>"""

    return subject, text, html
