"""One-shot: copy every file under ``storage/`` to the configured B2 bucket.

Run before flipping ``STORAGE_BACKEND=local`` to ``STORAGE_BACKEND=b2`` so
that ``media_assets`` rows pointing at object keys keep resolving — the
keys on disk and in B2 land at the same path.

Idempotent: each file is ``head_object``-checked first; only missing keys
are uploaded. Use ``--force`` to re-upload everything (e.g. after fixing
a bad key prefix).

Run::

    .venv/bin/python -m scripts.migrate_local_to_b2          # dry run
    .venv/bin/python -m scripts.migrate_local_to_b2 --apply  # do it
    .venv/bin/python -m scripts.migrate_local_to_b2 --apply --force
"""
from __future__ import annotations

import argparse
import asyncio
import mimetypes
import sys
from pathlib import Path

from app.config import get_settings
from app.storage import B2Storage, LocalStorage


def _strip_prefix(key: str, prefix: str) -> str:
    """The local key already includes the storage prefix; the B2 backend
    re-adds it inside ``put_object``. Strip exactly one copy so the final
    B2 key matches what the DB has."""
    if prefix and key.startswith(prefix):
        return key[len(prefix):]
    return key


def _content_type_for(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


async def main(apply: bool, force: bool) -> int:
    settings = get_settings()
    if not settings.b2_key_id or not settings.b2_application_key or not settings.b2_bucket_name:
        print("B2 credentials missing — set B2_KEY_ID, B2_APPLICATION_KEY, B2_BUCKET_NAME in .env first.")
        return 2

    local = LocalStorage(settings)
    b2 = B2Storage(settings)

    base = local._base_dir()  # noqa: SLF001 — we own the implementation
    if not base.exists():
        print(f"Local storage directory not found: {base}")
        return 2

    prefix = settings.storage_key_prefix or ""

    files: list[Path] = [p for p in base.rglob("*") if p.is_file()]
    if not files:
        print(f"No files under {base}.")
        return 0

    total_bytes = sum(p.stat().st_size for p in files)
    print(f"Scanning {len(files)} files ({total_bytes / 1024 / 1024:.1f} MB) under {base}")
    print(f"Target bucket: {settings.b2_bucket_name}   Prefix: {prefix!r}")
    print()

    uploaded = 0
    skipped = 0
    failed = 0
    bytes_uploaded = 0

    for i, path in enumerate(files, start=1):
        rel = path.relative_to(base).as_posix()
        unprefixed_key = _strip_prefix(rel, prefix)
        full_key = f"{prefix}{unprefixed_key}" if prefix else unprefixed_key

        # Idempotency: head_object is one round-trip and cheaper than a
        # blind re-upload. Skip if the file already exists on B2 unless
        # the caller asked for --force.
        if not force:
            try:
                existing = await b2.head_object(unprefixed_key)
            except Exception as exc:  # noqa: BLE001
                print(f"  [{i:>3}/{len(files)}] HEAD failed for {full_key}: {exc}")
                existing = None
            if existing is not None:
                skipped += 1
                continue

        body = path.read_bytes()
        ct = _content_type_for(path)

        if not apply:
            print(f"  [{i:>3}/{len(files)}] would upload  {full_key}  ({len(body):,} bytes, {ct})")
            uploaded += 1
            bytes_uploaded += len(body)
            continue

        try:
            written = await b2.put_object(unprefixed_key, body, content_type=ct)
        except Exception as exc:  # noqa: BLE001
            print(f"  [{i:>3}/{len(files)}] FAILED   {full_key}: {exc}")
            failed += 1
            continue
        uploaded += 1
        bytes_uploaded += len(body)
        print(f"  [{i:>3}/{len(files)}] uploaded  {written}  ({len(body):,} bytes)")

    print()
    if apply:
        print(
            f"Uploaded: {uploaded}   Skipped (already on B2): {skipped}   "
            f"Failed: {failed}   Bytes: {bytes_uploaded / 1024 / 1024:.1f} MB"
        )
    else:
        print(
            f"DRY RUN — would upload {uploaded} files "
            f"({bytes_uploaded / 1024 / 1024:.1f} MB); "
            f"{skipped} already on B2. Pass --apply to do it."
        )
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Actually upload (default is dry run).")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-upload even if the key already exists on B2.",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(main(apply=args.apply, force=args.force)))
