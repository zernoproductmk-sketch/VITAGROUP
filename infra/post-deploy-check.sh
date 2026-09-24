#!/bin/sh
set -eu

BASE_URL="${1:-https://corpvitagroup.ru}"

echo "[check] frontend: ${BASE_URL}"
frontend="$(curl -fsS "${BASE_URL}/")"
echo "${frontend}" | grep -qi "<!doctype html" || {
  echo "[check] frontend did not return HTML" >&2
  exit 1
}

echo "[check] health: ${BASE_URL}/health"
health="$(curl -fsS "${BASE_URL}/health")"

echo "${health}" | grep -q '"status":"ok"' || {
  echo "[check] health status is not ok" >&2
  echo "${health}" >&2
  exit 1
}

echo "${health}" | grep -q '"database":"ok"' || {
  echo "[check] database is not ok" >&2
  echo "${health}" >&2
  exit 1
}

echo "${health}" | grep -q '"schema_version":"013_qc_inspections.sql"' || {
  echo "[check] unexpected schema version" >&2
  echo "${health}" >&2
  exit 1
}

echo "[check] auth endpoint requires POST and exists"
status="$(curl -sS -o /dev/null -w '%{http_code}' "${BASE_URL}/api/v1/auth/login")"
case "${status}" in
  405|422) ;;
  *)
    echo "[check] unexpected auth endpoint status: ${status}" >&2
    exit 1
    ;;
esac

echo "[check] all public deployment checks passed"
