# TrojanPlate Backend

**Your goals. Your campus. Your plate.**

Backend API for TrojanPlate — an AI-powered **daily diet planner** for USC students. This repo is **API-only**; wire it to a separate frontend.

| Doc | Why |
|---|---|
| [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) | Frontend integration contract |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Backend architecture |
| [`docs/JUDGING.md`](docs/JUDGING.md) | Hackathon criteria map |
| [`docs/PRODUCT.md`](docs/PRODUCT.md) | Product scope |

## Setup

```bash
cd TrojanFork-Backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn trojanbites_extract.api.app:app --reload --port 8000
```

OpenAPI: http://127.0.0.1:8000/docs

```bash
./scripts/demo_usc.sh
curl -s -X POST http://127.0.0.1:8000/v1/plan/day \
  -H 'Content-Type: application/json' \
  -d @data/menus/examples/plan_day_usc.json | python3 -m json.tool
```

## Integrate from the frontend

CORS is open for the pilot. Primary calls:

| Endpoint | Use |
|---|---|
| `POST /v1/plan/day` | Full-day plan (`usc_dining` or `off_campus`) |
| `POST /v1/plan/swap` | Lock a meal and replan the rest of the day |
| `GET /v1/menus/usc-dining` | Dining-hall snapshot |
| `GET /v1/menus/off-campus` | Curated nearby dishes |
| `GET /health` | Readiness |

Example bodies: `data/menus/examples/`.

## Modes

1. **USC Dining** — Village, EVK, Parkside (meal-swipe / AYCE).  
2. **Off-Campus** — curated nearby menus, cuisine + cash budget (default 0.3 mi).

## Honesty

- Dated verified snapshots — no invented dishes  
- Unknown nutrition stays unavailable  
- Allergies are hard filters  
- Claude live extract is optional background stretch  

## Tests

```bash
pytest -q
```

Do not commit `.env`.
