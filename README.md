# Survival School

An MCQ-driven learning and gamification platform for universities — courses,
timed quizzes and exams with server-authoritative scoring, points/badges/
certificates, real-time chat, an AI tutor, and an admin console.

## Stack

- **Backend**: FastAPI (Python 3.11, async), SQLAlchemy 2.0, PostgreSQL 16, Redis 7, Alembic
- **Frontend**: Next.js 14 (App Router), TypeScript, Tailwind CSS
- **Automation**: n8n (event-driven notifications)
- **AI**: Sarvam AI (pluggable provider abstraction, mock provider for dev/CI)
- **Infra**: Docker Compose (local), GitHub Actions (CI/CD), Kubernetes manifests (readiness)

## Quick start

```bash
cp backend/.env.example backend/.env   # fill in real secrets
docker compose up -d --build
# backend: http://localhost:8000/api/docs   frontend: http://localhost:3000
```

See `docs/CONTRIBUTING.md` for running the backend/frontend directly on your
host (what this build was actually developed and tested against).

## Documentation

| Doc | Covers |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System design, key decisions, request lifecycle |
| [`docs/SECURITY.md`](docs/SECURITY.md) | Auth, RBAC, anti-cheat, rate limiting, dependency audits, known gaps |
| [`docs/DATABASE.md`](docs/DATABASE.md) | Schema, migrations, conventions |
| [`docs/API.md`](docs/API.md) | Full endpoint reference |
| [`docs/REALTIME.md`](docs/REALTIME.md) | WebSocket chat design and known multi-replica limitation |
| [`docs/AI.md`](docs/AI.md) | Sarvam AI integration — honest CONFIGURED-vs-TESTED status |
| [`docs/N8N.md`](docs/N8N.md) | n8n automation — real published workflow, honest network-hop status |
| [`docs/POWERBI.md`](docs/POWERBI.md) | How to connect Power BI to this platform's data |
| [`docs/OBSERVABILITY.md`](docs/OBSERVABILITY.md) | Logging, health checks, audit trail, what's not set up |
| [`docs/TESTING.md`](docs/TESTING.md) | The full test suite, what's tested and what isn't |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | Docker Compose, CI, Kubernetes — what's verified at each layer |
| [`docs/CI_CD.md`](docs/CI_CD.md) | GitHub Actions pipeline, job by job |
| [`docs/ENVIRONMENT.md`](docs/ENVIRONMENT.md) | Every environment variable |
| [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) | Local setup, conventions, pre-PR checklist |
| [`infra/k8s/README.md`](infra/k8s/README.md) | Kubernetes manifest set, gaps, apply order |

## Status

This is a working core MVP, not a mockup or demo shell — every claim of
"tested" in the docs above is backed by a real passing test against real
PostgreSQL/Redis, not a mock. See [`docs/STATUS.md`](docs/STATUS.md) for the
full, itemized production-readiness report: what's implemented and tested,
what's implemented and configured-but-unverified (and exactly why, given
this development sandbox's network restrictions), and what's an explicitly
documented gap rather than a hidden one.
