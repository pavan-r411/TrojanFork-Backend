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
| Public HTTPS (tunnel) | `https://lili-sparing-aliya.ngrok-free.dev/` (live while local server + ngrok run) |
| Permanent host | `render.yaml` / `Procfile` ready — connect Render/Fly to GitHub for stable URL |
| GitHub | https://github.com/pavan-r411/TrojanFork-Backend/tree/murali-krishna |

---

## P0 remaining for Sunday

- [x] Public HTTPS URL (ngrok tunnel; replace with Render for stability)  
- [x] Pitch slides markdown — [`docs/PITCH_SLIDES.md`](docs/PITCH_SLIDES.md)  
- [x] Devpost checklist — [`docs/DEVPOST.md`](docs/DEVPOST.md)  
- [x] Push latest branch to GitHub  
- [ ] Record ≤3 min demo video from the live UI  
- [ ] Export slides to PDF / Google Slides + screenshot  
