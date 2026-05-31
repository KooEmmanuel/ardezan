"""Ardezan worker — long-running AI orchestration and retention jobs.

Runs as a separate process from the FastAPI service so AI generation and
clean-up jobs don't block API requests, and so jobs survive a browser
disconnect (ARCHITECTURE.md §4.3, ADR-004).
"""
