# Atelier Backend

The FastAPI + Python worker backend for Atelier, the AI-native clothing store.

See `../SPECS.md`, `../ARCHITECTURE.md`, `../DATA_MODEL.md`, `../API.md`, `../MILESTONES.md` for the design docs, and `../requirements-tracker.xlsx` for the Phase 1 requirement list this build maps to.

## Stack

- **Python 3.12+** with **FastAPI** (async modular monolith per ARCHITECTURE §4.2)
- **MongoDB Atlas** via the **motor** async driver
- **Redis-backed worker** via **arq** for AI orchestration and retention jobs (ADR-004)
- **google-genai** SDK for Gemini (Analyzer, Recommender, Designer agents per ADR-002)
- **argon2-cffi** for password hashing, **itsdangerous** for signed guest tokens
- **structlog** for structured JSON logs

## Local development

### Prerequisites

- Python 3.12 or newer
- [uv](https://github.com/astral-sh/uv) (`brew install uv` or `pipx install uv`)
- Docker (for local MongoDB + Redis), or your own instances

### One command for everything (recommended)

From the **project root** (the `ecommerce/` directory, not `backend/`):

```bash
python dev.py            # full stack: docker + API + worker + frontend (if present)
python dev.py --setup    # one-time setup, then exit
python dev.py --no-docker --no-worker --port 8080   # mix-and-match
```

`dev.py` handles `.env` creation, `uv sync`, Docker, the API, the worker, and the
Next.js dev server when it lands. Ctrl+C cleanly stops everything. See `dev.py --help`.

### Or run pieces manually

If you'd rather start individual services in their own terminals:

```bash
cp .env.example .env       # first time only
uv sync                    # install deps
docker compose up -d       # local Mongo + Redis

uv run uvicorn app.main:app --reload --port 8000      # API
uv run arq worker.main.WorkerSettings                 # worker (separate terminal)
```

- API base: `http://localhost:8000/api/v1`
- Health: `http://localhost:8000/api/v1/health`
- OpenAPI: `http://localhost:8000/docs`
- Storage smoke (dev only): `http://localhost:8000/api/v1/__debug__/storage`

### Tests

```bash
uv run pytest
```

### Lint and type-check

```bash
uv run ruff check .
uv run ruff format .
uv run mypy app worker
```

## Project layout

```
backend/
├── app/                              # FastAPI service (REST + SSE)
│   ├── main.py                       # App factory, lifespan, error handlers
│   ├── config.py                     # Settings (pydantic-settings)
│   ├── db.py                         # Motor client + collection names + index setup
│   ├── errors.py                     # ApiError + consistent error shape
│   ├── deps.py                       # Common FastAPI dependencies
│   ├── logging_setup.py              # Structured logging via structlog
│   └── modules/
│       ├── auth/                     # Customer + admin sessions, guest tokens         (M1 + M3)
│       ├── catalog/                  # Products, variants, size charts                 (M1 + M2)
│       ├── inventory/                # Variant stock, soft holds, atomic last-unit     (M2)
│       ├── cart/                     # Anonymous + registered carts, login merge       (M2)
│       ├── checkout/                 # Stripe sessions, tax, shipping, idempotency     (M2)
│       ├── orders/                   # Order lifecycle, refunds, fulfillment, audit    (M2 + M3)
│       ├── admin/                    # Admin CRUD, analytics, AI kill switch           (M3)
│       └── ai_orchestrator/          # AI job creation + SSE relay                     (M4)
└── worker/                           # Python worker (arq)
    ├── main.py                       # WorkerSettings
    └── jobs/
        ├── ai_orchestration.py       # Analyzer → Recommender → Designer               (M4)
        ├── retention.py              # Cleanup of anonymous photos and generated imgs  (M6)
        └── inventory_holds.py        # Expire soft holds                               (M2)
```

## Open decisions (placeholders in code)

Until these resolve in `../requirements-tracker.xlsx`, the defaults are:

| Decision | Default | Lock by |
|---|---|---|
| `OD-011` Launch market + currency | `US` / `USD` / `en-US` | Before M1 finalisation |
| `OD-012` Size chart source | Single house chart | Before M1 product model implementation |
| `OD-003` Payment provider | Stripe | Before M2 checkout |
| `OD-009` Tax approach | Stripe Tax | Before M2 checkout |
| `OD-007` MFA requirement | Recommended only | Before M3 admin launch |

Swap the corresponding values in `.env` (or the platform's secret store) once locked.

## Milestone status

- [x] **M1 Foundation** — app/worker boot, Mongo + indexes, storage, config, security primitives
- [x] **M2 Catalog Commerce** — catalog, cart revalidation, inventory holds, checkout, Stripe webhooks, orders, emails
- [x] **M3 Admin Operations** — admin auth, products/variants/stock, orders/refunds, customers, AI controls, audit logs, dashboard
- [x] **M4 AI Try-On v1** — upload safety, analyzer/recommender/designer, SSE progress, results grid, add-to-cart, quotas/kill switch
- [x] **M5 Accounts + Fitting Room** — customer auth, password reset, order history, saved photo + consent, fitting room, guest claim
- [ ] **M6 MVP Stabilization** — broader test coverage, accessibility pass, SEO metadata, retention/webhook/race verification, runbook

> Update this checklist as milestone acceptance is verified against `../MILESTONES.md`.
