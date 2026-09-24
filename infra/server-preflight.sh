#!/bin/sh
set -eu

ENV_FILE="${1:-.env}"
DOMAIN="${VITAGROUP_DOMAIN:-corpvitagroup.ru}"

fail() {
  echo "[preflight] ERROR: $*" >&2
  exit 1
}

warn() {
  echo "[preflight] WARNING: $*" >&2
}

ok() {
  echo "[preflight] OK: $*"
}

need_command() {
  command -v "$1" >/dev/null 2>&1 || fail "missing command: $1"
}

env_value() {
  key="$1"
  grep -E "^${key}=" "$ENV_FILE" | tail -n 1 | cut -d= -f2-
}

echo "[preflight] VITAGROUP production server"

[ -f "$ENV_FILE" ] || fail "$ENV_FILE not found"

need_command docker
need_command git
need_command curl
need_command openssl

docker info >/dev/null 2>&1 || fail "Docker daemon is not available"
docker compose version >/dev/null 2>&1 || fail "Docker Compose plugin is not available"
ok "Docker and Compose are available"

if git ls-files --error-unmatch .env >/dev/null 2>&1; then
  fail ".env is tracked by Git"
fi
ok ".env is not tracked by Git"

mode="$(stat -c '%a' "$ENV_FILE" 2>/dev/null || true)"
case "$mode" in
  600|400) ok "$ENV_FILE permissions are restrictive ($mode)" ;;
  "") warn "could not determine $ENV_FILE permissions" ;;
  *) warn "$ENV_FILE permissions are $mode; recommended: chmod 600 $ENV_FILE" ;;
esac

environment="$(env_value ENVIRONMENT)"
[ "$environment" = "production" ] || fail "ENVIRONMENT must be production"

cors="$(env_value CORS_ORIGINS)"
echo "$cors" | grep -F "https://$DOMAIN" >/dev/null 2>&1 ||   fail "CORS_ORIGINS must include https://$DOMAIN"

pg_password="$(env_value POSTGRES_PASSWORD)"
[ -n "$pg_password" ] || fail "POSTGRES_PASSWORD is empty"
[ "$pg_password" != "change-this-before-deploy" ] ||   fail "POSTGRES_PASSWORD still uses the example value"
[ "${#pg_password}" -ge 20 ] || warn "POSTGRES_PASSWORD should be at least 20 characters"

jwt_secret="$(env_value AUTH_JWT_SECRET)"
[ -n "$jwt_secret" ] || fail "AUTH_JWT_SECRET is empty"
[ "$jwt_secret" != "replace-with-at-least-64-random-characters" ] ||   fail "AUTH_JWT_SECRET still uses the example value"
[ "${#jwt_secret}" -ge 48 ] || fail "AUTH_JWT_SECRET must contain at least 48 characters"

ok "production secrets are not example values"

coverse_token="$(env_value COVERSE_API_TOKEN)"
[ -n "$coverse_token" ] || warn "COVERSE_API_TOKEN is empty; Coverse sync will remain disabled"

yandex_url="$(env_value YANDEX_PLAN_PUBLIC_URL)"
[ -n "$yandex_url" ] || warn "YANDEX_PLAN_PUBLIC_URL is empty; ERP plan import from Yandex Disk will remain disabled"

docker compose --env-file "$ENV_FILE" config >/dev/null
ok "Docker Compose configuration is valid"

if docker compose --env-file "$ENV_FILE" config | grep -E '(^|[[:space:]])5432:5432([[:space:]]|$)' >/dev/null 2>&1; then
  fail "PostgreSQL port 5432 is published publicly in Compose"
fi
ok "PostgreSQL is not published by Compose"

memory_kb="$(awk '/MemTotal:/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)"
if [ "$memory_kb" -ge 7340032 ]; then
  ok "RAM is approximately 7 GiB or more"
else
  warn "RAM is below the recommended 8 GB class"
fi

available_kb="$(df -Pk . | awk 'NR==2 {print $4}')"
if [ "$available_kb" -ge 31457280 ]; then
  ok "at least 30 GB disk space is currently available"
else
  warn "less than 30 GB disk space is currently available"
fi

if command -v getent >/dev/null 2>&1; then
  addresses="$(getent ahostsv4 "$DOMAIN" 2>/dev/null | awk '{print $1}' | sort -u | tr '\n' ' ' || true)"
  if [ -n "$addresses" ]; then
    echo "[preflight] DNS: $DOMAIN -> $addresses"
  else
    warn "$DOMAIN does not currently resolve to an IPv4 address"
  fi
else
  warn "getent is unavailable; DNS check skipped"
fi

if command -v ss >/dev/null 2>&1; then
  for port in 80 443; do
    if ss -lnt | awk '{print $4}' | grep -E "[:.]$port$" >/dev/null 2>&1; then
      warn "TCP port $port is already in use; verify this is expected before starting Caddy"
    else
      ok "TCP port $port is free"
    fi
  done
fi

echo "[preflight] completed"
