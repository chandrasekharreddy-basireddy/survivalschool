# Deployment

Three ways to run this system, in increasing order of production-readiness.
Each section states plainly what has and hasn't actually been exercised.

## 1. Local development (`docker compose`) — structurally validated, not booted in this sandbox

```bash
cp backend/.env.example backend/.env   # then fill in real secrets
docker compose up -d --build
```

This brings up `postgres`, `redis`, `backend`, `migrate` (one-shot,
`alembic upgrade head && python -m app.seed`), `worker`, and `frontend`,
matching `docker-compose.yml` exactly.

**What was actually verified in this session:** `docker compose config`
succeeds (the compose file is structurally valid — correct service
dependencies, healthchecks, env wiring, volumes). The backend and frontend
were run and tested directly on the host (not inside Docker) against real
local Postgres/Redis instances, which is how the 30 passing backend tests
and the successful frontend production build were produced.

**What was NOT verified:** actually building and running the Docker images.
Every outbound request to a container registry (`docker.io`,
`mcr.microsoft.com`, `public.ecr.aws`, `gcr.io`) was blocked with `403
Forbidden` by this sandbox's network egress allowlist — this is a sandbox
restriction, not a problem with the Dockerfiles. The `Dockerfile`s
(`backend/Dockerfile`, `backend/Dockerfile.worker`, `frontend/Dockerfile`)
use standard multi-stage builds, non-root users, and healthchecks, and were
reviewed for correctness, but "reviewed" is a weaker claim than "built and
ran" — say that explicitly rather than implying the stronger claim. The
first real proof these images build correctly will be the `docker-build` job
in CI (`.github/workflows/ci.yml`), which runs on GitHub Actions
infrastructure with unrestricted registry access — see `docs/CI_CD.md`.

## 2. GitHub Actions CI — validated structurally, not yet run for real

`.github/workflows/ci.yml` runs on every push/PR to `main`: backend
lint+test+audit against real Postgres/Redis service containers, frontend
lint+typecheck+build, then Docker image builds + Trivy scan, then a full
`docker compose` smoke test hitting both `/api/v1/health` and `/`. The
workflow file's YAML syntax was validated and every path/script/port it
references was cross-checked against the actual repository (Dockerfiles
exist, `npm run lint`/`typecheck`/`build` scripts exist, the health endpoint
path matches). It has not yet executed on real GitHub Actions infrastructure
— see `docs/CI_CD.md` for exactly what "validated" means here versus what a
real green run would additionally prove.

## 3. Kubernetes — manifests are schema-valid, cluster deployment unverified

`infra/k8s/*.yaml` is a complete, kubeconform-validated manifest set
(namespace, config, secret template, Postgres StatefulSet, Redis Deployment,
migration Job, backend/worker/frontend Deployments with HPAs and a PDB,
Ingress, NetworkPolicies). See `infra/k8s/README.md` for the full honest
status — in short: **schema-valid, never applied to a real cluster**, and
every `image:` field is a placeholder because no image has actually been
built and pushed yet (see #1 above).

## Environment variables required for production

See `docs/ENVIRONMENT.md` for the full list. The single most important
guardrail: `app/config.py::Settings.validate_for_production()` runs at
startup when `APP_ENV=production` and raises immediately (not a warning — a
hard failure that prevents the app from serving traffic) if the database URL
still points at localhost, the email backend is still `console`,
`AI_PROVIDER=sarvam` is set without a `SARVAM_API_KEY`, or the JWT secret is
under 32 characters. This is a deliberate fail-fast design so a
misconfigured production deploy never silently runs with development
defaults.

## Recommended production topology

- Managed Postgres (not the in-cluster StatefulSet) — see
  `infra/k8s/README.md` for why.
- Managed Redis (not the in-cluster Deployment) — same reasoning.
- Backend: 2+ replicas behind the Ingress, HPA on CPU (already defined in
  `infra/k8s/06-backend.yaml`). **Caveat**: WebSocket chat does not yet
  support multi-replica broadcast — see `docs/REALTIME.md` before scaling
  backend replicas in a deployment where chat is actively used.
- Worker: single replica (see `infra/k8s/07-worker.yaml` for why — it's
  periodic sweeps, not a distributed work queue).
- Frontend: 2+ replicas, static/SSR pages behind the same Ingress.
- Object storage (S3 or equivalent) instead of `STORAGE_BACKEND=local` if
  running the backend with more than one replica and expecting file uploads
  to be consistently readable across pods — the codebase has a
  `STORAGE_BACKEND: Literal["local", "s3"]` setting but the S3 backend
  implementation itself is not present in this build; only `local` is
  functional today. Treat `s3` as a documented, planned setting, not a
  working feature.
