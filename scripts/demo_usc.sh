#!/usr/bin/env bash
# TrojanPlate USC judge demo
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
BASE="${BASE_URL:-http://127.0.0.1:8000}"

echo "== TrojanPlate · USC demo =="
echo "UI:  $BASE/"
echo "API: $BASE"
echo

if ! curl -sf "$BASE/health" >/dev/null; then
  echo "API not up. Start with:"
  echo "  source .venv/bin/activate"
  echo "  uvicorn trojanbites_extract.api.app:app --reload --port 8000"
  exit 1
fi

echo "-- Health --"
curl -s "$BASE/health" | python3 -m json.tool
echo
echo "-- Overview --"
curl -s "$BASE/v1/usc/overview" | python3 -m json.tool
echo
echo "-- USC Dining day plan (vegetarian / high protein) --"
curl -s -X POST "$BASE/v1/plan/day" \
  -H 'Content-Type: application/json' \
  -d @"$ROOT/data/menus/examples/plan_day_usc.json" | python3 -m json.tool
echo
echo "-- Off-Campus day plan --"
curl -s -X POST "$BASE/v1/plan/day" \
  -H 'Content-Type: application/json' \
  -d @"$ROOT/data/menus/examples/plan_day_off_campus.json" | python3 -m json.tool
echo
echo "Open $BASE/ for the mobile UI"
