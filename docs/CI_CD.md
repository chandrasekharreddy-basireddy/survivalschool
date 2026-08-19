# CI/CD pipeline

`.github/workflows/ci.yml` — four jobs, running on every push to `main`,
`feat/**` and `fix/**`, and on every pull request against `main`.

## Job 1: `backend-lint-and-test`

Runs against real `postgres:16-alpine` and `redis:7-alpine` service
containers (not sqlite, not mocks — the same integration-test philosophy
described in `docs/TESTING.md`).

1. Install dependencies from `requirements.txt` plus `ruff` and `pip-audit`.
2. `ruff check app tests` (with the ignore list pinned in the workflow) —
   must be zero errors.
3. `pip-audit -r requirements.txt` — fails on any known vulnerability.
4. `mypy app` — **non-blocking** (`continue-on-error: true`). The codebase is
   fully type-hinted but has never been gated on a clean mypy run; this
   surfaces type errors in the log without failing the build. Drop the
   `continue-on-error` once the existing findings are burned down.
5. `alembic upgrade head` against the service-container Postgres.
6. `alembic check` for model/migration drift — also **non-blocking**, since
   autogenerate doesn't perfectly detect CHECK constraints and can report
   benign diffs.
7. `pytest --tb=short -q` — the full suite (136 test functions, see
   `docs/TESTING.md`), run with `AI_PROVIDER=mock` and
   `EMAIL_BACKEND=console` so CI never needs real Sarvam/SMTP credentials.

## Job 2: `frontend-lint-build`

`npm install` → `npm run lint` (ESLint) → `npm run typecheck`
(`tsc --noEmit`) → `npm audit --omit=dev --audit-level=high` → `npm run build`
(production Next.js build, with placeholder `NEXT_PUBLIC_API_BASE_URL`/
`NEXT_PUBLIC_WS_BASE_URL` values since no real backend is reachable from a CI
runner).

## Job 3: `secret-scan`

`gitleaks/gitleaks-action@v2` over the full history (`fetch-depth: 0`), so a
credential committed at any point is caught, not just one in the latest diff.
Runs independently of the other jobs.

## Job 4: `docker-build` (depends on jobs 1 and 2)

1. `docker build` for the backend and frontend images (build-only — no
   registry push is configured).
2. **Advisory scan step** (`continue-on-error: true`): installs Trivy and
   Syft from their official install scripts, scans both images for fixable
   CRITICAL/HIGH CVEs (`--ignore-unfixed`), and emits SPDX SBOMs with Syft.
   Report-only by design — the image *build* is the gate here, so a scanner
   or network hiccup, or an unpatched upstream base-image CVE, can't block
   the pipeline. Findings are printed to the job log.

   Trivy/Syft are installed via script rather than via their GitHub Actions
   deliberately: a mis-pinned action tag previously failed this job at
   "Set up job", before any step ran.

There is **no** smoke-test job — the stack is not booted with
`docker compose` in CI. The worker image (`backend/Dockerfile.worker`) does
exist and is built by `docker-compose.yml`, but CI does **not** build it —
only the backend and frontend images are built here.

## Continuous dependency scanning (`.github/workflows/dependency-scan.yml`)

Job 1's `pip-audit` and job 2's `npm audit` only run when code changes
trigger a push/PR. That leaves a real gap: a dependency that was clean last
week can have a CVE disclosed against it today even if nobody touched the
repo. `dependency-scan.yml` closes it with a separate scheduled workflow:

- Runs daily at 06:15 UTC (`workflow_dispatch` also exposes a manual "run
  now" button in the Actions tab) — independent of any push or PR.
- `backend-dependency-scan`: `pip-audit -r requirements.txt --desc` —
  blocking (job fails on any known vulnerability).
- `frontend-dependency-scan`: `npm audit --omit=dev --audit-level=high` —
  blocking on high/critical findings.
- `notify-on-failure`: if either scan job fails, opens (or comments on an
  existing) GitHub issue labeled `dependency-vulnerability` linking straight
  to the failed run, using the built-in `GITHUB_TOKEN` — no external
  service, Slack webhook, or additional secret required.

### Automated update PRs (`.github/dependabot.yml`)

Complements the scan above — finding a vulnerability is only useful if
something also proposes the fix. Dependabot is configured for weekly
(Monday) update PRs across four ecosystems: `pip` (`/backend`), `npm`
(`/frontend`), `docker` (both `/backend` and `/frontend` Dockerfiles), and
`github-actions` (the action versions pinned in these workflow files
themselves — a real, often-overlooked supply-chain surface). Minor/patch
bumps within each ecosystem are grouped into one combined PR rather than a
dozen separate ones; major version bumps still get their own PR since those
more often need a manual look at breaking changes.

## Status

This pipeline runs green on GitHub Actions — all four jobs passing on the
`feat/survival-school-v2` branch.

Earlier revisions of this document described a `smoke-test` job, a separate
worker image build, Trivy wired up as a GitHub Action, and a "30 tests"
suite. None of those matched `ci.yml`; the descriptions above were rewritten
directly from the workflow file.
