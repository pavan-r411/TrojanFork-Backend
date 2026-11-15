# TrojanPlate — USC Adoption Path

**Scope:** University Park Campus daily diet planning (USC Dining + Off-Campus).

## Why departments can say yes

1. Uses Hospitality dining menus and a small verified nearby set — not invented dishes.  
2. Meal-swipe / AYCE modeled correctly (no fake buffet item prices).  
3. Unknown nutrition and allergens labeled honestly.  
4. FastAPI + snapshot JSON — easy for SG / IT to host.

## Partners

| Partner | Role |
|---|---|
| USC Student Government | Pilot cohort, feedback |
| USC Hospitality | Menu source of truth |
| DPS (public materials) | Campus geography honesty |

## Rollout

| Phase | Outcome |
|---|---|
| Hackathon | Dated snapshots + public demo UI |
| Semester 1 | Hosted API, more halls/retail, live menu refresh |
| Later | Walking routes, preference learning, authorized integrations |

## Run

```bash
pip install -e .
uvicorn trojanbites_extract.api.app:app --host 0.0.0.0 --port 8000
```

Open `/` for TrojanPlate. Optional: `INGEST_API_TOKEN` for paid collection jobs.
