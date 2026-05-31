"""MongoDB MCP server integration for ADK agents.

Two modes, picked by ``settings.mcp_enabled``:

  - ``False`` (default): the agent's data tools talk to Mongo directly
    via Motor.
  - ``True``: the agent connects to the official ``mongodb-mcp-server``
    (npm package, spawned via ``npx`` as a stdio subprocess) and exposes
    its tools to Gemini. This is the path that satisfies the hackathon's
    "MongoDB MCP server" requirement.

Both modes use the same ``MONGO_URL`` — one connection string for the
whole app, local in dev, Atlas in prod.

We expose a single function — ``get_catalog_search_runner()`` — that
returns an async callable. Callers don't need to know which backend is
serving the query.
"""
from __future__ import annotations

import os
import re
from typing import Any, Awaitable, Callable

import structlog
from motor.motor_asyncio import AsyncIOMotorClient

from app.config import get_settings
from app.db import C

log = structlog.get_logger(__name__)


CatalogSearchRunner = Callable[..., Awaitable[list[dict[str, Any]]]]


# ── Direct-Mongo fallback (used when MCP is disabled) ────────────────

def _direct_mongo_runner() -> CatalogSearchRunner:
    """Returns an async function that queries Mongo directly via Motor.

    The result shape matches what ``app.modules.try_on.recommender`` expects
    so the same downstream tools can consume it — flat ai-metadata keys,
    ``price_amount`` (not nested), and an inline variants list with
    in-stock sizes/colours.
    """
    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongo_url)
    db = client[settings.mongo_db]
    products = db[C.products]
    variants = db[C.variants]

    async def _run(
        query_text: str,
        category: str | None = None,
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        terms = [t for t in re.findall(r"[\w-]+", query_text.lower()) if len(t) > 2]
        match: dict[str, Any] = {"status": "published", "deleted_at": None}
        if category:
            match["category"] = category
        if terms:
            or_clauses: list[dict[str, Any]] = []
            for t in terms:
                rx = {"$regex": re.escape(t), "$options": "i"}
                or_clauses.append({"title": rx})
                or_clauses.append({"tags": rx})
                or_clauses.append({"category": rx})
            match["$or"] = or_clauses

        cursor = products.find(
            match,
            projection={
                "_id": 0,
                "product_id": 1,
                "title": 1,
                "category": 1,
                "subcategory": 1,
                "tags": 1,
                "pricing": 1,
                "ai": 1,
            },
        ).limit(limit)
        items = await cursor.to_list(limit)
        product_ids = [it["product_id"] for it in items]

        # Pull variants for the matched products in one round-trip so we
        # can include in-stock sizes/colours per candidate.
        variant_cursor = variants.find(
            {
                "product_id": {"$in": product_ids},
                "deleted_at": None,
                "status": "active",
            },
            projection={
                "_id": 0,
                "variant_id": 1,
                "product_id": 1,
                "sku": 1,
                "size": 1,
                "color": 1,
                "inventory": 1,
            },
        )
        variants_by_product: dict[str, list[dict[str, Any]]] = {}
        async for v in variant_cursor:
            pid = v["product_id"]
            inv = v.get("inventory") or {}
            variants_by_product.setdefault(pid, []).append(
                {
                    "variant_id": v["variant_id"],
                    "sku": v.get("sku"),
                    "size": v.get("size"),
                    "color": v.get("color"),
                    "available_for_sale": int(inv.get("stock_on_hand", 0)),
                }
            )

        out: list[dict[str, Any]] = []
        for it in items:
            pricing = it.pop("pricing", {}) or {}
            ai = it.pop("ai", {}) or {}
            out.append(
                {
                    "product_id": it["product_id"],
                    "title": it["title"],
                    "category": it["category"],
                    "subcategory": it.get("subcategory"),
                    "tags": it.get("tags", []),
                    # Flat keys the recommender expects:
                    "price_amount": pricing.get("base_price_amount"),
                    "sale_price_amount": pricing.get("compare_at_price_amount"),
                    "currency": pricing.get("currency", "USD"),
                    "fabric_type": ai.get("fabric_type"),
                    "formality": ai.get("formality"),
                    "fit_shape": ai.get("fit_shape"),
                    "season": ai.get("season"),
                    "color_palette": ai.get("color_palette") or [],
                    "compatibility_tags": ai.get("compatibility_tags") or [],
                    "variants": variants_by_product.get(it["product_id"], []),
                }
            )
        log.debug(
            "mcp_toolset.direct_query",
            terms=terms,
            category=category,
            hits=len(out),
        )
        return out

    return _run


# ── MCP-backed runner (mongodb-mcp-server) ───────────────────────────

def _mcp_runner() -> CatalogSearchRunner:
    """Routes catalog queries through the official ``mongodb-mcp-server``.

    The MCP server speaks JSON-RPC over stdio. We launch it as a
    subprocess on first use (per the standard MCP pattern) and reuse
    the connection across calls.

    NOTE: this path is dormant until ``MCP_ENABLED=true``. Switching it
    on is a one-line config change — no agent changes needed because
    the result shape is identical to the direct path.
    """
    # Import here so the absence of MCP packages on a default install
    # doesn't break the rest of the app.
    from google.adk.tools.mcp_tool.mcp_session_manager import (  # type: ignore[import-not-found]
        StdioConnectionParams,
    )
    from google.adk.tools.mcp_tool.mcp_toolset import (  # type: ignore[import-not-found]
        McpToolset,
        StdioServerParameters,
    )

    settings = get_settings()
    # Single source of truth: the MCP server connects to the same DB the
    # app uses. Local URL in dev, Atlas SRV string in prod.
    mongo_uri = settings.mongo_url

    # Per https://www.mongodb.com/docs/mcp-server/get-started/, the
    # connection string is passed via the MONGODB_URI environment
    # variable. ``--readOnly`` is recommended unless we need writes
    # (we don't — the agent only reads the catalog).
    raw_params = StdioServerParameters(
        command="npx",
        args=["-y", "mongodb-mcp-server@latest", "--readOnly"],
        env={"MONGODB_URI": mongo_uri, "PATH": os.environ.get("PATH", "")},
    )
    # StdioConnectionParams is the wrapper ADK v2.1+ expects. The default
    # 5s timeout is too tight for a cold npx + Atlas handshake.
    server_params = StdioConnectionParams(server_params=raw_params, timeout=60.0)
    state: dict[str, Any] = {"toolset": None, "tools": None}

    async def _ensure() -> dict[str, Any]:
        if state["toolset"] is None:
            toolset = McpToolset(connection_params=server_params)
            tools = await toolset.get_tools()
            tool_map = {t.name: t for t in tools}
            # The MongoDB MCP server doesn't auto-pick up MONGODB_URI from
            # env in --readOnly mode; we have to call its ``connect`` tool
            # to establish the session against our cluster. One call per
            # toolset lifetime.
            connect_tool = tool_map.get("connect")
            if connect_tool is not None:
                connect_result = await connect_tool.run_async(
                    args={"connectionString": mongo_uri},
                    tool_context=None,
                )
                log.info(
                    "mcp_toolset.mongodb_connected",
                    tools=list(tool_map.keys()),
                    connect_ok=not (
                        isinstance(connect_result, dict)
                        and connect_result.get("isError")
                    ),
                )
            else:
                log.warning(
                    "mcp_toolset.no_connect_tool",
                    available=list(tool_map.keys()),
                )
            state["toolset"] = toolset
            state["tools"] = tool_map
        return state["tools"]

    async def _run(
        query_text: str,
        category: str | None = None,
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        tools = await _ensure()
        # The MongoDB MCP server exposes a flat ``find`` tool.
        find_tool = tools.get("find") or tools.get("mongodb_find")
        if not find_tool:
            log.warning("mcp_toolset.no_find_tool", available=list(tools.keys()))
            return []

        terms = [t for t in re.findall(r"[\w-]+", query_text.lower()) if len(t) > 2]
        filter_doc: dict[str, Any] = {"status": "published", "deleted_at": None}
        if category:
            filter_doc["category"] = category
        if terms:
            filter_doc["$or"] = [
                {"title": {"$regex": re.escape(t), "$options": "i"}}
                for t in terms
            ]

        result = await find_tool.run_async(
            args={
                "database": settings.mongo_db,
                "collection": C.products,
                "filter": filter_doc,
                "limit": limit,
            },
            tool_context=None,
        )
        # MongoDB MCP wraps results in MCP CallToolResult — pull the
        # JSON content out of the text blocks.
        items = _extract_documents(result)

        # Pull in-stock variants for the matched products via a second
        # MCP find so the recommender can render sizes/colours in its
        # prompt. Same MCP session, same partner integration.
        product_ids = [it.get("product_id") for it in items if it.get("product_id")]
        variants_by_product: dict[str, list[dict[str, Any]]] = {}
        if product_ids:
            v_result = await find_tool.run_async(
                args={
                    "database": settings.mongo_db,
                    "collection": C.variants,
                    "filter": {
                        "product_id": {"$in": product_ids},
                        "deleted_at": None,
                        "status": "active",
                    },
                    "limit": 500,
                },
                tool_context=None,
            )
            for v in _extract_documents(v_result):
                pid = v.get("product_id")
                if not pid:
                    continue
                inv = v.get("inventory") or {}
                variants_by_product.setdefault(pid, []).append(
                    {
                        "variant_id": v.get("variant_id"),
                        "sku": v.get("sku"),
                        "size": v.get("size"),
                        "color": v.get("color"),
                        "available_for_sale": int(inv.get("stock_on_hand", 0)),
                    }
                )

        out: list[dict[str, Any]] = []
        for it in items:
            pricing = it.get("pricing", {}) or {}
            ai = it.get("ai", {}) or {}
            out.append(
                {
                    "product_id": it.get("product_id"),
                    "title": it.get("title"),
                    "category": it.get("category"),
                    "subcategory": it.get("subcategory"),
                    "tags": it.get("tags", []),
                    # Match the direct-runner shape so the recommender
                    # consumes either path identically.
                    "price_amount": pricing.get("base_price_amount"),
                    "sale_price_amount": pricing.get("compare_at_price_amount"),
                    "currency": pricing.get("currency", "USD"),
                    "fabric_type": ai.get("fabric_type"),
                    "formality": ai.get("formality"),
                    "fit_shape": ai.get("fit_shape"),
                    "season": ai.get("season"),
                    "color_palette": ai.get("color_palette") or [],
                    "compatibility_tags": ai.get("compatibility_tags") or [],
                    "variants": variants_by_product.get(it.get("product_id"), []),
                }
            )
        log.debug(
            "mcp_toolset.find_completed",
            terms=terms,
            category=category,
            hits=len(out),
            total_variants=sum(len(v) for v in variants_by_product.values()),
        )
        return out

    return _run


def _extract_documents(result: Any) -> list[dict[str, Any]]:
    """Normalise the ``mongodb-mcp-server`` ``find`` result into a list of
    dicts.

    The server's response shape (v1.11+) is a CallToolResult whose
    ``content`` is a list of TextContent blocks. Typical pattern:

        block[0]: "Query on collection 'X' resulted in N documents.
                   Returning M documents."   <- summary text
        block[1]: "...WARNING: untrusted user data...
                   <untrusted-user-data-UUID>
                   [{...}, {...}]   <- the JSON array we want
                   </untrusted-user-data-UUID>"

    We pull the JSON out of any block, tolerating either plain JSON,
    NDJSON, or wrapped-in-security-tags JSON.
    """
    import json as _json
    import re as _re

    if isinstance(result, list):
        return [d for d in result if isinstance(d, dict)]
    if isinstance(result, dict) and "documents" in result:
        return list(result["documents"])

    # MCP CallToolResult: result.content is a list of content blocks.
    content = getattr(result, "content", None) or (
        result.get("content") if isinstance(result, dict) else None
    )
    if not content:
        return []

    docs: list[dict[str, Any]] = []
    # Match the JSON payload inside MongoDB MCP's security wrapper tags,
    # whatever the UUID suffix is.
    untrusted_re = _re.compile(
        r"<untrusted-user-data-[^>]+>\s*(?P<body>[\[{].*?[\]}])\s*</untrusted-user-data-[^>]+>",
        _re.DOTALL,
    )

    for block in content:
        text = getattr(block, "text", None) or (
            block.get("text") if isinstance(block, dict) else None
        )
        if not text:
            continue
        text = text.strip()
        if not text:
            continue

        # 1) Try wrapped-in-security-tags first.
        wrapped = untrusted_re.search(text)
        if wrapped:
            try:
                parsed = _json.loads(wrapped.group("body"))
                if isinstance(parsed, list):
                    docs.extend(d for d in parsed if isinstance(d, dict))
                    continue
                if isinstance(parsed, dict):
                    docs.append(parsed)
                    continue
            except _json.JSONDecodeError:
                pass

        # 2) Plain JSON array / object.
        try:
            parsed = _json.loads(text)
            if isinstance(parsed, list):
                docs.extend(d for d in parsed if isinstance(d, dict))
                continue
            if isinstance(parsed, dict):
                docs.append(parsed)
                continue
        except _json.JSONDecodeError:
            pass

        # 3) NDJSON fallback.
        for line in text.splitlines():
            line = line.strip()
            if not line or not line.startswith(("{", "[")):
                continue
            try:
                obj = _json.loads(line)
                if isinstance(obj, dict):
                    docs.append(obj)
            except _json.JSONDecodeError:
                pass
    return docs


# ── Public factory ────────────────────────────────────────────────────

_runner: CatalogSearchRunner | None = None


def get_catalog_search_runner() -> CatalogSearchRunner:
    """Returns the configured runner. Cached after first call."""
    global _runner
    if _runner is not None:
        return _runner
    settings = get_settings()
    if settings.mcp_enabled:
        log.info("mcp_toolset.mode", mode="mongodb_mcp_server")
        _runner = _mcp_runner()
    else:
        log.info("mcp_toolset.mode", mode="direct_mongo")
        _runner = _direct_mongo_runner()
    return _runner
