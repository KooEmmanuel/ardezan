# Ardezan — Operations Runbook

Operational reference for deploying and running the Ardezan MVP (Milestone 6 —
MVP Stabilization). Covers deployment, configuration, health checks, the data
retention policy, backup/restore, and incident playbooks.

> Scope: Phase 1 MVP. Owner + small test group, single region. Edge-case
> hardening and HA are Phase 2.

---

## 1. System topology

Three long-running processes plus two stateful dependencies:

| Process | Command | Purpose |
|---|---|---|
| API | `uv run uvicorn app.main:app` | FastAPI storefront + admin API |
| Worker | `uv run arq worker.main.WorkerSettings` | AI try-on jobs, email, retention + inventory cron |
| Frontend | `npm run build && npm run start` | Next.js storefront + admin UI |

| Dependency | Used by | Notes |
|---|---|---|
| MongoDB | API + Worker | Primary datastore. Atlas in prod. |
| Redis | API + Worker | arq job queue + rate-limit counters |
| Object storage | API + Worker | Uploaded photos + generated images (`local` dev / Backblaze `b2` prod) |
| SMTP | Worker | Transactional email (order, verify, reset) |
| Gemini API | Worker | Analyzer / Recommender / Designer / Safety |

The API and Worker **share** `app/` code, MongoDB, and config. Both must run the
same release. See `ARCHITECTURE.md`.

---

## 2. Prerequisites

- Python 3.12+ with `uv`.
- Node 20+ with npm (frontend).
- MongoDB 6+ (Atlas recommended in prod).
- Redis 6+.
- Object storage bucket (Backblaze B2 or any S3-compatible) for prod.
- SMTP provider (Resend / Mailgun / SES / Postmark).
- Gemini API key.
- Stripe account (test keys for staging, live for prod).

---

## 3. Configuration & secrets

Backend config is environment-driven — see `backend/.env.example` for the full
list. **Never commit real secrets.** In prod, inject via the platform secret
store.

Generate the three session/token secrets independently:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Production-critical settings:

| Variable | Production value |
|---|---|
| `APP_ENV` | `production` |
| `SESSION_SECRET_CUSTOMER` / `SESSION_SECRET_ADMIN` / `GUEST_TOKEN_SECRET` | unique random per env |
| `STORAGE_BACKEND` | `b2` (+ `B2_*` keys) |
| `AI_SAFETY_CLASSIFIER_ENABLED` | `true` |
| `AI_SAFETY_FAIL_OPEN` | **`false`** |
| `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` | live keys |
| `SMTP_TLS_MODE` | `starttls` (or `ssl`) |
| `CORS_ALLOWED_ORIGINS` | the storefront origin only |

> The API **refuses to boot in production** if any session secret is still a
> `change-me-*` placeholder (`app/main.py::_assert_safe_secrets`).

Frontend (`frontend/.env.example`):

| Variable | Purpose |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | Public API origin |
| `NEXT_PUBLIC_SITE_URL` | Public storefront origin (canonical URLs, sitemap, robots, OG) |

---

## 4. Deploy

The first admin is bootstrapped automatically when `ADMIN_BOOTSTRAP_EMAIL` +
`ADMIN_BOOTSTRAP_PASSWORD` are set on first boot (idempotent thereafter).

```bash
# Backend (API + Worker share this image/release)
cd backend
uv sync --no-dev
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000      # API process
uv run arq worker.main.WorkerSettings                       # Worker process

# Frontend
cd frontend
npm ci
npm run build
npm run start                                               # or deploy to Vercel
```

Database indexes are created idempotently on API startup (`app/db.py::init_db`)
— no separate migration step in Phase 1.

Stripe: register the webhook endpoint `POST /api/v1/webhooks/stripe` and set
`STRIPE_WEBHOOK_SECRET`. Required events: `payment_intent.succeeded`,
`payment_intent.payment_failed`, `charge.refunded`, `refund.*`.

### Release checklist

1. `cd backend && uv run pytest -q && uv run ruff check .`
2. `cd frontend && npm run typecheck && npm run build`
3. Confirm env/secrets present in target environment (no placeholders).
4. Deploy API + Worker from the **same** release.
5. Smoke check `/api/v1/health` and the storefront home.
6. Verify the worker logged `worker.startup`.

---

## 5. Health & observability

- **Liveness/readiness**: `GET /api/v1/health` → `{"status":"ok"}`. Plus the
  probe endpoints installed by `app/observability.py`.
- **Worker liveness**: the `worker_health` job; check for `worker.startup` in logs.
- **Structured logs** (`structlog`): set `LOG_FORMAT=json` in prod. Every
  request carries a `request_id`; key events: `webhook.*`, `inventory.*`,
  `retention.*`, `ai.*`.
- **Payment audit**: the `payment_events` collection is the inspectable ledger
  for every Stripe event (`received` → `processed`/`failed`, deduped by event id).
- **AI jobs**: the `ai_jobs` collection records stage progress + failures.

---

## 6. Data retention policy

Enforced by the **retention sweep** cron (`worker/jobs/retention.py`), which runs
every 5 minutes and performs four bounded sweeps (500 docs each):

| Data | Policy | Mechanism |
|---|---|---|
| Anonymous uploaded photos | `ANONYMOUS_UPLOAD_RETENTION_MINUTES` (default 15) | `media_assets.retention.expires_at` → storage object deleted |
| Anonymous generated images | `ANONYMOUS_GENERATED_RETENTION_HOURS` (default 24) | same |
| Anonymous try-on sessions | expire at TTL → `status=expired`, `deleted_at` set | `_sweep_try_on_sessions` |
| Stale AI jobs | non-terminal past TTL → `expired` | `_sweep_ai_jobs` |
| Abandoned checkout sessions | `open` past TTL → `expired` | `_sweep_checkout_sessions` |
| Inventory holds | released on expiry (separate 30s cron) | `worker/jobs/inventory_holds.py` |
| Registered saved photos | retained while consent active; removed on opt-out/account deletion | account service + media sweep |

Storage cleanup is idempotent: once an object is removed, `storage_object_deleted_at`
is stamped so subsequent sweeps skip it. Failures are logged and retried on the
next tick — a sweep never aborts midway.

**Verify manually** (e.g. after a retention incident):

```bash
cd backend
uv run python -c "import asyncio; from app.db import init_db, close_db; \
from worker.jobs.retention import run_once; \
async def m(): \
  await init_db(); print(await run_once()); await close_db(); \
asyncio.run(m())"
```

Automated coverage: `tests/test_retention.py`.

---

## 7. Backup & restore

### MongoDB

- **Atlas (prod)**: enable Continuous/Cloud Backups with point-in-time
  recovery. Target RPO ≤ 1h for the MVP.
- **Manual / self-hosted**:

```bash
# Backup
mongodump --uri "$MONGO_URL" --db "$MONGO_DB" --gzip --archive=ardezan-$(date +%F).gz

# Restore (into a clean target — verify env first!)
mongorestore --uri "$MONGO_URL" --gzip --archive=ardezan-YYYY-MM-DD.gz --drop
```

Indexes are recreated automatically on next API boot, so a `--drop` restore is safe.

### Object storage

- **Backblaze B2 (prod)**: enable bucket lifecycle + versioning; rely on B2
  retention for object recovery.
- Storage holds *regenerable* artifacts (uploads expire fast; generated images
  can be re-generated). Mongo is the source of truth — prioritize the DB backup.

### Restore drill (do before launch)

1. Restore the latest dump into a scratch database.
2. Boot the API against it; confirm `/api/v1/health` and that catalog + a sample
   order read correctly.
3. Record the wall-clock restore time as the recovery estimate.

---

## 8. Incident playbooks

### AI is misbehaving / costs spiking
Set `AI_KILL_SWITCH=true` (or flip it via the admin AI controls). Generation
stops; **catalog browsing and checkout keep working** (REQ-063). Re-enable once
resolved. Spend ceiling: `AI_DAILY_SPEND_CEILING_USD`.

### Suspected unsafe uploads getting through
Confirm `AI_SAFETY_CLASSIFIER_ENABLED=true` and `AI_SAFETY_FAIL_OPEN=false` in
prod. Fail-open must never be enabled in production.

### Payment webhook problems
Inspect `payment_events`. Rows in `failed` carry `failure_reason`. Stripe retries
automatically; duplicates are deduped by event id, so replays are safe. Orders
are idempotent on `checkout_session_id`.

### Oversold inventory
Holds are atomic (`inventory.create_hold` with a conditional `$expr`); the
last-unit race is covered by `tests/test_inventory.py`. If counts drift, the
worker can re-derive `held_units` from the `inventory_holds` collection.

### Secret rotation / forced logout
Rotating `SESSION_SECRET_ADMIN` / `SESSION_SECRET_CUSTOMER` (or the cookie salt)
invalidates all sessions in that audience — useful as a break-glass.

---

## 9. Known Phase-1 limitations

- Strict `mypy` reports pre-existing type gaps in some `app/` modules
  (admin/try-on); functional but to be cleaned in Phase 2.
- Refund handling is admin-driven (M3); webhook refund events are logged only.
- Single-region, no autoscaling/HA — Phase 2.

See `MILESTONES.md` §9 for the Phase 2 hardening scope.
