# Contributing

## Local setup

This project runs the same way on Linux, macOS, and Windows 11 — the
commands below are grouped by shell, not by feature set. Nothing in this
codebase is Windows-only or Linux-only; the differences are just shell
syntax (activating a venv, setting an env var inline) and are called out
explicitly rather than assumed.

**The one thing every platform needs first**: a real local PostgreSQL 16 and
Redis 7. There is no sqlite/in-memory fallback — the test suite and the app
itself both require them. The path that works identically everywhere,
including Windows 11, is Docker Desktop:

```bash
git clone <repo>
cd survivalschool
docker compose up -d postgres redis
```

On Windows 11, install Docker Desktop with the WSL2 backend (the default in
any current install) — `docker compose` then behaves exactly as it does on
Linux/macOS, run from PowerShell, cmd, or a WSL terminal, your choice.
Running Postgres/Redis natively on Windows without Docker (e.g. via the
PostgreSQL Windows installer) also works fine; just update `DATABASE_URL`/
`REDIS_URL` in `.env` to match whatever host/port/credentials you set up.

### Backend

<table>
<tr><th>macOS / Linux (bash/zsh)</th><th>Windows 11 (PowerShell)</th></tr>
<tr><td>

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
python -m app.seed --with-demo-data
```

</td><td>

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
alembic upgrade head
python -m app.seed --with-demo-data
```

</td></tr>
</table>

Two Windows-specific notes, both one-time gotchas rather than ongoing
friction:

- If `.venv\Scripts\Activate.ps1` fails with a message about execution
  policies, PowerShell is blocking script execution by default. Run
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once (this is a
  standard, safe setting for local development, not a security workaround
  specific to this project) and re-open the terminal.
- Using Command Prompt instead of PowerShell: activate with
  `.venv\Scripts\activate.bat` instead of the `.ps1` script.

After that, `edit .env` (any editor) the same way on every platform — the
`.env` file format and every variable in it (see `docs/ENVIRONMENT.md`) is
identical regardless of OS. If you're running Postgres/Redis via
`docker compose up -d postgres redis` from the step above, the default
`.env.example` values (`localhost:5432`/`localhost:6379`) already work as-is.

### Frontend

Identical on every platform — Node.js's tooling doesn't have the
shell-syntax differences Python's venv activation does:

```bash
cd frontend
npm install
cp .env.local.example .env.local  # Windows: copy .env.local.example .env.local
```

## Before opening a PR

<table>
<tr><th>macOS / Linux</th><th>Windows 11 (PowerShell)</th></tr>
<tr><td>

```bash
cd backend
ruff check app tests --fix
pip-audit -r requirements.txt
APP_ENV=test python -m pytest -q
```

</td><td>

```powershell
cd backend
ruff check app tests --fix
pip-audit -r requirements.txt
$env:APP_ENV="test"; python -m pytest -q
```

</td></tr>
</table>

```bash
cd ../frontend
npm run lint
npm run typecheck
npm run build
```

(The frontend block is identical on every platform — no `$env:`/`export`
difference to call out there.)

All of the above run in CI (`docs/CI_CD.md`) — running them locally first
avoids a red CI run for something you could have caught in seconds. The CI
runner itself is Linux (`ubuntu-latest`), which is exactly why the case-
sensitivity and line-ending safeguards below matter: something that only
"works" because a contributor's Windows or macOS filesystem is
case-insensitive, or because their git silently rewrote CRLF back to LF, can
still break CI even though it looked fine locally.

## Cross-platform correctness — why this matters here specifically

A few real bugs in this exact codebase's history came from platform
assumptions, not from anything exotic — worth knowing so the same class of
bug doesn't come back:

- **File path casing.** Linux filesystems are case-sensitive; Windows and
  (by default) macOS are not. An import like `from "@/components/navbar"`
  when the real file is `NavBar.tsx` will silently work on a Windows or Mac
  laptop and then fail the moment it's built on Linux CI or in the Docker
  image. `frontend/tsconfig.json` sets
  `"forceConsistentCasingInFileNames": true` specifically so TypeScript
  catches this immediately, on any OS, instead of it surfacing as a
  confusing CI-only failure. Don't remove that flag.
- **Line endings.** `.gitattributes` at the repo root forces LF for text
  files regardless of a contributor's local git `autocrlf` setting. Without
  it, a Windows checkout can end up with CRLF line endings that, if ever
  committed, would corrupt a shebang line in a shell script enough to make
  Linux fail with "bad interpreter" — the interpreter path literally
  includes an invisible `\r`. There are no shell scripts in this repo today,
  but this is cheap insurance for the day one is added.
- **Hardcoded Unix paths.** `STORAGE_LOCAL_PATH` defaults to `/data/uploads`
  — that's correct for the Docker image (where it's always Linux inside the
  container, host OS doesn't matter) but would be an unusual, likely-broken
  path if someone ever ran the backend as a bare process directly on native
  Windows without Docker or WSL. If you add a feature that touches this
  path outside of a container, use `pathlib.Path` and resolve it relative to
  something OS-appropriate rather than assuming a POSIX absolute path is
  always valid.
- **Shell activation syntax isn't a platform detail to skip past.** The
  venv activation commands above look trivial but are the single most common
  point where a Windows contributor gets stuck early and silently gives up —
  `source .venv/bin/activate` simply doesn't exist as a concept in
  PowerShell/cmd. If you add a new setup step, add both forms, the way this
  document does.

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
