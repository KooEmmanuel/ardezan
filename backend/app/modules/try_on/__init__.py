"""AI Try-On module — job creation, upload safety, SSE progress stream.

The orchestrator runs in the worker process (per ARCHITECTURE §4.3 + ADR-004):
the API endpoint creates the job and returns immediately; the worker handles
Analyzer → Recommender → Designer with progress events streamed back.

M4 sub-milestones:
- M4.1 (this turn): job creation, upload safety pipeline, SSE skeleton,
  worker stub that walks the job through stages.
- M4.2: Analyzer agent (Gemini multimodal, structured output).
- M4.3: Recommender agent (CatalogContext + function calling).
- M4.4: Designer loop (Nano Banana per outfit, generated image storage).

References:
- API.md §10 (Try-On API)
- ARCHITECTURE.md §5.7 + §8 (Orchestrator + AI architecture)
- DATA_MODEL.md §9.1, §9.2 (try_on_sessions + ai_jobs)
- REQ-052, REQ-053, REQ-018, REQ-057, REQ-058, REQ-062, REQ-063
"""
