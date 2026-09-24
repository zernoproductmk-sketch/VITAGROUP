#!/bin/sh
set -eu

ENV_FILE="${1:-.env}"
BASE_URL="${VITAGROUP_BASE_URL:-https://corpvitagroup.ru}"

echo "[deploy] starting VITAGROUP production deployment"

sh infra/server-preflight.sh "$ENV_FILE"

if [ -n "$(docker compose --env-file "$ENV_FILE" ps -q db 2>/dev/null || true)" ] &&    [ "$(docker inspect -f '{{.State.Running}}' "$(docker compose --env-file "$ENV_FILE" ps -q db)" 2>/dev/null || true)" = "true" ]; then
  echo "[deploy] creating verified pre-deploy PostgreSQL backup"
  docker compose --env-file "$ENV_FILE" run --rm --no-deps     -e BACKUP_ONCE=true backup
else
  echo "[deploy] database is not running yet; pre-deploy backup skipped for first deployment"
fi

echo "[deploy] building application images"
docker compose --env-file "$ENV_FILE" build

echo "[deploy] starting database and applying migrations"
docker compose --env-file "$ENV_FILE" up -d db migrate

echo "[deploy] verifying migration container"
migration_id="$(docker compose --env-file "$ENV_FILE" ps -q migrate)"
[ -n "$migration_id" ] || {
  echo "[deploy] migrate container was not created" >&2
  exit 1
}

migration_exit="$(docker inspect -f '{{.State.ExitCode}}' "$migration_id")"
if [ "$migration_exit" != "0" ]; then
  echo "[deploy] migration failed with exit code $migration_exit" >&2
  docker compose --env-file "$ENV_FILE" logs --tail=200 migrate >&2 || true
  exit 1
fi

echo "[deploy] starting application services"
docker compose --env-file "$ENV_FILE" up -d backend frontend backup caddy

echo "[deploy] container state"
docker compose --env-file "$ENV_FILE" ps

echo "[deploy] running public post-deploy checks"
if ! sh infra/post-deploy-check.sh "$BASE_URL"; then
  echo "[deploy] post-deploy check failed; recent service logs follow" >&2
  docker compose --env-file "$ENV_FILE" logs --tail=200 backend frontend caddy >&2 || true
  exit 1
fi

echo "[deploy] SUCCESS"
