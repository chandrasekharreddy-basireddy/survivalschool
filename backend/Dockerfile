# Multi-stage build: compile deps in a full image, ship a slim runtime.
FROM python:3.14-slim AS builder

WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.14-slim AS runtime

# libpq5: Postgres client. curl: healthcheck. The rest (pango/cairo/gdk-pixbuf/
# fonts): required at runtime by weasyprint for GET /certificates/{number}/pdf
# (HTML->PDF certificate generation) — weasyprint imports these as shared
# libraries via cffi at call time, so they must be present in the final image,
# not just at pip-install time in the builder stage.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl \
    libpango-1.0-0 libpangocairo-1.0-0 libpangoft2-1.0-0 libcairo2 \
    libgdk-pixbuf-2.0-0 libffi8 fonts-dejavu-core shared-mime-info \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser

COPY --from=builder /install /usr/local
WORKDIR /app
COPY --chown=appuser:appuser . .

RUN mkdir -p /data/uploads && chown -R appuser:appuser /data
USER appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

# /api/v1/live, not /health — every health route is mounted under the API
# prefix (app/api/v1/health.py via api_router), so a bare /health 404s and
# would mark this container permanently unhealthy. Matches the path used by
# docker-compose and the k8s liveness probe.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/live || exit 1

CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "60", "--access-logfile", "-"]
