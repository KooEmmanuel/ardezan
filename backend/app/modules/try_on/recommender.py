"""Recommender agent (M4.3).

Takes the BodyProfile + CatalogContext and asks Gemini for outfit
recommendations. Output is forced to JSON via ``response_schema=
OutfitRecommendations``; we then **post-validate** every product_id and
variant_id against the context — the model can hallucinate IDs occasionally
and silently dropping bogus ones is safer than letting the customer see
broken cards.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from google.genai import types
from pydantic import ValidationError

from app.config import get_settings
from app.logging_setup import get_logger
from app.modules.try_on.agent_schemas import (
    OutfitItem,
    OutfitRecommendations,
    OutfitRecommendationsNamed,
    RecommendedOutfit,
)
from app.modules.try_on.cost import estimate_text_cost_cents
from app.modules.try_on.gemini_client import get_gemini_client

log = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RecommenderError(RuntimeError):
    """Raised on Gemini failure; carries the provider_call dict for audit."""

    def __init__(self, provider_call: dict[str, Any], message: str) -> None:
        super().__init__(message)
        self.provider_call = provider_call


_PROMPT_PREAMBLE = """\
You are a personal stylist. Based on the customer's body profile and the
available catalogue below, propose outfit recommendations.

HOW TO REFER TO PRODUCTS:
- For each item you choose, fill in ``product_title`` with the EXACT title
  as it appears in the catalogue (e.g. "Linen Blazer", "Slim Trousers").
- Use ``color`` to pick one of the colours listed for that product.
- Use ``size`` to pick one of the sizes listed for that product, choosing a
  size that fits the customer's measurements.
- Do NOT invent products. Only use titles that appear in the CATALOGUE list
  below.

Each outfit has 1 to {max_items} items. Vary the outfits — don't repeat the
same combination with minor changes. Use neutral, encouraging language.
"""


_SEEDED_RULES = """\
THIS IS A "TRY THIS PIECE ON ME" REQUEST. The customer selected a SPECIFIC
product. Treat it as the hero of every outfit you propose.

HARD RULES (do not violate):
- EVERY outfit you return MUST include "{seeded_title}" as one of its items.
  There are no exceptions.
- Vary the OTHER items around it — different trousers, shoes, layers, or
  accessories — so each outfit feels like a different way to wear the SAME
  hero piece.
- Do NOT swap the hero piece for a similar product. The customer wants this
  one specifically.
"""


def _format_profile(profile: dict[str, Any]) -> str:
    m = profile.get("estimated_measurements") or {}
    measurement_parts = [
        f"{name}={value}"
        for name, value in (
            ("height_cm", m.get("height_cm")),
            ("chest_cm", m.get("chest_cm")),
            ("waist_cm", m.get("waist_cm")),
            ("hip_cm", m.get("hip_cm")),
            ("inseam_cm", m.get("inseam_cm")),
        )
        if value is not None
    ]
    measurements_str = ", ".join(measurement_parts) or "not estimated"

    lines = [
        f"- body_shape: {profile.get('body_shape') or 'unspecified'}",
        f"- skin_undertone: {profile.get('skin_undertone') or 'unspecified'}",
        f"- measurements: {measurements_str}",
        f"- current_style_notes: {profile.get('current_style_notes') or '(none)'}",
        f"- fit_preference: {profile.get('fit_preference') or '(none)'}",
        f"- occasion: {profile.get('occasion') or '(none)'}",
    ]
    if profile.get("customer_prompt"):
        lines.append(f"- customer note: {profile['customer_prompt']}")
    return "\n".join(lines)


def _format_candidates(candidates: list[dict[str, Any]]) -> str:
    """Prompt-friendly catalogue listing.

    Omits internal IDs entirely so the model has no reason to invent them.
    Each row shows the title, category, price, AI tags, and the sizes /
    colours actually in stock.
    """
    rows: list[str] = []
    for p in candidates:
        tag_bits: list[str] = []
        for k in ("fabric_type", "formality", "fit_shape", "season"):
            if p.get(k):
                tag_bits.append(f"{k}={p[k]}")
        if p.get("color_palette"):
            tag_bits.append("palette=" + "|".join(p["color_palette"]))
        if p.get("compatibility_tags"):
            tag_bits.append("compat=" + "|".join(p["compatibility_tags"]))

        price_str = f"${p['price_amount'] / 100:.0f}"
        if p.get("sale_price_amount"):
            price_str += f" (was ${p['sale_price_amount'] / 100:.0f})"

        # Aggregate distinct sizes/colours that have stock.
        sizes: list[str] = []
        colours: list[str] = []
        for v in p.get("variants", []):
            if int(v.get("available_for_sale", 0)) <= 0:
                continue
            if v.get("size") and v["size"] not in sizes:
                sizes.append(v["size"])
            if v.get("color") and v["color"] not in colours:
                colours.append(v["color"])

        rows.append(
            f"- \"{p['title']}\" "
            f"({p['category']}{('/' + p['subcategory']) if p.get('subcategory') else ''}, "
            f"{price_str}, {', '.join(tag_bits) or 'no tags'})\n"
            f"    sizes: {', '.join(sizes) or '(no stock)'}\n"
            f"    colours: {', '.join(colours) or '(no stock)'}"
        )
    return "\n".join(rows)


def _seeded_title(context: dict[str, Any]) -> str | None:
    seeded_id = (context.get("constraints") or {}).get("seeded_product_id")
    if not seeded_id:
        return None
    for p in context.get("candidates", []):
        if p.get("product_id") == seeded_id:
            return p.get("title")
    return None


def _build_prompt(context: dict[str, Any]) -> str:
    profile = context["body_profile_summary"]
    constraints = context["constraints"]
    candidates = context["candidates"]

    seeded_title = _seeded_title(context)
    sections = [
        _PROMPT_PREAMBLE.format(
            max_items=constraints.get("max_items_per_outfit", 4),
        ).strip(),
    ]
    if seeded_title:
        sections.append(
            _SEEDED_RULES.format(seeded_title=seeded_title).strip()
        )
    seeded_title_display = f'"{seeded_title}"' if seeded_title else "none"
    sections += [
        "CUSTOMER PROFILE:\n" + _format_profile(profile),
        f"CONSTRAINTS: max_outfits={constraints.get('max_outfits', 10)}, "
        f"max_items_per_outfit={constraints.get('max_items_per_outfit', 4)}, "
        f"seeded_product_title={seeded_title_display}",
        f"CATALOGUE ({len(candidates)} products):\n" + _format_candidates(candidates),
        "Return JSON matching the OutfitRecommendationsNamed schema.",
    ]
    return "\n\n".join(sections)


# ── Title → ID resolution ───────────────────────────────────────────
def _normalise(s: str) -> str:
    return " ".join(s.lower().strip().split())


def _build_resolver_indexes(
    candidates: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[tuple[str, str], dict[str, Any]]]]:
    """Pre-compute lookup tables used by ``_resolve_named_to_ids``.

    Returns ``(by_title, variant_by_product_size_color)``:

    - ``by_title[normalised_title] = product_doc``
    - ``variant_by_product_size_color[product_id][(size_lower, color_lower)] = variant_doc``
    """
    by_title: dict[str, dict[str, Any]] = {}
    variants: dict[str, dict[tuple[str, str], dict[str, Any]]] = {}
    for p in candidates:
        by_title[_normalise(p["title"])] = p
        v_map: dict[tuple[str, str], dict[str, Any]] = {}
        for v in p.get("variants", []):
            key = (_normalise(v.get("size") or ""), _normalise(v.get("color") or ""))
            v_map[key] = v
        variants[p["product_id"]] = v_map
    return by_title, variants


def _resolve_named_to_ids(
    parsed_named: OutfitRecommendationsNamed,
    context: dict[str, Any],
) -> list[RecommendedOutfit]:
    """Map title + colour + size picks back to canonical IDs.

    Strategy per item:
      1. Match the title (case- and whitespace-insensitive) against catalog.
         Drop the item if no product matches.
      2. Find a variant matching (size, colour). If both don't match, try
         matching just the colour, then just the size, then fall back to
         the first in-stock variant for that product.
      3. Drop the item if the product has no in-stock variants at all.

    Outfits with no resolved items are dropped entirely.
    """
    by_title, variants_by_product = _build_resolver_indexes(context["candidates"])
    resolved_outfits: list[RecommendedOutfit] = []

    for named_outfit in parsed_named.outfits:
        resolved_items: list[OutfitItem] = []
        for named_item in named_outfit.items:
            product = by_title.get(_normalise(named_item.product_title))
            if not product:
                log.warning(
                    "recommender.title_unmatched",
                    title=named_item.product_title,
                    outfit_name=named_outfit.outfit_name,
                )
                continue

            v_map = variants_by_product.get(product["product_id"], {})
            target_size = _normalise(named_item.size or "")
            target_color = _normalise(named_item.color or "")

            variant: dict[str, Any] | None = None
            # 1. Exact size + colour
            if target_size and target_color:
                variant = v_map.get((target_size, target_color))
            # 2. Just colour
            if variant is None and target_color:
                for (_s, c), v in v_map.items():
                    if c == target_color and int(v.get("available_for_sale", 0)) > 0:
                        variant = v
                        break
            # 3. Just size
            if variant is None and target_size:
                for (s, _c), v in v_map.items():
                    if s == target_size and int(v.get("available_for_sale", 0)) > 0:
                        variant = v
                        break
            # 4. Any in-stock variant
            if variant is None:
                for v in v_map.values():
                    if int(v.get("available_for_sale", 0)) > 0:
                        variant = v
                        break
            if variant is None:
                log.warning(
                    "recommender.no_variant_in_stock",
                    title=named_item.product_title,
                    outfit_name=named_outfit.outfit_name,
                )
                continue

            resolved_items.append(
                OutfitItem(
                    product_id=product["product_id"],
                    variant_id=variant["variant_id"],
                    rationale=named_item.rationale,
                )
            )

        if resolved_items:
            resolved_outfits.append(
                RecommendedOutfit(
                    outfit_name=named_outfit.outfit_name,
                    items=resolved_items,
                    rationale=named_outfit.rationale,
                )
            )

    return resolved_outfits


def _validate(
    outfits: list[RecommendedOutfit],
    context: dict[str, Any],
) -> list[RecommendedOutfit]:
    """Drop any outfit referencing an unknown product_id or variant_id."""
    valid_product_ids = {p["product_id"] for p in context["candidates"]}
    valid_variant_ids: set[str] = set()
    product_for_variant: dict[str, str] = {}
    for p in context["candidates"]:
        for v in p["variants"]:
            valid_variant_ids.add(v["variant_id"])
            product_for_variant[v["variant_id"]] = p["product_id"]

    valid: list[RecommendedOutfit] = []
    for outfit in outfits:
        if not outfit.items:
            continue
        ok = True
        for item in outfit.items:
            if item.product_id not in valid_product_ids:
                log.warning(
                    "recommender.invalid_product_id",
                    product_id=item.product_id,
                    outfit_name=outfit.outfit_name,
                )
                ok = False
                break
            if item.variant_id not in valid_variant_ids:
                log.warning(
                    "recommender.invalid_variant_id",
                    variant_id=item.variant_id,
                    outfit_name=outfit.outfit_name,
                )
                ok = False
                break
            if product_for_variant[item.variant_id] != item.product_id:
                log.warning(
                    "recommender.variant_product_mismatch",
                    product_id=item.product_id,
                    variant_id=item.variant_id,
                )
                ok = False
                break
        if ok:
            valid.append(outfit)
    return valid


def _enforce_seeded_inclusion(
    outfits: list[RecommendedOutfit],
    context: dict[str, Any],
    seeded_id: str,
) -> list[RecommendedOutfit]:
    """Make sure every outfit contains the seeded product.

    If the model produced an outfit without the seed, we try to *repair* it
    by inserting a seed item (using a best-fit variant). Only if no in-stock
    variant of the seeded product exists do we drop the outfit entirely.

    This is what enforces the "see THIS shirt on me" promise of the per-product
    Try-on button.
    """
    seeded_product: dict[str, Any] | None = None
    for p in context.get("candidates", []):
        if p.get("product_id") == seeded_id:
            seeded_product = p
            break
    if seeded_product is None:
        # Catalog context dropped the seeded product (out of stock,
        # archived, etc.) — nothing to enforce; let outfits pass.
        log.warning("recommender.seed_not_in_context", seeded_id=seeded_id)
        return outfits

    seeded_title = seeded_product.get("title")

    def _first_in_stock_variant() -> dict[str, Any] | None:
        for v in seeded_product.get("variants", []) or []:
            if int(v.get("available_for_sale", 0)) > 0:
                return v
        return None

    fallback_variant = _first_in_stock_variant()
    if fallback_variant is None:
        # Seeded product has zero stock — every outfit that doesn't already
        # include some variant of it has to go.
        log.warning(
            "recommender.seed_out_of_stock", seeded_id=seeded_id, title=seeded_title
        )
        return [
            o for o in outfits if any(i.product_id == seeded_id for i in o.items)
        ]

    enforced: list[RecommendedOutfit] = []
    repaired = 0
    for outfit in outfits:
        has_seed = any(i.product_id == seeded_id for i in outfit.items)
        if has_seed:
            enforced.append(outfit)
            continue
        # Repair: insert the seed at the front. Cap items so we don't
        # exceed the per-outfit limit.
        max_items = int(
            (context.get("constraints") or {}).get("max_items_per_outfit", 4)
        )
        seed_item = OutfitItem(
            product_id=seeded_id,
            variant_id=fallback_variant["variant_id"],
            rationale=f"Your selected piece — {seeded_title}.",
        )
        new_items = [seed_item, *outfit.items][:max_items]
        enforced.append(
            RecommendedOutfit(
                outfit_name=outfit.outfit_name,
                items=new_items,
                rationale=outfit.rationale,
            )
        )
        repaired += 1

    if repaired:
        log.info(
            "recommender.seed_repaired_outfits",
            seeded_id=seeded_id,
            repaired_count=repaired,
            total=len(outfits),
        )
    return enforced


async def recommend(
    context: dict[str, Any],
) -> tuple[list[RecommendedOutfit], dict[str, Any]]:
    """Run the Recommender. Returns ``(valid_outfits, provider_call_metadata)``.

    Raises :class:`RecommenderError` on Gemini failure or invalid JSON.
    """
    settings = get_settings()
    client = get_gemini_client()
    model_name = settings.gemini_model_recommender

    if not context["candidates"]:
        provider_call = {
            "provider": "gemini",
            "model": model_name,
            "purpose": "recommender",
            "status": "skipped",
            "latency_ms": 0,
            "estimated_cost_amount": 0,
            "currency": "USD",
            "error_code": "EmptyCatalogContext",
            "error_message": "No eligible products in the catalogue.",
            "created_at": _now(),
        }
        raise RecommenderError(provider_call, "No catalogue candidates to recommend from")

    prompt = _build_prompt(context)
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=OutfitRecommendationsNamed,
        temperature=0.7,
        max_output_tokens=8192,
        # Disable internal thinking budget — see analyzer.py for the reason.
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )

    started = time.perf_counter()
    started_at = _now()
    try:
        response = await client.aio.models.generate_content(
            model=model_name,
            contents=[prompt],
            config=config,
        )
    except Exception as exc:  # noqa: BLE001
        latency_ms = int((time.perf_counter() - started) * 1000)
        provider_call = {
            "provider": "gemini",
            "model": model_name,
            "purpose": "recommender",
            "status": "failed",
            "latency_ms": latency_ms,
            "estimated_cost_amount": 0,
            "currency": "USD",
            "error_code": type(exc).__name__,
            "error_message": str(exc)[:300],
            "created_at": started_at,
        }
        log.warning("recommender.call_failed", error=str(exc)[:200])
        raise RecommenderError(provider_call, "Recommender call failed") from exc

    latency_ms = int((time.perf_counter() - started) * 1000)
    usage = getattr(response, "usage_metadata", None)
    estimated_cost = estimate_text_cost_cents(usage)

    parsed_named: OutfitRecommendationsNamed | None = getattr(response, "parsed", None)
    if parsed_named is None:
        text = getattr(response, "text", None) or ""
        try:
            parsed_named = OutfitRecommendationsNamed.model_validate_json(text)
        except ValidationError as exc:
            provider_call = {
                "provider": "gemini",
                "model": model_name,
                "purpose": "recommender",
                "status": "failed",
                "latency_ms": latency_ms,
                "estimated_cost_amount": estimated_cost,
                "currency": "USD",
                "error_code": "InvalidJsonOutput",
                "error_message": str(exc)[:300],
                "created_at": started_at,
            }
            log.warning("recommender.invalid_output", text_excerpt=text[:200])
            raise RecommenderError(
                provider_call, "Recommender returned invalid JSON"
            ) from exc

    # Resolve the model's title + colour + size picks back to canonical IDs
    # via a deterministic catalog lookup. Then run the original ID-based
    # validator as a final sanity pass.
    proposed = _resolve_named_to_ids(parsed_named, context)
    valid = _validate(proposed, context)

    # If this was a "try this piece on me" request, enforce the seed in
    # every outfit. Outfits the model returned without it get auto-repaired
    # by inserting the seed (so the customer always sees their hero piece);
    # if even repair fails the outfit is dropped.
    seeded_id = (context["constraints"] or {}).get("seeded_product_id")
    if seeded_id:
        valid = _enforce_seeded_inclusion(valid, context, seeded_id)

    # Trim to max_outfits.
    max_outfits = int(context["constraints"].get("max_outfits", 10))
    valid = valid[:max_outfits]

    provider_call = {
        "provider": "gemini",
        "model": model_name,
        "purpose": "recommender",
        "request_id": getattr(response, "response_id", None),
        "status": "ok",
        "latency_ms": latency_ms,
        "input_tokens": getattr(usage, "prompt_token_count", 0) if usage else 0,
        "output_tokens": getattr(usage, "candidates_token_count", 0) if usage else 0,
        "estimated_cost_amount": estimated_cost,
        "currency": "USD",
        "error_code": None,
        "error_message": None,
        "created_at": started_at,
        "extra": {
            "outfits_proposed": len(proposed),
            "outfits_valid": len(valid),
            "outfits_dropped": len(proposed) - len(valid),
        },
    }

    log.info(
        "recommender.ok",
        proposed=len(proposed),
        valid=len(valid),
        latency_ms=latency_ms,
        estimated_cost_cents=estimated_cost,
    )
    return valid, provider_call
