# Kubernetes manifests — readiness status

**Status: readiness-only, not applied against a live cluster.** This sandbox has
no Kubernetes cluster available (no `kubectl`, no cloud credentials), so nothing
here has been run through `kubectl apply` or `kubectl dry-run` against a real
API server. Every manifest below has been validated for YAML syntax and
cross-checked against the actual application (paths, ports, image build
context, env var names) but has **not** been proven to deploy successfully.
Treat this as a strong starting point that needs a real cluster smoke test
before production use, not as verified infrastructure.

## What's here

| File | Purpose |
|---|---|
| `00-namespace.yaml` | `survivalschool` namespace |
| `01-configmap.yaml` | Non-secret runtime config, mirrors `backend/.env.example` |
| `02-secret.yaml.example` | **Template only** — fill in and apply out-of-band, never commit filled values |
| `03-postgres.yaml` | Postgres StatefulSet + headless Service (use a managed DB in real prod) |
| `04-redis.yaml` | Redis Deployment + Service (use a managed cache in real prod) |
| `05-migrate-job.yaml` | One-shot `alembic upgrade head` Job, run before rolling backend/worker |
| `06-backend.yaml` | Backend API Deployment, Service, uploads PVC, HPA, PDB |
| `07-worker.yaml` | Background worker Deployment (single replica — see file comment on why) |
| `08-frontend.yaml` | Next.js frontend Deployment, Service, HPA |
| `09-ingress.yaml` | TLS ingress for API + app hosts (assumes ingress-nginx + cert-manager) |
| `10-networkpolicy.yaml` | Default-deny plus explicit allow rules between tiers |
| `11-backup-cronjob.yaml` | Nightly `pg_dump` CronJob + dedicated backup PVC — see `docs/DATABASE.md#backups` |

## Known gaps / what you must decide before this is real production infra

1. **Container images don't exist yet.** Every `image:` field points to
   `ghcr.io/REPLACE_ME_ORG/survivalschool-{backend,worker,frontend}:latest`,
   which is a placeholder. This sandbox could not build or push these images —
   every outbound container-registry request (docker.io, ghcr.io, gcr.io,
   mcr.microsoft.com, public.ecr.aws) was blocked by the sandbox's network
   egress allowlist. The `Dockerfile`s themselves (`backend/Dockerfile`,
   `backend/Dockerfile.worker`, `frontend/Dockerfile`) are real and were
   validated structurally (`docker compose config`), but no image has actually
   been built or scanned in this session. The CI pipeline (`.github/workflows/ci.yml`)
   will build and Trivy-scan them once pushed to GitHub Actions, which has
   unrestricted registry access.
2. **In-cluster Postgres/Redis are for staging/demo, not production.** For a
   real production deployment, point `DATABASE_URL`/`REDIS_URL` at a managed
   service (RDS, Cloud SQL, ElastiCache, etc.) and delete `03-postgres.yaml` /
   `04-redis.yaml`.
3. **Secrets management is a template, not a solution.** `02-secret.yaml.example`
   shows the required keys; wire up a real secret manager (Sealed Secrets,
   External Secrets Operator, SOPS) before applying anything derived from it.
4. **Ingress assumes ingress-nginx + cert-manager are pre-installed** on the
   cluster with a `letsencrypt-prod` ClusterIssuer already configured. Swap
   the `ingressClassName` / annotations if your cluster uses a different
   controller (ALB Ingress Controller, GKE Ingress, Traefik).
5. **The `local` storage backend + single ReadWriteOnce PVC for uploads** only
   works correctly with a single backend replica actually touching those files
   consistently across pod restarts on the same node-affinity-free scheduling;
   for `backend` running multiple replicas with `STORAGE_BACKEND=local`,
   switch to a ReadWriteMany volume (EFS/Filestore) or, better, switch
   `STORAGE_BACKEND` to an object-store backend if/when one is implemented.
6. **No cluster-level resource quotas, priority classes, or multi-AZ topology
   spread constraints** are defined — add these per your cluster's actual
   capacity planning before running this in a shared cluster.

## Suggested apply order (once images exist and secrets are real)

```bash
kubectl apply -f infra/k8s/00-namespace.yaml
kubectl apply -f infra/k8s/01-configmap.yaml
kubectl apply -f <your-real-rendered-secret>.yaml   # NOT 02-secret.yaml.example verbatim
kubectl apply -f infra/k8s/03-postgres.yaml
kubectl apply -f infra/k8s/04-redis.yaml
kubectl wait --for=condition=ready pod -l app=postgres -n survivalschool --timeout=120s
kubectl apply -f infra/k8s/05-migrate-job.yaml
kubectl wait --for=condition=complete job/survivalschool-migrate -n survivalschool --timeout=120s
kubectl apply -f infra/k8s/06-backend.yaml
kubectl apply -f infra/k8s/07-worker.yaml
kubectl apply -f infra/k8s/08-frontend.yaml
kubectl apply -f infra/k8s/09-ingress.yaml
kubectl apply -f infra/k8s/10-networkpolicy.yaml
```
