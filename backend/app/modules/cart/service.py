"""Cart service — stateless revalidation and try-on full-look add.

Both operations follow the same pattern: take a list of (product_id, variant_id,
quantity) tuples, batch-fetch the underlying products and variants, and return
enriched lines with a status per line. No DB writes here — the frontend updates
its local cart based on the response.

Stock recheck happens at the moment of the call — never trusting any value
from a previous read (REQ-055).
"""
from __future__ import annotations

import secrets
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db import C
from app.errors import ApiError, ErrorCode
from app.logging_setup import get_logger
from app.modules.cart.repository import CartRepository, new_line_id
from app.modules.cart.schemas import (
    AddLineRequest,
    CartLineInput,
    CartLineState,
    CartTotals,
    FullLookAddResponse,
    FullLookItem,
    LineStatus,
    RevalidateResponse,
    ServerCart,
    ServerCartLine,
)
from app.modules.catalog.schemas import VariantPricing

log = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gen_line_id() -> str:
    return f"line_{secrets.token_hex(8)}"


def _available_for_sale(variant_doc: dict[str, Any]) -> int:
    inv = variant_doc.get("inventory", {}) or {}
    return max(
        0,
        int(inv.get("stock_on_hand", 0)) - int(inv.get("held_units", 0)),
    )


def _build_pricing(variant_doc: dict[str, Any]) -> VariantPricing:
    return VariantPricing(**variant_doc["pricing"])


def _empty_state(
    line_id: str,
    product_id: str | None,
    variant_id: str | None,
    quantity: int,
    *,
    kind: str = "catalog",
    design_session_id: str | None = None,
    source: str = "catalog",
    try_on_session_id: str | None = None,
    try_on_card_id: str | None = None,
) -> CartLineState:
    """A removed/unknown line — variant, product, or design session is gone."""
    return CartLineState(
        line_id=line_id,
        kind=kind,  # type: ignore[arg-type]
        product_id=product_id,
        variant_id=variant_id,
        design_session_id=design_session_id,
        quantity=quantity,
        status="removed",
        source=source,  # type: ignore[arg-type]
        try_on_session_id=try_on_session_id,
        try_on_card_id=try_on_card_id,
        message="This item is no longer available.",
    )


class CartService:
    """Stateless cart operations. No persistence in Phase 1 — anonymous carts
    live in browser ``localStorage``; the backend just validates them."""

    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self.db = db
        self.products = db[C.products]
        self.variants = db[C.variants]

    # ── Internal: batch fetch ──────────────────────────────────
    async def _fetch_products(self, product_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not product_ids:
            return {}
        cursor = self.products.find(
            {"product_id": {"$in": product_ids}, "status": "published", "deleted_at": None},
        )
        return {doc["product_id"]: doc async for doc in cursor}

    async def _fetch_variants(self, variant_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not variant_ids:
            return {}
        cursor = self.variants.find(
            {"variant_id": {"$in": variant_ids}, "status": "active", "deleted_at": None},
        )
        return {doc["variant_id"]: doc async for doc in cursor}

    async def _fetch_design_sessions(
        self, design_session_ids: list[str]
    ) -> dict[str, dict[str, Any]]:
        """Batch-fetch design sessions referenced by custom_design cart lines."""
        if not design_session_ids:
            return {}
        cursor = self.db[C.design_sessions].find(
            {"design_session_id": {"$in": design_session_ids}}
        )
        return {doc["design_session_id"]: doc async for doc in cursor}

    async def _revalidate_design_line(
        self,
        line: CartLineInput,
        sessions: dict[str, dict[str, Any]],
        *,
        customer_id: str | None = None,
        anonymous_session_id: str | None = None,
    ) -> CartLineState:
        """Build a CartLineState for a custom_design line from its session.

        Custom designs have no inventory and no SKU. The session is the
        source of truth for both the title and the locked-in price. A
        session in ``failed`` state is treated as removed so checkout
        can't proceed against it. A session the caller doesn't own is
        also treated as removed — design ids must not be checkout-able
        by anyone who merely knows them.
        """
        from app.modules.catalog.schemas import VariantPricing

        session = sessions.get(line.design_session_id) if line.design_session_id else None
        if not session or session.get("status") != "ready":
            return _empty_state(
                line.line_id,
                product_id=None,
                variant_id=None,
                quantity=line.quantity,
                kind="custom_design",
                design_session_id=line.design_session_id,
                source=line.source,
            )

        owner_customer = session.get("customer_id")
        owner_anon = session.get("anonymous_session_id")
        owned = (
            (owner_customer is not None and owner_customer == customer_id)
            or (owner_anon is not None and owner_anon == anonymous_session_id)
            # Legacy sessions with no owner recorded stay usable.
            or (not owner_customer and not owner_anon)
        )
        if not owned:
            log.warning(
                "cart.design_line_not_owned",
                design_session_id=line.design_session_id,
                caller_customer_id=customer_id,
            )
            return _empty_state(
                line.line_id,
                product_id=None,
                variant_id=None,
                quantity=line.quantity,
                kind="custom_design",
                design_session_id=line.design_session_id,
                source=line.source,
            )

        estimate = session.get("estimate") or {}
        fabric = session.get("fabric_snapshot") or {}
        piece = (session.get("piece_type") or "piece").title()
        title = f"Custom {piece} in {fabric.get('name', 'selected fabric')}"
        price = int(estimate.get("total_amount", 0))
        currency = estimate.get("currency", "USD")

        # Fail closed on a missing/corrupt estimate — never let a custom
        # design reach checkout at $0.
        if price <= 0:
            log.error(
                "cart.design_line_zero_estimate",
                design_session_id=line.design_session_id,
            )
            return _empty_state(
                line.line_id,
                product_id=None,
                variant_id=None,
                quantity=line.quantity,
                kind="custom_design",
                design_session_id=line.design_session_id,
                source=line.source,
            )
        pricing = VariantPricing(price_amount=price, currency=currency)

        # Re-sign the rendered image so the cart row has a fresh URL.
        image_url: str | None = None
        gen_id = session.get("generated_media_asset_id")
        if gen_id:
            media = await self.db[C.media_assets].find_one(
                {"media_asset_id": gen_id}, projection={"storage": 1, "_id": 0}
            )
            if media and (media.get("storage") or {}).get("object_key"):
                from app.storage import get_storage
                image_url = await get_storage().presigned_get_url(
                    media["storage"]["object_key"], expires_in=3600
                )

        # Custom design lines are always quantity 1 — each design is a
        # one-off. We accept the input quantity but cap it at 1 so the
        # rest of the system treats them uniformly.
        effective_qty = 1
        return CartLineState(
            line_id=line.line_id,
            kind="custom_design",
            product_id=None,
            variant_id=None,
            design_session_id=line.design_session_id,
            product_title=title,
            variant_title=None,
            size=None,
            color=fabric.get("color_family"),
            color_hex=None,
            primary_media_asset_id=gen_id,
            primary_image_url=image_url,
            quantity=effective_qty,
            status="ok",
            source=line.source,
            try_on_session_id=line.try_on_session_id,
            try_on_card_id=line.try_on_card_id,
            pricing=pricing,
            line_subtotal_amount=price * effective_qty,
            available_quantity=1,
        )

    # ── Public ─────────────────────────────────────────────────
    async def revalidate(
        self,
        lines: Iterable[CartLineInput],
        *,
        customer_id: str | None = None,
        anonymous_session_id: str | None = None,
    ) -> RevalidateResponse:
        """Refresh prices, availability, and stock status for every line.

        Returns one ``CartLineState`` per input line, with a ``status`` field
        the UI uses to render warnings or remove the line. The caller's
        identity (customer or anonymous id) gates custom_design lines.
        """
        lines_list = list(lines)
        catalog_lines = [l for l in lines_list if l.kind == "catalog"]
        design_lines = [l for l in lines_list if l.kind == "custom_design"]

        product_ids = list({l.product_id for l in catalog_lines if l.product_id})
        variant_ids = list({l.variant_id for l in catalog_lines if l.variant_id})

        products = await self._fetch_products(product_ids)
        variants = await self._fetch_variants(variant_ids)

        # Hydrate the design sessions referenced by any custom_design lines.
        design_sessions = await self._fetch_design_sessions(
            [l.design_session_id for l in design_lines if l.design_session_id]
        )

        # Sign catalog image URLs in one pass so the cart page can render
        # thumbnails without a separate fetch per product.
        from app.modules.catalog.repository import CatalogRepository
        signed_image_urls = await CatalogRepository(self.db).signed_urls_for(
            [p.get("primary_media_asset_id") for p in products.values() if p.get("primary_media_asset_id")]
        )

        states: list[CartLineState] = []
        for line in lines_list:
            if line.kind == "custom_design":
                states.append(
                    await self._revalidate_design_line(
                        line,
                        design_sessions,
                        customer_id=customer_id,
                        anonymous_session_id=anonymous_session_id,
                    )
                )
                continue

            product = products.get(line.product_id) if line.product_id else None
            variant = variants.get(line.variant_id) if line.variant_id else None

            # Removed: product or variant is gone / unpublished / soft-deleted.
            if not product or not variant or variant.get("product_id") != line.product_id:
                states.append(
                    _empty_state(
                        line.line_id,
                        line.product_id,
                        line.variant_id,
                        line.quantity,
                        source=line.source,
                        try_on_session_id=line.try_on_session_id,
                        try_on_card_id=line.try_on_card_id,
                    )
                )
                continue

            pricing = _build_pricing(variant)
            available = _available_for_sale(variant)

            # Determine status (priority order: out_of_stock > low_stock > price_changed > ok)
            status: LineStatus = "ok"
            message: str | None = None

            if available <= 0:
                status = "out_of_stock"
                message = "This item just sold out."
            elif available < line.quantity:
                status = "low_stock"
                message = f"Only {available} left — quantity will be reduced."
            elif (
                line.expected_unit_price_amount is not None
                and line.expected_unit_price_amount != pricing.price_amount
            ):
                status = "price_changed"
                old = line.expected_unit_price_amount
                new = pricing.price_amount
                message = f"Price changed from ${old/100:.2f} to ${new/100:.2f}."

            effective_qty = min(line.quantity, available) if available > 0 else 0
            line_subtotal = pricing.price_amount * effective_qty

            primary_id = product.get("primary_media_asset_id")
            states.append(
                CartLineState(
                    line_id=line.line_id,
                    product_id=line.product_id,
                    variant_id=line.variant_id,
                    product_slug=product.get("slug"),
                    product_title=product.get("title"),
                    variant_title=variant.get("title"),
                    size=variant.get("size"),
                    color=variant.get("color"),
                    color_hex=variant.get("color_hex"),
                    primary_media_asset_id=primary_id,
                    # Same precedence as the catalog DTO (catalog/repository.py):
                    # a seeded ``static_image_url`` wins, else the B2 signed URL.
                    # Without this, seeded products (no media asset) show a blank
                    # thumbnail in the cart even though the catalog renders fine.
                    primary_image_url=(
                        product.get("static_image_url")
                        or (signed_image_urls.get(primary_id) if primary_id else None)
                    ),
                    quantity=line.quantity,
                    status=status,
                    source=line.source,
                    try_on_session_id=line.try_on_session_id,
                    try_on_card_id=line.try_on_card_id,
                    pricing=pricing,
                    line_subtotal_amount=line_subtotal,
                    available_quantity=available,
                    message=message,
                )
            )

        # Totals - use current price x min(requested, available); only count lines that survive.
        currency = next(
            (s.pricing.currency for s in states if s.pricing is not None),
            "USD",
        )
        subtotal = sum(s.line_subtotal_amount for s in states)
        item_count = sum(
            min(s.quantity, s.available_quantity)
            for s in states
            if s.status not in {"removed", "out_of_stock"}
        )
        any_changes = any(s.status != "ok" for s in states)
        blocks_checkout = any(s.status in {"removed", "out_of_stock"} for s in states)

        return RevalidateResponse(
            lines=states,
            totals=CartTotals(
                subtotal_amount=subtotal,
                item_count=item_count,
                currency=currency,
            ),
            any_changes=any_changes,
            blocks_checkout=blocks_checkout,
        )

    async def add_full_look(
        self,
        items: Iterable[FullLookItem],
        *,
        try_on_session_id: str,
        card_id: str,
    ) -> FullLookAddResponse:
        """Validate every item in a try-on bundle and return cart-ready lines.

        Per REQ-055, stock is rechecked at this moment — generation-time
        inventory is never trusted. If any item is unavailable, it's separated
        into ``unavailable_lines`` so the UI can offer a swap or partial add.
        """
        items_list = list(items)
        variant_ids = [it.variant_id for it in items_list]
        product_ids = list({it.product_id for it in items_list})

        products = await self._fetch_products(product_ids)
        variants = await self._fetch_variants(variant_ids)

        added: list[CartLineState] = []
        unavailable: list[CartLineState] = []

        for item in items_list:
            line_id = _gen_line_id()
            product = products.get(item.product_id)
            variant = variants.get(item.variant_id)

            if not product or not variant or variant.get("product_id") != item.product_id:
                unavailable.append(
                    _empty_state(
                        line_id,
                        item.product_id,
                        item.variant_id,
                        item.quantity,
                        source="try_on_full_look",
                        try_on_session_id=try_on_session_id,
                        try_on_card_id=card_id,
                    )
                )
                continue

            pricing = _build_pricing(variant)
            available = _available_for_sale(variant)

            line = CartLineState(
                line_id=line_id,
                product_id=item.product_id,
                variant_id=item.variant_id,
                product_slug=product.get("slug"),
                product_title=product.get("title"),
                variant_title=variant.get("title"),
                size=variant.get("size"),
                color=variant.get("color"),
                color_hex=variant.get("color_hex"),
                primary_media_asset_id=product.get("primary_media_asset_id"),
                # Seeded catalog serves images from static_image_url, not B2.
                # (revalidate() re-resolves this on cart load too, but set it
                # here so the add-to-cart confirmation shows the thumbnail.)
                primary_image_url=product.get("static_image_url"),
                quantity=item.quantity,
                status="ok",
                source="try_on_full_look",
                try_on_session_id=try_on_session_id,
                try_on_card_id=card_id,
                pricing=pricing,
                line_subtotal_amount=pricing.price_amount * item.quantity,
                available_quantity=available,
            )

            if available <= 0:
                line.status = "out_of_stock"
                line.message = "This piece just sold out — try a swap below."
                line.line_subtotal_amount = 0
                unavailable.append(line)
            elif available < item.quantity:
                line.status = "low_stock"
                line.message = f"Only {available} left."
                line.line_subtotal_amount = pricing.price_amount * available
                # Still "added" but at reduced quantity — UI will note the change.
                added.append(line)
            else:
                added.append(line)

        log.info(
            "cart.full_look_add",
            try_on_session_id=try_on_session_id,
            card_id=card_id,
            requested=len(items_list),
            added=len(added),
            unavailable=len(unavailable),
        )

        return FullLookAddResponse(
            added_lines=added,
            unavailable_lines=unavailable,
            swap_suggestions=[],   # populated in M4 when the recommender can suggest swaps
            all_available=len(unavailable) == 0,
        )

    # ── M5.2: Server-side cart operations ──────────────────────
    @property
    def repo(self) -> CartRepository:
        # Lazy because not every CartService call needs the repo (stateless
        # revalidation predates it). Cached per instance for reuse.
        if not hasattr(self, "_repo"):
            self._repo = CartRepository(self.db)
        return self._repo

    async def get_or_create_cart(self, customer_id: str) -> dict[str, Any]:
        cart = await self.repo.find_active_for_customer(customer_id)
        if cart is None:
            cart = await self.repo.create_for_customer(customer_id)
            log.info("cart.created", customer_id=customer_id, cart_id=cart["cart_id"])
        return cart

    async def add_line_to_cart(
        self,
        customer_id: str,
        body: AddLineRequest,
    ) -> dict[str, Any]:
        cart = await self.get_or_create_cart(customer_id)

        # Validate the product + variant exist and are sellable.
        product = await self.products.find_one(
            {
                "product_id": body.product_id,
                "status": "published",
                "deleted_at": None,
            }
        )
        if product is None:
            raise ApiError(
                ErrorCode.NOT_FOUND,
                "Product not available.",
                http_status=404,
                details={"product_id": body.product_id},
            )
        variant = await self.variants.find_one(
            {
                "variant_id": body.variant_id,
                "product_id": body.product_id,
                "status": "active",
                "deleted_at": None,
            }
        )
        if variant is None:
            raise ApiError(
                ErrorCode.NOT_FOUND,
                "Variant not available.",
                http_status=404,
                details={"variant_id": body.variant_id},
            )

        # Catalog adds for the same variant merge by quantity. Try-on adds
        # stay as separate lines so the customer can pick per outfit.
        if body.source == "catalog" and not body.try_on_session_id:
            for existing in cart.get("lines", []):
                if (
                    existing.get("variant_id") == body.variant_id
                    and existing.get("source", "catalog") == "catalog"
                    and not existing.get("try_on_session_id")
                ):
                    new_qty = min(99, int(existing["quantity"]) + body.quantity)
                    log.info(
                        "cart.line_merged",
                        cart_id=cart["cart_id"],
                        line_id=existing["line_id"],
                        new_quantity=new_qty,
                    )
                    updated = await self.repo.update_line_quantity(
                        cart["cart_id"], existing["line_id"], quantity=new_qty
                    )
                    assert updated is not None
                    return updated

        line_doc = {
            "line_id": new_line_id(),
            "product_id": body.product_id,
            "variant_id": body.variant_id,
            "quantity": body.quantity,
            "source": body.source,
            "try_on_session_id": body.try_on_session_id,
            "try_on_card_id": body.try_on_card_id,
            "price_snapshot": variant["pricing"],
            "added_at": _now(),
        }
        updated = await self.repo.push_line(cart["cart_id"], line_doc)
        assert updated is not None
        log.info(
            "cart.line_added",
            cart_id=cart["cart_id"],
            line_id=line_doc["line_id"],
            variant_id=body.variant_id,
            quantity=body.quantity,
            source=body.source,
        )
        return updated

    async def update_cart_line(
        self,
        customer_id: str,
        line_id: str,
        quantity: int,
    ) -> dict[str, Any]:
        cart = await self.get_or_create_cart(customer_id)
        if not any(l.get("line_id") == line_id for l in cart.get("lines", [])):
            raise ApiError(
                ErrorCode.NOT_FOUND,
                f"Cart line not found: {line_id}",
                http_status=404,
            )
        updated = await self.repo.update_line_quantity(
            cart["cart_id"], line_id, quantity=quantity
        )
        assert updated is not None
        return updated

    async def remove_cart_line(
        self,
        customer_id: str,
        line_id: str,
    ) -> dict[str, Any]:
        cart = await self.get_or_create_cart(customer_id)
        updated = await self.repo.remove_line(cart["cart_id"], line_id)
        return updated or cart

    async def merge_anonymous_into_server(
        self,
        customer_id: str,
        anonymous_lines: Iterable[CartLineInput],
    ) -> dict[str, Any]:
        """Per REQ-044: when a guest with items in their localStorage signs
        in, merge those lines into the server cart. Same-variant conflicts
        keep the higher quantity."""
        cart = await self.get_or_create_cart(customer_id)

        anon_list = list(anonymous_lines)
        if not anon_list:
            return cart

        product_ids = list({l.product_id for l in anon_list})
        variant_ids = list({l.variant_id for l in anon_list})
        products_lookup = await self._fetch_products(product_ids)
        variants_lookup = await self._fetch_variants(variant_ids)

        kept = 0
        added = 0
        skipped = 0
        for input_line in anon_list:
            product = products_lookup.get(input_line.product_id)
            variant = variants_lookup.get(input_line.variant_id)
            if not product or not variant or variant.get("product_id") != input_line.product_id:
                skipped += 1
                continue

            # Catalog-source merging by variant. Try-on lines always become
            # new lines (each from a different outfit) so we don't dedup.
            if input_line.source == "catalog" and not input_line.try_on_session_id:
                existing = next(
                    (
                        l
                        for l in cart.get("lines", [])
                        if l.get("variant_id") == input_line.variant_id
                        and l.get("source", "catalog") == "catalog"
                        and not l.get("try_on_session_id")
                    ),
                    None,
                )
                if existing is not None:
                    new_qty = min(99, max(int(existing["quantity"]), input_line.quantity))
                    if new_qty != int(existing["quantity"]):
                        updated = await self.repo.update_line_quantity(
                            cart["cart_id"], existing["line_id"], quantity=new_qty
                        )
                        cart = updated or cart
                    kept += 1
                    continue

            # New line.
            line_doc = {
                "line_id": new_line_id(),
                "product_id": input_line.product_id,
                "variant_id": input_line.variant_id,
                "quantity": input_line.quantity,
                "source": input_line.source,
                "try_on_session_id": input_line.try_on_session_id,
                "try_on_card_id": input_line.try_on_card_id,
                "price_snapshot": variant["pricing"],
                "added_at": _now(),
            }
            updated = await self.repo.push_line(cart["cart_id"], line_doc)
            cart = updated or cart
            added += 1

        log.info(
            "cart.merged",
            cart_id=cart["cart_id"],
            customer_id=customer_id,
            kept_higher=kept,
            added=added,
            skipped_invalid=skipped,
        )
        return cart

    # ── Read-time enrichment ──────────────────────────────────
    async def hydrate_server_cart(
        self,
        cart_doc: dict[str, Any],
    ) -> ServerCart:
        """Attach display fields (titles, sizes, colours) and totals onto
        the server cart for the GET /cart response."""
        lines_raw = cart_doc.get("lines", []) or []
        product_ids = list({l["product_id"] for l in lines_raw})
        variant_ids = list({l["variant_id"] for l in lines_raw})
        products = await self._fetch_products(product_ids)
        variants = await self._fetch_variants(variant_ids)

        enriched_lines: list[ServerCartLine] = []
        subtotal = 0
        currency = "USD"
        item_count = 0
        for l in lines_raw:
            p = products.get(l["product_id"])
            v = variants.get(l["variant_id"])
            snapshot = VariantPricing(**l["price_snapshot"])
            currency = snapshot.currency
            quantity = int(l["quantity"])
            subtotal += int(snapshot.price_amount) * quantity
            item_count += quantity
            enriched_lines.append(
                ServerCartLine(
                    line_id=l["line_id"],
                    product_id=l["product_id"],
                    variant_id=l["variant_id"],
                    quantity=quantity,
                    source=l.get("source", "catalog"),
                    try_on_session_id=l.get("try_on_session_id"),
                    try_on_card_id=l.get("try_on_card_id"),
                    price_snapshot=snapshot,
                    added_at=l["added_at"],
                    product_title=p.get("title") if p else None,
                    variant_size=v.get("size") if v else None,
                    variant_color=v.get("color") if v else None,
                    variant_color_hex=v.get("color_hex") if v else None,
                    primary_media_asset_id=(p or {}).get("primary_media_asset_id"),
                )
            )

        return ServerCart(
            cart_id=cart_doc["cart_id"],
            customer_id=cart_doc["customer_id"],
            status=cart_doc["status"],
            lines=enriched_lines,
            item_count=item_count,
            snapshot_subtotal_amount=subtotal,
            currency=currency,
            last_validated_at=cart_doc.get("last_validated_at"),
            created_at=cart_doc["created_at"],
            updated_at=cart_doc["updated_at"],
        )
