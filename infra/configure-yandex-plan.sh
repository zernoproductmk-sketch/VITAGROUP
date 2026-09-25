#!/bin/sh
set -eu

ENV_FILE="${1:-.env}"

if [ ! -f "$ENV_FILE" ]; then
  echo "[yandex] env file not found: $ENV_FILE" >&2
  exit 1
fi

echo "[yandex] checking Yandex Disk API hostname resolution"
if ! getent hosts cloud-api.yandex.net >/dev/null 2>&1; then
  echo "[yandex] ERROR: cloud-api.yandex.net does not resolve on this server" >&2
  exit 2
fi

printf "Вставьте публичную ссылку Яндекс Диска на файл или папку: "
IFS= read -r YANDEX_URL

if [ -z "$YANDEX_URL" ]; then
  echo "[yandex] public URL is empty" >&2
  exit 1
fi

printf "Путь к файлу внутри папки (если ссылка ведет сразу на файл — просто Enter): "
IFS= read -r YANDEX_PATH

tmp="${ENV_FILE}.tmp.$$"
awk -v url="$YANDEX_URL" -v path="$YANDEX_PATH" '
  BEGIN { url_done = 0; path_done = 0 }
  /^YANDEX_PLAN_PUBLIC_URL=/ {
    print "YANDEX_PLAN_PUBLIC_URL=" url
    url_done = 1
    next
  }
  /^YANDEX_PLAN_RESOURCE_PATH=/ {
    print "YANDEX_PLAN_RESOURCE_PATH=" path
    path_done = 1
    next
  }
  { print }
  END {
    if (!url_done) print "YANDEX_PLAN_PUBLIC_URL=" url
    if (!path_done) print "YANDEX_PLAN_RESOURCE_PATH=" path
  }
' "$ENV_FILE" > "$tmp"

chmod 600 "$tmp"
mv "$tmp" "$ENV_FILE"

unset YANDEX_URL YANDEX_PATH

echo "[yandex] source saved to $ENV_FILE"
echo "[yandex] recreating backend with updated environment"
docker compose up -d --force-recreate backend

echo "[yandex] waiting for backend health"
i=0
status=""
while [ "$i" -lt 30 ]; do
  container_id="$(docker compose ps -q backend)"
  status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id" 2>/dev/null || true)"
  if [ "$status" = "healthy" ]; then
    break
  fi
  i=$((i + 1))
  sleep 2
done

if [ "$status" != "healthy" ]; then
  echo "[yandex] backend is not healthy after restart" >&2
  docker compose logs --tail=100 backend >&2 || true
  exit 1
fi

echo "[yandex] running read-only preview"
docker compose exec -T backend python - <<'PY'
import asyncio
from app.erp_plan_import import yandex_plan_preview

async def main():
    result = await yandex_plan_preview()
    print("[yandex] configured =", result.get("configured"))
    print("[yandex] resource_type =", result.get("resource_type"))
    print("[yandex] name =", result.get("name"))
    if result.get("resource_type") == "file":
        sheets = result.get("sheets") or []
        print("[yandex] sheets =", len(sheets))
        for item in sheets[:5]:
            print(
                "[yandex] sheet:",
                item.get("name"),
                "recognized=",
                ",".join(item.get("recognized_fields") or []),
                "core=",
                ",".join(item.get("core_fields_found") or []),
            )
    else:
        print("[yandex] message =", result.get("message"))
        for item in (result.get("items") or [])[:20]:
            print("[yandex] item:", item.get("name"), item.get("type"), item.get("path"))

asyncio.run(main())
PY
