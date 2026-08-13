# Contributing

## Local setup

```bash
git clone <repo>
cd survivalschool

# Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edit with your local DB/Redis URLs and any real API keys
alembic upgrade head
python -m app.seed --with-demo-data   # optional: creates demo admin/instructor/student accounts

# Frontend
cd ../frontend
npm install
cp .env.local.example .env.local  # if present; otherwise set NEXT_PUBLIC_API_BASE_URL directly
```

You need a real local PostgreSQL 16 and Redis 7 for the backend to run or
its test suite to pass — there is no sqlite/in-memory fallback. The quickest
path is `docker compose up -d postgres redis` and pointing `DATABASE_URL`/
`REDIS_URL` at those containers.

## Before opening a PR

```bash
cd backend
ruff check app tests --fix     # auto-fix what can be auto-fixed
pip-audit -r requirements.txt  # must report no known vulnerabilities
APP_ENV=test python -m pytest -q  # must be 24/24 passing (or more, if you added tests)

cd ../frontend
npm run lint
npm run typecheck
npm run build
```

All of the above run in CI (`docs/CI_CD.md`) — running them locally first
avoids a red CI run for something you could have caught in seconds.

## Code conventions

- **Backend**: `from __future__ import annotations` at the top of every
  module; type hints throughout; `ruff` rule sets `E`, `F`, `W`, `I` (see
  `pyproject.toml`) — line length is not enforced (`E501` ignored) but
  import sorting and unused-variable/import checks are.
- **No lambda assignments** (`E731`) — use `def`. No unused variables
  (`F841`) — if a return value is genuinely unused, don't assign it.
- **Services vs. routes**: business logic belongs in `app/services/*.py`,
  not inline in `app/api/v1/*.py` route handlers — routes should read as
  "validate input, call a service, return a schema," not contain scoring,
  gamification, or notification logic directly. See `docs/ARCHITECTURE.md`.
- **New protected endpoints** must declare a `require_permission(...)` or
  `require_role(...)` dependency explicitly — there is no global "logged in
  users can do X" default; see `app/dependencies.py`.
- **Never trust a client-submitted score/correctness field.** Any new
  assessment-adjacent endpoint must grade server-side against the question
  bank, following the existing pattern in `app/services/scoring_service.py`.
  This is the single most load-bearing convention in the codebase — see
  `docs/SECURITY.md`.
- **New external integrations** (a third AI provider, a second automation
  platform) should follow the abstraction pattern in
  `app/services/ai_provider.py` — an interface plus a mock implementation
  used in tests, not a direct vendor SDK call from route handlers.

## Documentation discipline

If your change affects behavior described in `docs/*.md`, update the
relevant doc in the same PR. This codebase's guiding constraint (see the
root `README.md`) is that documentation must never claim something is
tested/working/configured that it isn't — if you implement something but
can't verify it end-to-end in your environment (e.g. no network access to a
third-party API), say so explicitly in both the code comment and the doc,
the way `app/services/ai_provider.py` and `app/services/n8n_service.py`
already do. A false "this works" is worse than an honest "this is
implemented but unverified."

## Adding a migration

```bash
cd backend
alembic revision --autogenerate -m "describe the change"
# review the generated file by hand — autogenerate is a starting point
alembic upgrade head
```

## Adding a Kubernetes-relevant config value

New settings in `app/config.py::Settings` need a matching entry in
`infra/k8s/01-configmap.yaml` (non-secret) or
`infra/k8s/02-secret.yaml.example` (secret) with the **exact same field
name** — `Settings` uses `extra="ignore"`, so a typo'd env var name fails
silently rather than raising, which makes this an easy mistake to miss in
review. Double-check the name matches before merging.
