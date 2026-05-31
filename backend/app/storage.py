"""Object storage with pluggable backends.

Two implementations behind one interface:

- **``local``** — files on the host filesystem under ``storage_local_dir``.
  ``presigned_get_url`` returns a regular HTTP URL pointing at the local
  ``/api/v1/storage/{path}`` route (see ``app/modules/storage_files``).
  No signature, no expiry — fine for dev / single-host deploys, avoids
  Backblaze's daily-egress cap during development.

- **``b2``** — Backblaze B2 native API via ``b2sdk``. Signed URLs use B2's
  ``get_download_authorization`` token, cached at half-life so the browser
  and ``next/image`` cache can hit deterministically.

Picked by ``Settings.storage_backend``. Both backends share the same
caller-facing interface (``put_object``, ``get_object``, ``delete_object``,
``head_object``, ``presigned_get_url``, ``presigned_put_url``) so callers
don't care which one is active.

Every key is prefixed with ``storage_key_prefix`` (default ``atelier/``)
exactly once so multiple projects can share one bucket or directory.

References:
- ARCHITECTURE.md §7 (Storage architecture, retention buckets, signed URLs)
- DATA_MODEL.md §5 (``media_assets``)
- REQ-066, REQ-068 (retention windows for anonymous artifacts)
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from b2sdk.v2 import B2Api, InMemoryAccountInfo
from b2sdk.v2.exception import FileNotPresent

from app.config import Settings, get_settings
from app.errors import ApiError, ErrorCode
from app.logging_setup import get_logger

log = get_logger(__name__)


# ── URL cache (shared across backends) ─────────────────────────────
class _UrlCache:
    """Process-local TTL cache for presigned URLs.

    Each entry lives for half its original validity window so a cache hit
    always returns a URL with at least 50% of its TTL remaining. Within that
    window every request for the same ``(object_key, ttl)`` pair returns
    the same URL — browser caches, the next/image optimizer cache, and any
    upstream CDN can all hit deterministically.
    """

    def __init__(self, max_entries: int = 5000) -> None:
        self.max = max_entries
        self.data: dict[tuple[str, int], tuple[str, datetime]] = {}
        self._lock = asyncio.Lock()

    def get(self, object_key: str, ttl_seconds: int) -> str | None:
        entry = self.data.get((object_key, ttl_seconds))
        if not entry:
            return None
        url, generated_at = entry
        elapsed = (datetime.now(timezone.utc) - generated_at).total_seconds()
        if elapsed > ttl_seconds / 2:
            return None
        return url

    async def put(self, object_key: str, ttl_seconds: int, url: str) -> None:
        async with self._lock:
            if len(self.data) >= self.max:
                oldest_key = min(self.data.items(), key=lambda kv: kv[1][1])[0]
                self.data.pop(oldest_key, None)
            self.data[(object_key, ttl_seconds)] = (
                url,
                datetime.now(timezone.utc),
            )


_url_cache = _UrlCache(max_entries=5000)


# ── Shared key-prefix helper ───────────────────────────────────────
def _full_key(settings: Settings, key: str) -> str:
    """Prepend ``storage_key_prefix`` exactly once."""
    prefix = settings.storage_key_prefix or ""
    cleaned = key.lstrip("/")
    if prefix and cleaned.startswith(prefix):
        return cleaned
    return f"{prefix}{cleaned}" if prefix else cleaned


# ── Public Storage interface ───────────────────────────────────────
class StorageBackend(Protocol):
    """Common shape every backend implements."""

    async def put_object(
        self,
        key: str,
        body: bytes,
        content_type: str,
        *,
        metadata: dict[str, str] | None = None,
        cache_control: str | None = None,
    ) -> str: ...

    async def get_object(self, key: str) -> bytes: ...

    async def delete_object(self, key: str) -> None: ...

    async def head_object(self, key: str) -> dict[str, Any] | None: ...

    async def presigned_get_url(self, key: str, *, expires_in: int = 3600) -> str: ...

    async def presigned_put_url(
        self, key: str, content_type: str, *, expires_in: int = 600
    ) -> str: ...


# ── B2 native backend ──────────────────────────────────────────────
class B2Storage:
    """Backblaze B2 native API. Async via ``asyncio.to_thread`` over b2sdk."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._api: B2Api | None = None
        self._bucket: Any | None = None
        self._download_base_url: str | None = None
        self._auth_lock = asyncio.Lock()

    def _full_key(self, key: str) -> str:
        return _full_key(self.settings, key)

    def _require_configured(self) -> None:
        s = self.settings
        if not s.b2_key_id or not s.b2_application_key or not s.b2_bucket_name:
            raise ApiError(
                ErrorCode.INTERNAL_ERROR,
                "Object storage is not configured.",
                http_status=503,
                details={
                    "hint": "Set B2_KEY_ID, B2_APPLICATION_KEY, B2_BUCKET_NAME in .env"
                },
            )

    def _authorize_sync(self) -> tuple[B2Api, Any, str]:
        info = InMemoryAccountInfo()
        api = B2Api(info)
        api.authorize_account(
            "production",
            self.settings.b2_key_id,
            self.settings.b2_application_key,
        )
        bucket = api.get_bucket_by_name(self.settings.b2_bucket_name)
        return api, bucket, info.get_download_url()

    async def _ensure_ready(self) -> tuple[B2Api, Any, str]:
        if self._bucket is not None and self._api is not None and self._download_base_url is not None:
            return self._api, self._bucket, self._download_base_url
        async with self._auth_lock:
            if self._bucket is None or self._api is None or self._download_base_url is None:
                self._require_configured()
                api, bucket, download_base = await asyncio.to_thread(self._authorize_sync)
                self._api = api
                self._bucket = bucket
                self._download_base_url = download_base
        assert self._api is not None and self._bucket is not None and self._download_base_url is not None
        return self._api, self._bucket, self._download_base_url

    async def put_object(
        self,
        key: str,
        body: bytes,
        content_type: str,
        *,
        metadata: dict[str, str] | None = None,
        cache_control: str | None = None,
    ) -> str:
        _, bucket, _ = await self._ensure_ready()
        full = self._full_key(key)
        file_info: dict[str, str] = {}
        if metadata:
            file_info.update({k: str(v) for k, v in metadata.items()})
        if cache_control:
            file_info["b2-cache-control"] = cache_control

        def _upload() -> Any:
            return bucket.upload_bytes(
                data_bytes=body,
                file_name=full,
                content_type=content_type,
                file_info=file_info or None,
            )

        await asyncio.to_thread(_upload)
        log.info("storage.put", backend="b2", key=full, bytes=len(body))
        return full

    async def get_object(self, key: str) -> bytes:
        _, bucket, _ = await self._ensure_ready()
        full = self._full_key(key)

        def _download() -> bytes:
            try:
                downloaded = bucket.download_file_by_name(full)
            except FileNotPresent as exc:
                raise FileNotFoundError(full) from exc
            from io import BytesIO

            buf = BytesIO()
            downloaded.save(buf)
            return buf.getvalue()

        try:
            return await asyncio.to_thread(_download)
        except FileNotFoundError as exc:
            raise ApiError(
                ErrorCode.NOT_FOUND,
                f"Object not found: {full}",
                http_status=404,
            ) from exc

    async def delete_object(self, key: str) -> None:
        _, bucket, _ = await self._ensure_ready()
        full = self._full_key(key)

        def _delete() -> None:
            try:
                versions = bucket.list_file_versions(file_name=full).iterator()
            except Exception:
                versions = []
            for version in versions:
                if getattr(version, "file_name", None) != full:
                    continue
                try:
                    bucket.delete_file_version(version.id_, version.file_name)
                except FileNotPresent:
                    continue
            log.info("storage.delete", backend="b2", key=full)

        await asyncio.to_thread(_delete)

    async def head_object(self, key: str) -> dict[str, Any] | None:
        _, bucket, _ = await self._ensure_ready()
        full = self._full_key(key)

        def _head() -> dict[str, Any] | None:
            try:
                info = bucket.get_file_info_by_name(full)
            except FileNotPresent:
                return None
            return {
                "ContentLength": getattr(info, "size", None),
                "ContentType": getattr(info, "content_type", None),
                "Metadata": getattr(info, "file_info", None) or {},
            }

        return await asyncio.to_thread(_head)

    async def presigned_get_url(self, key: str, *, expires_in: int = 3600) -> str:
        _, bucket, download_base = await self._ensure_ready()
        full = self._full_key(key)

        cached = _url_cache.get(full, expires_in)
        if cached:
            return cached

        def _authorize() -> str:
            token = bucket.get_download_authorization(
                file_name_prefix=full,
                valid_duration_in_seconds=int(expires_in),
            )
            return f"{download_base}/file/{bucket.name}/{full}?Authorization={token}"

        url = await asyncio.to_thread(_authorize)
        await _url_cache.put(full, expires_in, url)
        return url

    async def presigned_put_url(
        self,
        key: str,
        content_type: str,
        *,
        expires_in: int = 600,
    ) -> str:
        raise ApiError(
            ErrorCode.INTERNAL_ERROR,
            "Direct browser uploads aren't supported on the B2 native backend.",
            http_status=501,
            details={"hint": "Upload through the API; the server forwards to B2."},
        )


# ── Local filesystem backend ───────────────────────────────────────
class LocalStorage:
    """Files live in ``storage_local_dir`` on the host.

    The directory is created on first write. URLs returned by
    ``presigned_get_url`` point at the API's own
    ``/api/v1/storage/{path}`` route, so the browser can fetch them
    without any extra auth. There are no signatures — this backend is for
    dev / trusted-host use, not a public internet deployment.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _full_key(self, key: str) -> str:
        return _full_key(self.settings, key)

    def _base_dir(self) -> Path:
        # Resolve relative paths from the repo root (parent of backend/).
        # Allows ``storage`` in .env to put files at ``<repo>/storage``.
        raw = Path(self.settings.storage_local_dir)
        if raw.is_absolute():
            return raw
        backend_dir = Path(__file__).resolve().parent.parent
        repo_root = backend_dir.parent
        return (repo_root / raw).resolve()

    def _path_for(self, key: str) -> Path:
        full = self._full_key(key)
        # Defence in depth: reject any key that tries to escape the base dir.
        if ".." in full.split("/"):
            raise ApiError(
                ErrorCode.VALIDATION_ERROR,
                "Invalid storage path.",
                http_status=400,
            )
        return self._base_dir() / full

    async def put_object(
        self,
        key: str,
        body: bytes,
        content_type: str,
        *,
        metadata: dict[str, str] | None = None,
        cache_control: str | None = None,
    ) -> str:
        full = self._full_key(key)
        target = self._path_for(key)

        def _write() -> None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)

        await asyncio.to_thread(_write)
        log.info("storage.put", backend="local", key=full, bytes=len(body))
        return full

    async def get_object(self, key: str) -> bytes:
        target = self._path_for(key)

        def _read() -> bytes:
            try:
                return target.read_bytes()
            except FileNotFoundError as exc:
                raise FileNotFoundError(str(target)) from exc

        try:
            return await asyncio.to_thread(_read)
        except FileNotFoundError as exc:
            raise ApiError(
                ErrorCode.NOT_FOUND,
                f"Object not found: {self._full_key(key)}",
                http_status=404,
            ) from exc

    async def delete_object(self, key: str) -> None:
        target = self._path_for(key)

        def _delete() -> None:
            try:
                target.unlink()
            except FileNotFoundError:
                pass

        await asyncio.to_thread(_delete)
        log.info("storage.delete", backend="local", key=self._full_key(key))

    async def head_object(self, key: str) -> dict[str, Any] | None:
        target = self._path_for(key)
        if not target.exists():
            return None
        stat = target.stat()
        return {"ContentLength": stat.st_size, "ContentType": None, "Metadata": {}}

    async def presigned_get_url(self, key: str, *, expires_in: int = 3600) -> str:
        base = self.settings.storage_local_public_base_url.rstrip("/")
        return f"{base}/api/v1/storage/{self._full_key(key)}"

    async def presigned_put_url(
        self,
        key: str,
        content_type: str,
        *,
        expires_in: int = 600,
    ) -> str:
        raise ApiError(
            ErrorCode.INTERNAL_ERROR,
            "Direct browser uploads aren't supported on the local backend.",
            http_status=501,
        )


# ── Backwards-compat ``Storage`` facade that dispatches by setting ──
class Storage:
    """Thin adapter so existing callers (``get_storage().put_object(...)``)
    keep working. Picks the backend on first call based on
    ``Settings.storage_backend`` and proxies through.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._backend: StorageBackend | None = None

    def _resolve(self) -> StorageBackend:
        if self._backend is not None:
            return self._backend
        if self.settings.storage_backend == "local":
            self._backend = LocalStorage(self.settings)
        else:
            self._backend = B2Storage(self.settings)
        log.info("storage.backend_selected", backend=self.settings.storage_backend)
        return self._backend

    async def put_object(
        self,
        key: str,
        body: bytes,
        content_type: str,
        *,
        metadata: dict[str, str] | None = None,
        cache_control: str | None = None,
    ) -> str:
        return await self._resolve().put_object(
            key, body, content_type, metadata=metadata, cache_control=cache_control
        )

    async def get_object(self, key: str) -> bytes:
        return await self._resolve().get_object(key)

    async def delete_object(self, key: str) -> None:
        await self._resolve().delete_object(key)

    async def head_object(self, key: str) -> dict[str, Any] | None:
        return await self._resolve().head_object(key)

    async def presigned_get_url(self, key: str, *, expires_in: int = 3600) -> str:
        return await self._resolve().presigned_get_url(key, expires_in=expires_in)

    async def presigned_put_url(
        self, key: str, content_type: str, *, expires_in: int = 600
    ) -> str:
        return await self._resolve().presigned_put_url(
            key, content_type, expires_in=expires_in
        )


# ── Singleton accessor ─────────────────────────────────────────
_storage: Storage | None = None


def get_storage() -> Storage:
    """Return the process-wide storage facade. Lazy — built on first call."""
    global _storage
    if _storage is None:
        _storage = Storage()
    return _storage
