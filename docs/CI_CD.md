# CI/CD pipeline

`.github/workflows/ci.yml` — four jobs, running on every push and pull
request against `main`.

## Job 1: `backend-lint-and-test`

Runs against real `postgres:16-alpine` and `redis:7-alpine` service
containers (not sqlite, not mocks — the same integration-test philosophy
described in `docs/TESTING.md`).

1. Install dependencies from `requirements.txt` plus `ruff` and `pip-audit`.
2. `ruff check app tests` — must be zero errors (verified locally in this
   build: it is).
3. `pip-audit -r requirements.txt` — must report no known vulnerabilities
   (verified locally in this build: it does, after upgrading `fastapi`,
   `starlette`, `pyjwt`, `python-multipart`, `jinja2`, `python-dotenv`,
   `pytest`, `uvicorn`, `gunicorn`, and `setuptools` to patched versions
   during this build specifically to close what `pip-audit` originally
   flagged).
4. `alembic upgrade head` against the service-container Postgres.
5. `pytest --cov=app --cov-report=term-missing --cov-report=xml` — the same
   24 tests described in `docs/TESTING.md`, run with `AI_PROVIDER=mock` and
   `EMAIL_BACKEND=console` so CI never needs real Sarvam/SMTP credentials.
6. Upload `coverage.xml` as a build artifact.

## Job 2: `frontend-lint-build`

`npm ci` → `npm run lint` (ESLint) → `npm run typecheck` (`tsc --noEmit`) →
`npm audit --production` (non-blocking, reports only) → `npm run build`
(production Next.js build, with placeholder `NEXT_PUBLIC_API_BASE_URL`/
`NEXT_PUBLIC_WS_BASE_URL` values since no real backend is reachable from a CI
runner).

## Job 3: `docker-build` (depends on jobs 1 and 2)

Builds the backend, worker, and frontend images with
`docker/build-push-action@v6` (`push: false` — build-only, no registry push
configured, since none is set up yet), then runs `aquasecurity/trivy-action`
against the backend image for CRITICAL/HIGH vulnerabilities (`exit-code: "0"`
— reports findings without failing the pipeline, until they've been triaged
at least once; flip to `"1"` to hard-fail once a baseline is established).

## Job 4: `smoke-test` (depends on job 3)

Boots the full stack with `docker compose up -d --build`, polls
`http://localhost:8000/api/v1/health` and `http://localhost:3000` for up to
150 seconds each, dumps `docker compose logs` on failure, and always tears
the stack down (`docker compose down -v`) whether the smoke test passed or
failed.

## Honest status: written and cross-checked, not yet run

Every claim above about what the pipeline *does* is true by reading the
workflow file. What this document cannot yet claim is that the pipeline
*has run successfully* — that requires pushing to GitHub, which depends on
this session's GitHub push access (see `docs/DEPLOYMENT.md` and the final
delivery notes for this build). What was done in this sandbox instead, to
close that gap as much as possible without GitHub Actions itself:

- The workflow YAML was parsed and validated as syntactically correct.
- Every file path, script name (`npm run lint`, `npm run typecheck`), and
  endpoint path (`/api/v1/health`) the workflow references was independently
  cross-checked against the actual repository and confirmed to exist/match.
- Steps 2–5 of job 1 (lint, audit, migrate, test) were run directly in this
  sandbox against real local Postgres/Redis — the same commands the CI job
  runs, just not inside the GitHub Actions runner itself — and all passed.
- The frontend build (job 2's final step) was run directly in this sandbox
  and succeeded.
- Jobs 3 and 4 (Docker builds, Trivy scan, compose smoke test) could not be
  run in this sandbox because of the container-registry network block
  described in `docs/DEPLOYMENT.md` — these will get their first real
  execution on GitHub Actions.

The first actual green (or red) checkmark on a real PR is the true
confirmation this pipeline works end-to-end; until then, "validated" means
"internally consistent and independently cross-checked," not "has run."
