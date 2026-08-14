#!/usr/bin/env bash
# Nightly logical backup of the Survival School Postgres database.
#
# Honest status: this script has been syntax-checked and its individual
# commands (pg_dump, gzip, find) are standard and well-understood, but it has
# NOT been run end-to-end against a real production database in this sandbox
# (no long-lived Postgres instance with real data existed to back up). Treat
# it as a solid, reviewed starting point — test it against a staging database
# before relying on it in production, per docs/DATABASE.md.
#
# Usage:
#   BACKUP_DIR=/backups DATABASE_URL_SYNC=postgresql://... ./backup_postgres.sh
#
# Intended to run either as a k8s CronJob (see infra/k8s/11-backup-cronjob.yaml)
# or as a plain cron entry on a host that has network access to Postgres and
# a `pg_dump` binary matching (or newer than) the server's major version.
set -euo pipefail

: "${DATABASE_URL_SYNC:?DATABASE_URL_SYNC must be set (e.g. postgresql://user:pass@host:5432/dbname)}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_FILE="${BACKUP_DIR}/survivalschool-${TIMESTAMP}.sql.gz"

mkdir -p "${BACKUP_DIR}"

echo "[backup] starting pg_dump -> ${OUT_FILE}"
# --format=plain piped through gzip (rather than pg_dump -Fc) so the output is
# restorable with nothing more exotic than `gunzip | psql` — no dependency on
# having the exact same pg_dump/pg_restore version available at restore time.
pg_dump --dbname="${DATABASE_URL_SYNC}" --no-owner --no-privileges --format=plain | gzip -9 > "${OUT_FILE}"

SIZE_BYTES=$(stat -c%s "${OUT_FILE}" 2>/dev/null || stat -f%z "${OUT_FILE}")
if [ "${SIZE_BYTES}" -lt 100 ]; then
  echo "[backup] ERROR: output file suspiciously small (${SIZE_BYTES} bytes) — likely a failed/empty dump. Not treating this as a successful backup." >&2
  rm -f "${OUT_FILE}"
  exit 1
fi
echo "[backup] wrote ${OUT_FILE} (${SIZE_BYTES} bytes)"

# Verification step (spec: "backup verification process") — gunzip -t proves
# the archive isn't truncated/corrupted without doing a full restore. It does
# NOT prove the SQL is restorable; see docs/DATABASE.md for the recommended
# periodic full-restore drill this cannot replace.
gzip -t "${OUT_FILE}"
echo "[backup] integrity check passed"

echo "[backup] pruning backups older than ${RETENTION_DAYS} days"
find "${BACKUP_DIR}" -name 'survivalschool-*.sql.gz' -mtime "+${RETENTION_DAYS}" -print -delete

echo "[backup] done"
