#!/usr/bin/env bash
# Small live pilot: off-campus restaurants inside USC DPS patrol.
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate
LIMIT="${1:-3}"
echo "Running off-campus DPS pilot (limit=${LIMIT})..."
trojanbites init-db
trojanbites ingest-off-campus-dps --campus usc_upc --limit "${LIMIT}" --force
echo "Done. Export with: trojanbites export"
