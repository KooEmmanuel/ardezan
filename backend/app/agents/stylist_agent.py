"""Stylist agent — Google ADK wrapper around our existing recommender +
catalog query + designer logic.

The agent's loop:

1. Receives a refinement prompt + body profile from the caller.
2. Uses ``search_catalog`` (MongoDB-backed; routed via the MongoDB MCP
   server when enabled — see ``app/agents/mcp_toolset.py``) to find
   candidate pieces matching the brief.
3. Uses ``propose_outfits`` to compose 5-10 outfit candidates against
   the body profile.
4. Returns a structured plan that the worker then renders into images.

This file deliberately keeps the agent thin — the heavy lifting still
lives in ``app/modules/try_on/recommender.py`` and ``designer.py``. The
ADK Agent is an *orchestrator* that decides when and how to call those
existing capabilities; we don't re-implement Gemini calls here.
"""
from __future__ import annotations

import contextvars
import json
from typing import Any

import structlog
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import FunctionTool
from google.genai.types import Content, Part
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import get_settings

log = structlog.get_logger(__name__)


# ── Tool implementations ──────────────────────────────────────────────
#
# Tools are plain async Python functions. The ADK introspects their
# signatures and docstrings to expose them to Gemini.

async def search_catalog_tool(
    query_text: str,
    category: str | None = None,
    limit: int = 12,
) -> str:
    """Search the published product catalog.

    Use this to find pieces that match a styling brief. Examples:
        - query_text="lightweight linen shirts", category="Tops"
        - query_text="warmer outerwear for cool evenings"

    Args:
        query_text: A natural-language description of what to look for.
            The function tokenises it and searches across title, tags,
            and category. It is OK to repeat key style words.
        category: Optional category filter (e.g. "Tops", "Outerwear").
        limit: Maximum results to return (default 12).

    Returns:
        A JSON string of objects with keys:
            product_id, title, category, base_price_amount, currency,
            tags, ai_metadata (formality / fabric_type / season / color_palette).
    """
    from app.agents.mcp_toolset import get_catalog_search_runner

    runner = get_catalog_search_runner()
    items = await runner(query_text=query_text, category=category, limit=limit)
    return json.dumps(items, default=str)


async def propose_outfits_tool(
    body_profile_json: str,
    candidates_json: str,
    refinement_brief: str,
    count: int = 5,
) -> str:
    """Compose outfit suggestions against a body profile and candidate pieces.

    Internally this calls Gemini with the existing recommender prompt +
    constrained schema, then resolves the named outfits back to concrete
    variant IDs the worker can render.

    Args:
        body_profile_json: JSON string of the customer's body profile.
        candidates_json: JSON string of candidate products (from search_catalog).
        refinement_brief: The user's natural-language brief.
        count: How many outfits to propose (default 5; max 10).

    Returns:
        JSON string with shape:
            {"outfits": [{"title": "...", "items": [...], "rationale": "..."}, ...]}
    """
    # NOTE: lazy import so unit tests that mock the agent don't pull in
    # the whole try_on graph.
    from app.modules.try_on import recommender as _recommender

    try:
        body_profile = json.loads(body_profile_json)
        candidates = json.loads(candidates_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid JSON input: {exc}"})

    if not candidates:
        return json.dumps({"error": "No candidates supplied", "outfits": []})

    desired = max(1, min(10, int(count)))
    context: dict[str, Any] = {
        "body_profile_summary": body_profile,
        "constraints": {
            "max_outfits": desired,
            "max_items_per_outfit": 4,
        },
        "candidates": candidates,
        "optional_inputs": {"prompt": refinement_brief},
        "seeded_product_id": None,
    }
    try:
        outfits, _provider_call = await _recommender.recommend(context)
    except _recommender.RecommenderError as exc:
        log.warning("stylist_agent.recommender_failed", error=str(exc))
        return json.dumps({"error": "Recommender failed", "outfits": []})

    # Stash the (outfits, candidates) pair on the *per-run* register so
    # ``run_stylist_refine`` can pick them up to build cards. A context
    # variable (not module state) keeps concurrent refine jobs isolated —
    # the worker runs several jobs at once.
    outfit_dicts = [
        o.model_dump() if hasattr(o, "model_dump") else o for o in outfits
    ]
    register = _proposal_register.get()
    if register is not None:
        register["outfits"] = outfit_dicts
        register["candidates"] = candidates
    return json.dumps(outfit_dicts, default=str)


# Per-run register so ``run_stylist_refine`` can return both the agent's
# structured outfits *and* the candidate list the tool worked on, without
# polluting the LLM's tool-result payload. ContextVar (instead of a module
# global) so concurrent jobs can't cross-contaminate each other's plans:
# the tool call executes inside the run's task tree and therefore sees the
# dict its own run installed.
_proposal_register: contextvars.ContextVar[dict[str, Any] | None] = (
    contextvars.ContextVar("stylist_proposal_register", default=None)
)


# ── Agent definition ──────────────────────────────────────────────────

_AGENT_INSTRUCTION = """\
You are Ardezan's personal stylist agent. You help customers refine their
try-on session.

You are given:
  - The customer's body profile (a structured JSON summary of body shape,
    proportions, undertone, etc.).
  - The customer's refinement brief (free-form text — what they want
    changed about the prior outfits).
  - The session's prior outfits (so you understand what came before).

Your job:
  1. Search the catalog using ``search_catalog`` with focused queries
     that match the refinement brief. Run multiple searches if the brief
     mixes categories (e.g. "warmer trousers and a less formal jacket").
  2. Compose outfit suggestions with ``propose_outfits``, passing the
     body profile, the candidates you found, and the brief verbatim.
  3. Return a short natural-language summary (2-3 sentences) explaining
     the styling decisions to the customer. Do NOT enumerate every
     product; the UI renders the cards separately. Reference fabric,
     drape, or fit in your summary — that's what stylists do.

Constraints:
  - Never invent product IDs. Always go through the tools.
  - Stay on-brand: Ardezan is minimalist DTC clothing, considered
    fabrics, monochrome palette. Avoid loud or trend-chasing language.
  - If the catalog has nothing matching the brief, say so honestly and
    suggest one viable adjacent direction.
"""


def build_stylist_agent() -> Agent:
    """Construct (but do not run) the stylist Agent.

    Kept as a factory so tests can build isolated instances without
    touching module-level state.
    """
    import os

    settings = get_settings()
    # ADK reads GOOGLE_API_KEY; we standardised on GEMINI_API_KEY for the
    # rest of the codebase. Bridge them so both work.
    if settings.gemini_api_key and not os.environ.get("GOOGLE_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = settings.gemini_api_key
    return Agent(
        name="ardezan_stylist",
        model=settings.gemini_model_recommender,
        instruction=_AGENT_INSTRUCTION,
        tools=[
            FunctionTool(search_catalog_tool),
            FunctionTool(propose_outfits_tool),
        ],
    )


# ── Runner / public entry point ───────────────────────────────────────

_runner: Runner | None = None
_session_service: InMemorySessionService | None = None


def _get_runner() -> Runner:
    global _runner, _session_service
    if _runner is None:
        _session_service = InMemorySessionService()
        _runner = Runner(
            agent=build_stylist_agent(),
            app_name="ardezan-stylist",
            session_service=_session_service,
        )
    return _runner


async def run_stylist_refine(
    *,
    db: AsyncIOMotorDatabase[Any],
    session_id: str,
    user_id: str,
    refinement_brief: str,
    body_profile: dict[str, Any],
    prior_outfit_titles: list[str] | None = None,
) -> dict[str, Any]:
    """Public entry point used by the worker / refine endpoint.

    Returns a structured result:
        {
          "summary": "...",                # the agent's narrative
          "outfit_plan": [...],            # parsed propose_outfits result
          "tool_calls": [...],             # for the admin AI-jobs page
        }
    """
    runner = _get_runner()
    # Ensure the session exists in the InMemorySessionService.
    assert _session_service is not None
    try:
        await _session_service.create_session(
            app_name="ardezan-stylist",
            user_id=user_id,
            session_id=session_id,
        )
    except Exception:  # noqa: BLE001
        # Already exists from a prior turn — fine, we'll just append.
        pass

    prior_titles_blob = ", ".join(prior_outfit_titles or []) or "(none)"
    seed_msg = (
        f"Refinement brief: {refinement_brief.strip()}\n\n"
        f"Body profile (JSON): {json.dumps(body_profile, default=str)}\n\n"
        f"Prior outfit titles: {prior_titles_blob}\n\n"
        "Search the catalog, propose outfits, and return a short summary."
    )
    new_message = Content(role="user", parts=[Part(text=seed_msg)])

    summary_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    outfit_plan_raw: str | None = None

    # Fresh per-run register; the propose_outfits tool writes into it.
    proposal: dict[str, Any] = {"outfits": None, "candidates": None}
    _register_token = _proposal_register.set(proposal)
    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=new_message,
        ):
            # Capture tool calls + final response text from event stream.
            # ADK events carry function_call / function_response pairs.
            content = getattr(event, "content", None)
            if content and content.parts:
                for part in content.parts:
                    if getattr(part, "function_call", None):
                        fc = part.function_call
                        tool_calls.append(
                            {
                                "name": fc.name,
                                "args": dict(fc.args) if fc.args else {},
                            }
                        )
                    if getattr(part, "function_response", None):
                        fr = part.function_response
                        if fr.name == "propose_outfits_tool":
                            outfit_plan_raw = (
                                fr.response.get("result")
                                if isinstance(fr.response, dict)
                                else None
                            )
                    if (
                        getattr(part, "text", None)
                        and event.is_final_response()
                    ):
                        summary_parts.append(part.text)
    finally:
        _proposal_register.reset(_register_token)

    summary = "\n".join(summary_parts).strip()
    try:
        outfit_plan = json.loads(outfit_plan_raw) if outfit_plan_raw else []
    except (ValueError, TypeError):
        outfit_plan = []

    # Pull the (outfits, candidates) pair the tool stashed on this run's
    # register.
    structured_outfits = proposal.get("outfits") or []
    candidates_used = proposal.get("candidates") or []

    log.info(
        "stylist_agent.refine_complete",
        session_id=session_id,
        user_id=user_id,
        outfit_count=len(structured_outfits),
        candidate_count=len(candidates_used),
        tool_call_count=len(tool_calls),
    )
    return {
        "summary": summary,
        "outfit_plan": outfit_plan,
        "structured_outfits": structured_outfits,
        "candidates": candidates_used,
        "tool_calls": tool_calls,
    }


