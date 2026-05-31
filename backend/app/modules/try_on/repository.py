"""Try-on data access — ai_jobs + try_on_sessions + media_assets writes."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db import C


class TryOnRepository:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self.db = db
        self.try_on_sessions = db[C.try_on_sessions]
        self.ai_jobs = db[C.ai_jobs]
        self.media_assets = db[C.media_assets]

    # ── ai_jobs reads ──────────────────────────────────────────
    async def find_job(self, job_id: str) -> dict[str, Any] | None:
        return await self.ai_jobs.find_one({"job_id": job_id})

    async def insert_job(self, doc: dict[str, Any]) -> None:
        await self.ai_jobs.insert_one(doc)

    # ── try_on_sessions reads ──────────────────────────────────
    async def find_session(self, session_id: str) -> dict[str, Any] | None:
        return await self.try_on_sessions.find_one({"try_on_session_id": session_id})

    async def insert_session(self, doc: dict[str, Any]) -> None:
        await self.try_on_sessions.insert_one(doc)

    # ── media_assets ───────────────────────────────────────────
    async def insert_media_asset(self, doc: dict[str, Any]) -> None:
        await self.media_assets.insert_one(doc)
