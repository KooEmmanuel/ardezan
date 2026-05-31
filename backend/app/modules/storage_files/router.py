"""Serves local-backend storage files.

Mounted only when ``Settings.storage_backend == "local"``. Streams the file
bytes with the right content-type and a long ``Cache-Control`` so the
browser and the ``next/image`` optimizer can cache hard. Path-traversal is
prevented at two layers: FastAPI's ``path`` converter doesn't include
``..`` segments automatically because we resolve and check, and we also
verify the resolved path stays inside the configured base directory.
"""
from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.config import get_settings

router = APIRouter()


def _base_dir() -> Path:
    settings = get_settings()
    raw = Path(settings.storage_local_dir)
    if raw.is_absolute():
        return raw
    backend_dir = Path(__file__).resolve().parent.parent.parent.parent
    repo_root = backend_dir.parent
    return (repo_root / raw).resolve()


@router.get("/{path:path}", include_in_schema=False)
async def serve_local_file(path: str):
    base = _base_dir()
    if not path:
        raise HTTPException(status_code=404)
    # FastAPI's ``path`` converter accepts ``..`` segments. Strip them and
    # then verify the resolved target stays inside ``base`` — defence in
    # depth against directory traversal.
    candidate = (base / path).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid path") from exc

    if not candidate.is_file():
        raise HTTPException(status_code=404)

    mime, _ = mimetypes.guess_type(str(candidate))
    return FileResponse(
        candidate,
        media_type=mime or "application/octet-stream",
        headers={"Cache-Control": "public, max-age=86400, immutable"},
    )
