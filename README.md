# TrojanPlate

**Your goals. Your campus. Your plate.**

AI-powered **daily diet planner** for USC students. Plan breakfast, lunch, and dinner from **USC residential dining halls** or **walkable off-campus restaurants** (default 0.3 mi), with up to three personalized recommendations per meal — and a plan that updates when you swap.

| Doc | Why |
|---|---|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Product architecture |
| [`docs/JUDGING.md`](docs/JUDGING.md) | Hackathon criteria map |
| [`docs/ADOPTION.md`](docs/ADOPTION.md) | Campus adoption path |
| [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) | API contract |
| [`docs/PRODUCT.md`](docs/PRODUCT.md) | Product scope & demo story |

## Quick start

```bash
cd TrojanFork-Backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn trojanbites_extract.api.app:app --reload --port 8000
```

Open **http://127.0.0.1:8000/** (mobile-first demo) or `/docs`.

```bash
./scripts/demo_usc.sh
curl -s -X POST http://127.0.0.1:8000/v1/plan/day \
  -H 'Content-Type: application/json' \
  -d @data/menus/examples/plan_day_usc.json | python3 -m json.tool
```

## Product modes

1. **USC Dining** — Village, EVK, Parkside (meal-swipe / AYCE).  
2. **Off-Campus** — curated nearby menus, cuisine + cash budget.

## AI / data honesty

- Recommendations use **dated verified snapshots**, not invented dishes.  
- Unknown nutrition stays `null` / unavailable.  
- Allergies are hard filters; never guaranteed allergen-free.  
- Claude live extract is optional background stretch — not on the student request path.

## Tests

```bash
pytest -q
```

Do not commit `.env`.
