# TrojanPlate — Status (USC hackathon)

**Date:** 2026-11-14  
**Product:** TrojanPlate — daily diet planner for USC  
**Judging:** [`docs/JUDGING.md`](docs/JUDGING.md)

---

## Implemented

| Capability | Notes |
|---|---|
| Product pivot | Day planner (not discovery-first) |
| USC Dining snapshot | Village, EVK, Parkside dated `2026-11-14` |
| Off-campus curated set | 4 venues / 76 dishes ≤0.3 mi of Tommy Trojan |
| Profile + day plan API | `POST /v1/plan/day` |
| Meal swap / replan | `POST /v1/plan/swap` |
| Mobile-first UI | `/` onboarding → modes → day plan |
| AYCE / swipe modeling | No fake per-dish dining-hall prices |
| Honest nutrition | Unavailable labeled; estimation off |

---

## Tests

Run `pytest -q` — includes plan engine + frontend smoke.

---

## Deploy

| Item | Status |
|---|---|
| Local demo | `uvicorn trojanbites_extract.api.app:app --port 8000` |
| Cloud | See `Procfile` / `render.yaml` — public URL after host deploy |

---

## P0 remaining for Sunday

- [ ] Public HTTPS URL live  
- [ ] Devpost video / slides / screenshot  
- [ ] Push latest branch to GitHub  
