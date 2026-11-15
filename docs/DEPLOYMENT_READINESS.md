# Deployment readiness report — TrojanPlate pilot

**Date:** 2026-11-15  
**Status:** Locally demo-ready. **Not claimed live** — no production URL verified in this pass.

## What works locally

| Area | Evidence |
|---|---|
| Health / ready | `GET /health`, `GET /ready` |
| Auth + owned plans | `POST /v1/auth/register|login`, `GET/PUT /v1/profile`, `GET/PUT /v1/plans`, swap-preview |
| Live daily plan | `POST /v1/live/plan` (Places + OpenAI; USC official feed) |
| Directions | Structured `directions` on each recommendation (Maps walking URL; no API key in URL) |
| Empty states | `empty_state.reason_code` + diagnostics + actions (never “remove allergies”) |
| Breakfast fix | Inferred breakfast-by-name with unverified note; see `BREAKFAST_FAILURE.md` |
| Frontend journey | Sign-in optional, prefs, campus/off-campus, select, swap preview, undo, directions, local+server persistence |
| Automated tests | Backend **110 passed**; frontend nutrition + live-plan + Chrome smoke **passed** |

## Environment

Copy `TrojanFork-Backend/.env.example` → `.env` (never commit secrets):

- Server-only: `OPENAI_API_KEY`, `GOOGLE_MAPS_API_KEY`, optional `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `INGEST_API_TOKEN`
- `DATABASE_URL=sqlite:///./data/trojanbites.db` (auto-migrate on boot)
- `SESSION_TTL_HOURS=168`

Browser never receives private keys. Maps directions links do not embed keys.

## Run

```bash
cd TrojanFork-Backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn trojanbites_extract.api.app:app --reload --port 8000
# UI: http://127.0.0.1:8000/ui/
```

Or from frontend: `npm start` (starts the same backend).

Background off-campus DPS ingestion (optional, not on the student request path):

```bash
trojanbites init-db
trojanbites ingest-off-campus-dps --campus usc_upc --limit 3
```

## Migrations

SQLite schema is created/extended by `init_db()` / `migrate_schema()` on startup (users, auth_sessions, saved_day_plans, restaurants, …).  
**Rollback:** restore the previous `data/trojanbites.db` file from backup before upgrade.  
Validate on a disposable DB first: `DATABASE_URL=sqlite:///./data/trojanbites_pilot.db`.

## Hosting

`render.yaml` + Procfile are present. Connect the Backend GitHub repo to Render/Fly, set env vars, health check `/health`.

**Remaining deploy step:** authorized Render/Fly (or ngrok) publish + verify the HTTPS URL loads `/ui/` and completes the demo script with live keys. Until that succeeds, do **not** mark the app production-live.

## Honest limits

- Live Places/OpenAI E2E depends on billed credentials and network; fixture/smoke tests are labeled and mocked.
- Distance is straight-line, not routed walking time.
- Off-campus allergen safety is text-evidence only; USC uses published tags.
- Food-truck directions require a recently confirmed location or show unavailable.
- Device Maps app deep-link launching was not hardware-tested; browser Google Maps URLs are verified by unit tests.
- CORS is open (`*`) for the pilot — tighten before a public production launch.
- Paid-call rate limiting / `MAX_LLM_USD_PER_DAY` enforcement remains incomplete for production abuse resistance.

## Breakfast failure (confirmed)

**Cause:** Off-campus unlabeled dishes could fill lunch/dinner only; breakfast required explicit `meal_periods`, so pancakes without a “breakfast” label produced **0 choices**.  
**Fix:** Breakfast-name inference with unverified availability labeling + structured `NO_BREAKFAST_MENU_PUBLISHED` empty state. Details: `docs/BREAKFAST_FAILURE.md`.
