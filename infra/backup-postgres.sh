#!/bin/sh
set -eu

RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"

run_backup() {
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  target="/backups/vitagroup_${timestamp}.dump"
  temp="${target}.tmp"

  echo "[backup] starting ${timestamp}"
  pg_dump \
    --format=custom \
    --compress=9 \
    --no-owner \
    --no-acl \
    --file="${temp}"

  echo "[backup] verifying dump"
  if ! pg_restore --list "${temp}" >/dev/null 2>&1; then
    rm -f "${temp}"
    echo "[backup] verification failed; invalid dump removed" >&2
    return 1
  fi

  mv "${temp}" "${target}"
  echo "[backup] created and verified ${target}"

  find /backups     -type f     -name 'vitagroup_*.dump'     -mtime "+${RETENTION_DAYS}"     -delete

  echo "[backup] retention complete (${RETENTION_DAYS} days)"
}

while true; do
  run_backup
  sleep 86400
done
