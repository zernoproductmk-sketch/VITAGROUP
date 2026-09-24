#!/bin/sh
set -eu

ENV_FILE="${1:-.env}"

if [ ! -f "$ENV_FILE" ]; then
  echo "[coverse] env file not found: $ENV_FILE" >&2
  exit 1
fi

printf "Введите Coverse API-токен (ввод скрыт): "
stty -echo
IFS= read -r COVERSE_TOKEN
stty echo
printf "\n"

cleanup() {
  unset COVERSE_TOKEN
}
trap cleanup EXIT INT TERM

if [ -z "$COVERSE_TOKEN" ]; then
  echo "[coverse] token is empty" >&2
  exit 1
fi

tmp="${ENV_FILE}.tmp.$$"
awk -v token="$COVERSE_TOKEN" '
  BEGIN { replaced = 0 }
  /^COVERSE_API_TOKEN=/ {
    print "COVERSE_API_TOKEN=" token
    replaced = 1
    next
  }
  { print }
  END {
    if (!replaced) print "COVERSE_API_TOKEN=" token
  }
' "$ENV_FILE" > "$tmp"

chmod 600 "$tmp"
mv "$tmp" "$ENV_FILE"

echo "[coverse] token saved to $ENV_FILE"
echo "[coverse] recreating backend with updated environment"
docker compose up -d --force-recreate backend

echo "[coverse] waiting for backend health"
i=0
while [ "$i" -lt 30 ]; do
  status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$(docker compose ps -q backend)" 2>/dev/null || true)"
  if [ "$status" = "healthy" ]; then
    break
  fi
  i=$((i + 1))
  sleep 2
done

if [ "$status" != "healthy" ]; then
  echo "[coverse] backend is not healthy after restart" >&2
  docker compose logs --tail=100 backend >&2 || true
  exit 1
fi

echo "[coverse] running API smoke check"
docker compose exec -T backend python - <<'PY'
import asyncio
from app.integrations.coverse import CoverseClient

DOCUMENT_ID = "cb08fd21-0624-4fc6-9050-b4146f2f6fbb"

async def main():
    client = CoverseClient()
    try:
        cells = await client.read_range(
            DOCUMENT_ID,
            "СПРАВОЧНИК_ЛИНИЙ",
            "A1:B3",
        )
    finally:
        await client.close()

    if len(cells) < 2:
        raise SystemExit("Coverse smoke check returned too few rows")

    print(f"[coverse] SUCCESS: rows returned = {len(cells)}")

asyncio.run(main())
PY
