"""Daily low-stock digest emailed to the operator.

Runs once a day via the arq cron in ``worker/main.py``. Skips entirely if
``LOW_STOCK_ALERT_ENABLED=false`` or ``LOW_STOCK_ALERT_EMAIL`` is empty —
that way fresh dev environments don't spam MailHog with stale data.

Threshold check: a variant is "low" when
``(stock_on_hand - held_units) <= low_stock_threshold`` with
``track_inventory=True`` and ``status="active"``. Held units count as
already-reserved so a variant with a full active checkout isn't
double-flagged.
"""
from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.db import C, get_db
from app.logging_setup import get_logger
from app.modules.emails.smtp_client import get_smtp_client
from app.modules.emails.templates import render_low_stock_digest

log = get_logger("worker.jobs.inventory_alerts")

# Cap the digest so a freshly-out-of-stock catalogue doesn't generate a
# 2000-row email. The operator should follow the link to /admin/products
# for the long tail.
MAX_ROWS = 50


async def daily_low_stock_digest(ctx: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    if not settings.low_stock_alert_enabled:
        return {"status": "disabled"}
    recipient = settings.low_stock_alert_email or settings.admin_bootstrap_email
    if not recipient:
        log.warning(
            "low_stock.no_recipient",
            hint="Set LOW_STOCK_ALERT_EMAIL or ADMIN_BOOTSTRAP_EMAIL in .env",
        )
        return {"status": "no_recipient"}

    db = get_db()

    # Find variants below threshold. Mongo can evaluate the math directly
    # via $expr — no need to scan in Python.
    cursor = db[C.variants].find(
        {
            "deleted_at": None,
            "status": "active",
            "inventory.track_inventory": True,
            "$expr": {
                "$lte": [
                    {
                        "$subtract": [
                            {"$ifNull": ["$inventory.stock_on_hand", 0]},
                            {"$ifNull": ["$inventory.held_units", 0]},
                        ]
                    },
                    {"$ifNull": ["$inventory.low_stock_threshold", 0]},
                ]
            },
        },
        projection={
            "variant_id": 1,
            "product_id": 1,
            "sku": 1,
            "size": 1,
            "color": 1,
            "inventory": 1,
            "_id": 0,
        },
    ).limit(MAX_ROWS)
    variants = await cursor.to_list(MAX_ROWS)

    if not variants:
        log.info("low_stock.none")
        return {"status": "ok", "count": 0}

    # Hydrate product titles in one query.
    product_ids = list({v["product_id"] for v in variants})
    products: dict[str, str] = {}
    async for p in db[C.products].find(
        {"product_id": {"$in": product_ids}},
        projection={"product_id": 1, "title": 1, "_id": 0},
    ):
        products[p["product_id"]] = p.get("title") or "Untitled"

    items: list[dict[str, Any]] = []
    for v in variants:
        inv = v.get("inventory") or {}
        stock = int(inv.get("stock_on_hand", 0) or 0)
        held = int(inv.get("held_units", 0) or 0)
        items.append(
            {
                "variant_id": v["variant_id"],
                "product_id": v["product_id"],
                "product_title": products.get(v["product_id"], "Untitled"),
                "sku": v.get("sku", ""),
                "size": v.get("size", ""),
                "color": v.get("color", ""),
                "quantity": max(0, stock - held),
                "threshold": int(inv.get("low_stock_threshold", 0) or 0),
            }
        )

    # Newest threshold-breakers near the top — sort by remaining quantity
    # ascending so the most urgent rows are first.
    items.sort(key=lambda x: (x["quantity"], x["product_title"]))

    subject, text, html = render_low_stock_digest(
        items, link_base_url=settings.email_link_base_url
    )
    await get_smtp_client().send(
        to=recipient, subject=subject, text=text, html=html
    )
    log.info("low_stock.sent", recipient=recipient, count=len(items))
    return {"status": "ok", "count": len(items), "recipient": recipient}


__all__ = ["daily_low_stock_digest"]
