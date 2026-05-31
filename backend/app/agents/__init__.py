"""Ardezan ADK agents (Google Agent Development Kit).

Each module here defines one ``google.adk.agents.Agent`` plus the tools
it exposes. Agents are the long-term orchestration layer for the AI
features — over time, the procedural pipelines in ``app/modules/try_on``
will move behind these agents.

Phase 1 (hackathon scope):
    - ``stylist_agent``: takes a refinement prompt + prior body profile,
      queries the catalog (via MongoDB MCP when enabled, direct Mongo
      otherwise), proposes outfit titles, and triggers image generation.
"""
from app.agents.stylist_agent import build_stylist_agent, run_stylist_refine

__all__ = ["build_stylist_agent", "run_stylist_refine"]
