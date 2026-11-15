# Trojan Fork — Final Status (multi-university pilot)

**Date:** 2026-11-14  
**Product:** Trojan Fork  
**Goal:** Location-aware, multi-university food discovery with USC as first campus and UCLA as second config test.

---

## Implemented

| Capability | Notes |
|---|---|
| Multi-campus registry | `config/universities.yaml`, `config/campuses/usc_upc.yaml`, `config/campuses/ucla_westwood.yaml` |
| Campus resolution | Lat/lng auto-select, manual select, confirmation when ambiguous |
| Official vs radius boundaries | USC = DPS GeoJSON; UCLA = labeled `search_radius` (not official) |
| Campus-scoped restaurants / meals | `campus_id` on records; no cross-campus leakage |
| Background ingestion jobs | `queued/running/partial/completed/failed`, idempotent per campus/day |
| Fast API responses | Returns stored data immediately; optional async collect |
| Deterministic recommendations | Budget, diet claims, protein/calories, distance |
| FastAPI endpoints | Campuses, resolve, nearby, meals, suggest, ingestion jobs, health/ready |
| Pilot data | USC Claude pilot imported; UCLA fixture menu extracted |
| Exports | `exports/usc_restaurants.json` + `.md` |
| Tests | **23 passed** (campus switch, isolation, API, boundary, validation) |

---

## Tested

| Check | Result |
|---|---|
| Resolve USC from test coords (34.0224, -118.2851) | `usc_upc` |
| Resolve UCLA from Westwood coords | `ucla_westwood` |
| UCLA fixture menu → veg wrap under $12 | Pass |
| USC vs UCLA query isolation | Pass |
| Ingestion job idempotency / states | Pass |
| Health/ready | Pass |
| Full pytest suite | **23 passed** |

---

## Deployed

| Item | Status |
|---|---|
| Local API (`uvicorn` on :8000) | **Runnable locally** |
| Cloud / pilot hosting | **Not deployed** — no hosting credentials/config in repo |
| Live health check on public URL | **Blocked** — no deploy target configured |

**Do not treat the backend as “live in production.”** It is a deployable local pilot.

Start locally:

```bash
source .venv/bin/activate
uvicorn trojanbites_extract.api.app:app --reload --port 8000
curl http://127.0.0.1:8000/health
```

---

## Blocked / mocked

| Dependency | Status |
|---|---|
| `ANTHROPIC_API_KEY` | **Empty** — Claude live extraction blocked; deterministic/fixture path used |
| `GOOGLE_MAPS_API_KEY` | **Empty** — Places discovery blocked (reported in job errors) |
| Authorized web search API | Not configured (`adapters.web_search: none`) |
| Walking Routes API | Not implemented — straight-line haversine only |
| Production secrets / auth | Optional `INGEST_API_TOKEN` only |
| UCLA live menus | **Fixture only** (`tests/fixtures/ucla_sample_menu.html`) |

---

## Vertical slice completed tonight

1. Resolve USC from test coordinates — **yes**  
2. Load verified DPS boundary config — **yes**  
3. Discover small restaurant set — **pilot import + seed** (Places blocked)  
4. Retrieve ≥1 permitted menu — **yes** (USC hospitality fetch + UCLA fixture)  
5. Extract/validate dishes — **deterministic** (Claude blocked without key)  
6. Store with sources — **yes**  
7. Budget/diet recommendation — **yes** (campus-scoped)  
8. Export Markdown/JSON — **yes**  
9. Second university (UCLA) without core rewrites — **yes** (config + fixture)

---

## Production gaps

- Fill API keys for live Claude + Places  
- Replace UCLA fixture with real permitted sources  
- Walking-time routing  
- Postgres + real job queue for scale  
- Deploy to hosting + verify public `/health`  
- Stronger auth/rate limits for paid ingestion  

See also: `ARCHITECTURE.md`, `extraction_framework.md`, `README.md`.
