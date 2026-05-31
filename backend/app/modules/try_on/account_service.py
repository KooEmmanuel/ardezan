"""Fitting Room service.

Owns the per-customer try-on session views, saved-photo opt-in, and body-
profile opt-in. All operations are ownership-enforced (404 if a session
exists but belongs to another customer — no existence leak).

Deletion is soft: ``deleted_at`` is set on the session, every related
``generated_images`` row, and the related ``media_assets`` rows. The actual
object-storage deletion happens via the retention worker (M6).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db import C
from app.errors import ApiError, ErrorCode
from app.logging_setup import get_logger
from app.storage import get_storage

log = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class FittingRoomService:
    def __init__(self, db: AsyncIOMotorDatabase[Any]) -> None:
        self.db = db

    # ── List ───────────────────────────────────────────────────
    async def list_for_customer(
        self,
        customer_id: str,
        *,
        limit: int = 24,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        query = {"customer_id": customer_id, "deleted_at": None}
        cursor = (
            self.db[C.try_on_sessions]
            .find(query)
            .sort("created_at", -1)
            .skip(offset)
            .limit(limit)
        )
        sessions = await cursor.to_list(limit)
        total = await self.db[C.try_on_sessions].count_documents(query)

        # Look up the first generated image per session for the grid thumbnail.
        rep_image_ids: list[str] = []
        for s in sessions:
            for card in s.get("result_cards", []) or []:
                gid = card.get("generated_image_id")
                if gid:
                    rep_image_ids.append(gid)
                    break

        media_by_image = await self._media_ids_for_generated_images(rep_image_ids)
        url_by_image = await self._sign_urls(
            list(media_by_image.values()), expires_in=3600
        )

        items: list[dict[str, Any]] = []
        for s in sessions:
            rep_image_id: str | None = None
            rep_outfit: str | None = None
            for card in s.get("result_cards", []) or []:
                if card.get("generated_image_id"):
                    rep_image_id = card["generated_image_id"]
                    rep_outfit = card.get("outfit_name")
                    break
            url: str | None = None
            if rep_image_id:
                media_id = media_by_image.get(rep_image_id)
                if media_id:
                    url = url_by_image.get(media_id)
            items.append(
                {
                    "try_on_session_id": s["try_on_session_id"],
                    "source": s.get("source", "upload"),
                    "status": s["status"],
                    "created_at": s["created_at"],
                    "result_card_count": len(s.get("result_cards") or []),
                    "representative_image_url": url,
                    "representative_outfit_name": rep_outfit,
                }
            )
        return items, total

    # ── Single detail ──────────────────────────────────────────
    async def get_for_customer(
        self, session_id: str, customer_id: str
    ) -> dict[str, Any]:
        session = await self.db[C.try_on_sessions].find_one(
            {
                "try_on_session_id": session_id,
                "customer_id": customer_id,
                "deleted_at": None,
            }
        )
        if not session:
            raise ApiError(
                ErrorCode.NOT_FOUND,
                f"Try-on session not found: {session_id}",
                http_status=404,
            )

        cards = session.get("result_cards") or []
        image_ids = [
            c["generated_image_id"]
            for c in cards
            if c.get("generated_image_id")
        ]
        media_by_image = await self._media_ids_for_generated_images(image_ids)
        url_by_media = await self._sign_urls(
            list(media_by_image.values()), expires_in=3600
        )

        enriched_cards: list[dict[str, Any]] = []
        for card in cards:
            url: str | None = None
            gid = card.get("generated_image_id")
            if gid:
                media_id = media_by_image.get(gid)
                if media_id:
                    url = url_by_media.get(media_id)
            enriched_cards.append({**card, "image_url": url})

        return {
            "try_on_session_id": session["try_on_session_id"],
            "source": session.get("source", "upload"),
            "status": session["status"],
            "optional_inputs": session.get("optional_inputs") or {},
            "body_profile_snapshot": session.get("body_profile_snapshot"),
            "result_cards": enriched_cards,
            "created_at": session["created_at"],
            "updated_at": session.get("updated_at", session["created_at"]),
        }

    # ── Public read (anonymous + customer) ─────────────────────
    async def get_public(
        self,
        session_id: str,
        *,
        requesting_customer_id: str | None,
    ) -> dict[str, Any]:
        """Read a try-on session without requiring a customer cookie.

        - Anonymous sessions (no ``customer_id``) are readable by anyone with
          the session id — same threat model as the SSE endpoint.
        - Customer-owned sessions return 404 unless the requester is the
          owner. No existence leak across accounts.
        """
        session = await self.db[C.try_on_sessions].find_one(
            {"try_on_session_id": session_id, "deleted_at": None}
        )
        if not session:
            raise ApiError(
                ErrorCode.NOT_FOUND,
                f"Try-on session not found: {session_id}",
                http_status=404,
            )

        owner_customer_id = session.get("customer_id")
        if owner_customer_id and owner_customer_id != requesting_customer_id:
            raise ApiError(
                ErrorCode.NOT_FOUND,
                f"Try-on session not found: {session_id}",
                http_status=404,
            )

        cards = session.get("result_cards") or []
        image_ids = [
            c["generated_image_id"]
            for c in cards
            if c.get("generated_image_id")
        ]
        media_by_image = await self._media_ids_for_generated_images(image_ids)
        url_by_media = await self._sign_urls(
            list(media_by_image.values()), expires_in=3600
        )

        enriched_cards: list[dict[str, Any]] = []
        for card in cards:
            url: str | None = None
            gid = card.get("generated_image_id")
            if gid:
                media_id = media_by_image.get(gid)
                if media_id:
                    url = url_by_media.get(media_id)
            enriched_cards.append({**card, "image_url": url})

        return {
            "try_on_session_id": session["try_on_session_id"],
            "source": session.get("source", "upload"),
            "status": session["status"],
            "optional_inputs": session.get("optional_inputs") or {},
            "body_profile_snapshot": session.get("body_profile_snapshot"),
            "result_cards": enriched_cards,
            "created_at": session["created_at"],
            "updated_at": session.get("updated_at", session["created_at"]),
        }

    # ── Delete ─────────────────────────────────────────────────
    async def delete_for_customer(
        self, session_id: str, customer_id: str
    ) -> None:
        session = await self.db[C.try_on_sessions].find_one(
            {
                "try_on_session_id": session_id,
                "customer_id": customer_id,
                "deleted_at": None,
            }
        )
        if not session:
            raise ApiError(
                ErrorCode.NOT_FOUND,
                f"Try-on session not found: {session_id}",
                http_status=404,
            )

        now = _now()
        # Cascade: every related generated_images + media_assets row gets
        # deleted_at set so the retention worker (M6) tears them down.
        await self.db[C.generated_images].update_many(
            {"try_on_session_id": session_id},
            {"$set": {"retention.deleted_at": now, "updated_at": now}},
        )
        await self.db[C.media_assets].update_many(
            {"owner_type": "try_on_session", "owner_id": session_id},
            {"$set": {"retention.deleted_at": now, "updated_at": now}},
        )
        await self.db[C.try_on_sessions].update_one(
            {"try_on_session_id": session_id},
            {
                "$set": {
                    "deleted_at": now,
                    "status": "deleted",
                    "updated_at": now,
                }
            },
        )
        log.info(
            "fitting_room.session_deleted",
            try_on_session_id=session_id,
            customer_id=customer_id,
        )

    # ── Saved photo ────────────────────────────────────────────
    async def opt_in_saved_photo(
        self,
        customer_id: str,
        *,
        try_on_session_id: str,
        consent_version: str,
    ) -> dict[str, Any]:
        session = await self.db[C.try_on_sessions].find_one(
            {
                "try_on_session_id": try_on_session_id,
                "customer_id": customer_id,
                "deleted_at": None,
            }
        )
        if not session:
            raise ApiError(
                ErrorCode.NOT_FOUND,
                f"Try-on session not found: {try_on_session_id}",
                http_status=404,
            )
        media_asset_id = session.get("uploaded_media_asset_id")
        if not media_asset_id:
            raise ApiError(
                ErrorCode.NOT_FOUND,
                "Session has no uploaded photo to save.",
                http_status=404,
            )

        now = _now()
        # Promote the upload to registered retention so the cleanup worker
        # leaves it alone.
        await self.db[C.media_assets].update_one(
            {"media_asset_id": media_asset_id},
            {
                "$set": {
                    "retention.policy": "registered_until_deleted",
                    "retention.expires_at": None,
                    "updated_at": now,
                }
            },
        )
        await self.db[C.customers].update_one(
            {"customer_id": customer_id},
            {
                "$set": {
                    "saved_photo.media_asset_id": media_asset_id,
                    "saved_photo.opted_in": True,
                    "saved_photo.photo_uploaded_at": now,
                    "saved_photo.photo_consent_version": consent_version,
                    "updated_at": now,
                }
            },
        )
        log.info(
            "fitting_room.saved_photo_opted_in",
            customer_id=customer_id,
            media_asset_id=media_asset_id,
            consent_version=consent_version,
        )
        return await self.saved_photo_status(customer_id)

    async def delete_saved_photo(self, customer_id: str) -> dict[str, Any]:
        customer = await self.db[C.customers].find_one(
            {"customer_id": customer_id, "deleted_at": None}
        )
        if not customer:
            raise ApiError(
                ErrorCode.NOT_FOUND, "Account not found.", http_status=404
            )

        saved = customer.get("saved_photo") or {}
        media_asset_id = saved.get("media_asset_id")
        now = _now()

        if media_asset_id:
            await self.db[C.media_assets].update_one(
                {"media_asset_id": media_asset_id},
                {"$set": {"retention.deleted_at": now, "updated_at": now}},
            )

        await self.db[C.customers].update_one(
            {"customer_id": customer_id},
            {
                "$set": {
                    "saved_photo.media_asset_id": None,
                    "saved_photo.opted_in": False,
                    "saved_photo.photo_uploaded_at": None,
                    "saved_photo.photo_consent_version": None,
                    "updated_at": now,
                }
            },
        )
        log.info("fitting_room.saved_photo_deleted", customer_id=customer_id)
        return await self.saved_photo_status(customer_id)

    async def saved_photo_status(self, customer_id: str) -> dict[str, Any]:
        customer = await self.db[C.customers].find_one(
            {"customer_id": customer_id, "deleted_at": None}
        )
        if not customer:
            return {
                "opted_in": False,
                "has_photo": False,
                "photo_url": None,
                "photo_uploaded_at": None,
                "photo_consent_version": None,
            }
        saved = customer.get("saved_photo") or {}
        media_asset_id = saved.get("media_asset_id")
        url: str | None = None
        if media_asset_id and saved.get("opted_in"):
            media = await self.db[C.media_assets].find_one(
                {"media_asset_id": media_asset_id}
            )
            if media and not (media.get("retention") or {}).get("deleted_at"):
                url = await get_storage().presigned_get_url(
                    media["storage"]["object_key"], expires_in=3600
                )
        return {
            "opted_in": bool(saved.get("opted_in", False)),
            "has_photo": bool(media_asset_id and url),
            "photo_url": url,
            "photo_uploaded_at": saved.get("photo_uploaded_at"),
            "photo_consent_version": saved.get("photo_consent_version"),
        }

    # ── Body profile ───────────────────────────────────────────
    async def opt_in_body_profile(
        self, customer_id: str, *, try_on_session_id: str
    ) -> dict[str, Any]:
        session = await self.db[C.try_on_sessions].find_one(
            {
                "try_on_session_id": try_on_session_id,
                "customer_id": customer_id,
                "deleted_at": None,
            }
        )
        if not session:
            raise ApiError(
                ErrorCode.NOT_FOUND,
                f"Try-on session not found: {try_on_session_id}",
                http_status=404,
            )
        snapshot = session.get("body_profile_snapshot")
        if not snapshot:
            raise ApiError(
                ErrorCode.CONFLICT,
                "This session doesn't have a body profile yet — wait for the Analyzer to finish.",
                http_status=409,
            )

        now = _now()
        await self.db[C.customers].update_one(
            {"customer_id": customer_id},
            {
                "$set": {
                    "body_profile.opted_in": True,
                    "body_profile.source_try_on_session_id": try_on_session_id,
                    "body_profile.measurements_estimate": snapshot.get(
                        "measurements_estimate"
                    ),
                    "body_profile.fit_preference": (
                        session.get("optional_inputs") or {}
                    ).get("fit_preference"),
                    "body_profile.updated_at": now,
                    "updated_at": now,
                }
            },
        )
        log.info(
            "fitting_room.body_profile_opted_in",
            customer_id=customer_id,
            try_on_session_id=try_on_session_id,
        )
        return await self.body_profile_status(customer_id)

    async def delete_body_profile(self, customer_id: str) -> dict[str, Any]:
        now = _now()
        await self.db[C.customers].update_one(
            {"customer_id": customer_id},
            {
                "$set": {
                    "body_profile.opted_in": False,
                    "body_profile.source_try_on_session_id": None,
                    "body_profile.measurements_estimate": None,
                    "body_profile.updated_at": now,
                    "updated_at": now,
                }
            },
        )
        log.info("fitting_room.body_profile_deleted", customer_id=customer_id)
        return await self.body_profile_status(customer_id)

    async def body_profile_status(self, customer_id: str) -> dict[str, Any]:
        customer = await self.db[C.customers].find_one(
            {"customer_id": customer_id, "deleted_at": None}
        )
        if not customer:
            return {
                "opted_in": False,
                "source_try_on_session_id": None,
                "measurements_estimate": None,
                "fit_preference": None,
                "updated_at": None,
            }
        bp = customer.get("body_profile") or {}
        return {
            "opted_in": bool(bp.get("opted_in", False)),
            "source_try_on_session_id": bp.get("source_try_on_session_id"),
            "measurements_estimate": bp.get("measurements_estimate"),
            "fit_preference": bp.get("fit_preference"),
            "updated_at": bp.get("updated_at"),
        }

    # ── Helpers ────────────────────────────────────────────────
    async def _media_ids_for_generated_images(
        self, generated_image_ids: list[str]
    ) -> dict[str, str]:
        if not generated_image_ids:
            return {}
        cursor = self.db[C.generated_images].find(
            {"generated_image_id": {"$in": generated_image_ids}},
            projection={"generated_image_id": 1, "media_asset_id": 1, "_id": 0},
        )
        return {
            doc["generated_image_id"]: doc["media_asset_id"]
            async for doc in cursor
            if doc.get("media_asset_id")
        }

    async def _sign_urls(
        self, media_asset_ids: list[str], *, expires_in: int
    ) -> dict[str, str]:
        if not media_asset_ids:
            return {}
        cursor = self.db[C.media_assets].find(
            {"media_asset_id": {"$in": media_asset_ids}},
            projection={"media_asset_id": 1, "storage.object_key": 1, "retention.deleted_at": 1, "_id": 0},
        )
        keys: dict[str, str] = {}
        async for doc in cursor:
            if (doc.get("retention") or {}).get("deleted_at"):
                continue
            key = (doc.get("storage") or {}).get("object_key")
            if key:
                keys[doc["media_asset_id"]] = key

        storage = get_storage()
        signed: dict[str, str] = {}
        for media_id, key in keys.items():
            try:
                signed[media_id] = await storage.presigned_get_url(
                    key, expires_in=expires_in
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("fitting_room.sign_failed", media_id=media_id, error=str(exc))
        return signed
