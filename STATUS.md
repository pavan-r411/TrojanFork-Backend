# TrojanPlate — Status (USC hackathon)

**Date:** 2026-11-15  
**Product:** TrojanPlate — daily diet planner for USC  
**Judging:** [`docs/JUDGING.md`](docs/JUDGING.md)  
**Readiness:** [`docs/DEPLOYMENT_READINESS.md`](docs/DEPLOYMENT_READINESS.md) · **Demo:** [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md)

---

## Implemented (pilot E2E)

| Capability | Notes |
|---|---|
| Sign-in (optional) | Bearer sessions; PBKDF2 passwords; owned profile + day plans |
| Live plan UI | `/ui/` → `POST /v1/live/plan` |
| Preferences + budget + campus/off-campus | Profile onboarding + dining limits |
| Variety | ≤3 picks / slot across kitchens when inventory allows |
| Swap preview + undo | Client preview deltas; undo last swap |
| Directions | **Get directions** walking Maps URLs (Place ID / coords / address) |
| Empty states | Structured `empty_state` reason codes + recovery actions |
| Breakfast fix | Inferred breakfast-by-name; see `docs/BREAKFAST_FAILURE.md` |
| Honest nutrition | `null` unknowns; **Nutrition unavailable** / AI-estimated labels |
| Persistence | localStorage always; server plans when signed in |
| Off-campus DPS job | Background Places + Gemini ingestion (teammate boundary split) |
| AYCE / swipe modeling | No fake per-dish dining-hall prices |
| Health | `/health`, `/ready` |

---

## Tests

```bash
cd TrojanFork-Backend && .venv/bin/python -m pytest -q   # 110 passed (2026-11-15)
cd TrojanFork-Frontend && npm test                       # nutrition + live-plan + Chrome smoke
```

---

## Deploy

| Item | Status |
|---|---|
| Local demo | `uvicorn … --port 8000` → http://127.0.0.1:8000/ui/ |
| Permanent host | `render.yaml` ready — **not verified live in this pass** |
| Public HTTPS | Pending authorized Render/Fly/ngrok publish |

---

## Remaining

- [ ] Publish + verify production HTTPS URL end-to-end with live keys  
- [ ] Record ≤3 min demo video  
- [ ] Tighten CORS and paid-call rate limits for public production  
