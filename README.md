# TrojanPlate Backend

**Your goals. Your campus. Your plate.**

Backend API for TrojanPlate — an AI-powered **daily diet planner** for USC students. API code and data live in this repository. When the sibling `TrojanFork-Frontend` checkout is present, the backend also serves it at `/ui/`.

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

## Notes

- Missing published calories stay `null`; separately labeled AI estimates are available in the live flow.
- Menu prices exclude tax/fees.
- Distance is straight-line miles unless Routes API is added later.
- Do not commit `.env`.

## OpenAI meal personalization

`POST /v1/suggest` (also `/v1/recommendations`) now filters the catalog first, then asks OpenAI to rank up to three existing dishes for one meal period. `personalize: false` retains the original catalog-only behavior. Claude remains an optional **menu extraction** provider; it is not used for meal personalization.

Configure only in backend `.env`:

```dotenv
RECOMMENDATION_PROVIDER=openai
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4.1-mini
OPENAI_TIMEOUT_S=8
RECOMMENDATION_CANDIDATE_LIMIT=30
```

Example request:

```json
{
  "campus_id": "usc_upc",
  "budget_max": 15,
  "diet": ["vegetarian"],
  "meal_period": "lunch",
  "collect_missing": false,
  "personalize": true,
  "preferences": {
    "goal": "training_support",
    "preferred_foods": ["tofu", "rice"],
    "allergies": [],
    "excluded_ingredients": [],
    "targets": {"calories": 2200, "protein_g": 130},
    "remaining": {"calories": 1200, "protein_g": 75}
  }
}
```

`diet`, `cuisine`, `budget_max`, published nutrition constraints, campus and distance remain server-side catalog filters. `preferences` provides soft ranking context, not instructions. Targets/remaining values are supplied inputs, not calculated or persisted by this endpoint. No body measurements or user identity are sent to OpenAI. Up to 30 candidates are sent by default. The request uses Responses API strict JSON Schema with `store: false`, an eight-second timeout, and no automatic retries. This is not a daily calorie planner yet.

The response retains `suggested_meals`, with additive variant ID, published carbs/fat, serving label, evidence status, and `recommendation_reason`. `personalization` reports provider/status/warnings. AI output contains only candidate IDs and reasons; database records provide every price and nutrition value. Unknown values remain null. Duplicate, invented or malformed choices, incomplete responses, refusals, timeouts, and API errors use a labeled deterministic fallback. An empty valid selection stays empty. Insufficient matches never produce invented options.

**Current restriction limitation:** search hits cannot establish safe ingredient/allergen eligibility. Nonempty `preferences.allergies` or `excluded_ingredients` returns no suggestions and `restriction_evidence_missing`, including when personalization is disabled. Add a dedicated evidence-backed eligibility check before enabling these recommendations. Dietary claims alone do not establish allergen safety.

Existing API ingestion defaults remain unchanged: set `collect_missing: false` when only ranking stored data. No live OpenAI request is made without a key and candidates. Paid API calls occur when personalization is enabled and configured; production authentication, per-user rate limits and spending enforcement are still required (the existing `MAX_LLM_USD_PER_DAY` setting is not enforced by this adapter).

The existing frontend is still on its demo `/api/...` contract. This change implements backend personalization only; frontend `/api/plans/generate`, `/api/plans/swap`, daily tracking, and persistence still require the separate integration layer. Keep frontend demo mode enabled until that layer is implemented. OpenAI keys must never be added to frontend config.

Run `.venv/bin/python -m pytest -q`. `tests/test_recommendations.py` uses mocked HTTP responses and never spends API credits. Provider request reference: https://developers.openai.com/api/docs/guides/structured-outputs

## On-demand live recommendations (Google Places + OpenAI)

`POST /v1/live/suggest` now uses **Google Places → official website menu retrieval → OpenAI extraction and ranking**. Gemini is no longer called. There are no catalog/database reads, writes, cache entries or ingestion jobs in this flow. Legacy `/v1/suggest` remains catalog-based for compatibility.

Use the existing backend `.env` keys `GOOGLE_MAPS_API_KEY` (Places API New enabled) and `OPENAI_API_KEY`. `OPENAI_MODEL` defaults to `gpt-4.1-mini`. `GEMINI_API_KEY` and Gemini configuration are unused by this endpoint. Keep all keys server-side. Live tests succeeded for both USC Dining and off-campus menu recommendations on November 14, 2026.

### Postman

Start `uvicorn trojanbites_extract.api.app:app --reload --port 8000`. Send POST to `http://127.0.0.1:8000/v1/live/suggest`, with Body → raw → JSON and `Content-Type: application/json`:

```json
{
  "mode": "off_campus",
  "date": "2026-11-14",
  "location_name": "USC Village, Los Angeles",
  "radius_miles": 0.3,
  "meal_period": "dinner",
  "diet": [],
  "preferences": {
    "goal": "balanced",
    "preferred_foods": ["rice bowls"],
    "targets": {"calories": 2200, "protein_g": 130},
    "remaining": {"calories": 1200, "protein_g": 75}
  }
}
```

Use the date you want to query. Alternatively replace `location_name` with `lat: 34.0224` and `lng: -118.2851`. Both coordinates must be supplied together. Named locations use Places Text Search's best match and return `resolved_location`; verify this is the intended location. Supplying coordinates avoids an ambiguous name. A radius is geographic distance, not a walking route.

For USC use `mode: "usc_dining"`, `dining_hall: "evk"` (or `parkside`, `university-village`, `All halls`) and your requested date/meal period. Location is not needed. Supported periods include `brunch`; the API does not silently substitute brunch for lunch or a different date. Some periods may have no menu. The current USC feed lacks per-item prices, calories and macros, so these remain null.

### Source behavior

Off-campus discovery returns up to ten Places results; the pipeline distance-checks the coordinates, then visits up to five nearest websites and up to two menu/nutrition links per site concurrently. In-memory fetching checks public URLs at each redirect, robots rules, response sizes and timeouts. HTML, text, JSON and up to ten PDF pages are supported. JavaScript-only menus, login pages, delivery platforms and inaccessible sites may yield no usable dishes. There is no speculative or stored-menu fallback. The bounded search is not an exhaustive list of restaurants.

OpenAI extracts source-attributed dish facts with strict structured output, using `store: false`. Dish names must occur in a source quote. Numerical values require a verbatim source quote containing the dish name and an explicitly labeled value; unsupported numbers remain null. Dietary filters require explicit claims in the dish quote. A maximum budget excludes dishes with unknown prices. Menu text is untrusted input; OpenAI cannot fetch arbitrary URLs or override the provided sources. This validates text evidence, not the restaurant's real-time stock or nutritional accuracy. Request-date availability for off-campus published menus is not guaranteed.

USC reads the official feed used by its menu page: `https://hospitality.usc.edu/wp-json/hsp-api/v1/get-res-dining-menus/{hall}?y=...&m=...&d=...`. Returned dates and meal names must match. No off-campus sources are used. The JSON is parsed directly; OpenAI only ranks these dishes.

OpenAI chooses up to three eligible dishes using the supplied preferences, goals and remaining nutrition. Unknown nutrition stays unknown, with no estimates based on dish names. Allergies/ingredient exclusions currently fail closed because available evidence cannot establish safety. If extraction fails, no invented menu is produced. If ranking fails, the response labels any live filtered fallback explicitly.

Response includes `suggested_meals`, `sources` with source URLs and quoted evidence where applicable, `retrieved_at`, `resolved_location`, `personalization`, and source warnings. Partial retrieval can still return results from successful sources. Use a client timeout of at least 120 seconds for testing; live retrieval/extraction can be slower than stored search. Requests may incur Google Places and OpenAI charges. The existing frontend remains in demo mode and needs its daily-plan API adapter connected separately; this endpoint can be tested directly in Postman now.

Run `.venv/bin/python -m pytest -q`. Live-flow tests cover official USC date/period matching, radius and budget checks, unsupported source facts, missing location, restrictions and private URL rejection. Unit tests use mocks and do not spend API credits.


## Connected TrojanPlate frontend

The backend now serves the existing UI at `/ui/` (the root redirects there). With your server already running, open `http://127.0.0.1:8000/ui/`. `POST /v1/live/plan` accepts the frontend's mode/date/profile/context payload and returns its typed daily-plan contract. Off-campus discovery/extraction is shared within a daily request, then OpenAI ranks meal choices per slot; no cross-request food cache or catalog is used. USC slots read official menus. Missing nutrition remains null.

The UI uses same-origin requests with a 120-second timeout; no backend host or secret is embedded in frontend source. `npm start` in the frontend folder can launch this same backend if it is not already running. The frontend now has demo mode disabled. Plans/selections stay in browser memory, while eaten logs and manually entered targets use browser sessionStorage. These are not server-owned user records, and no account/database has been added. See the frontend README for tracking limits and instructions.


Daily variety: `/v1/live/plan` coordinates meal slots sequentially, removes already recommended IDs/dish names, and reserves candidates for later periods. Off-campus breakfast/snack options require explicit meal-period text from the fetched menu; unlabeled meals can be considered for lunch/dinner with unverified-availability notes. If the live sources and filters yield too few distinct meals, slots remain empty with a clear explanation instead of repeating dishes. Unknown-nutrition explanations cannot speculate about ingredients or claim balanced macros.

Shared menu prices: live extraction accepts explicit category prices (for example a printed `Salads $12.95` heading followed by named salad options). The source text and exact option line are required; additions, subsequent price headings, and sauce-option boundaries end the category. This prevents rejecting valid menu prices merely because the price is printed once per section, while retaining null for genuinely unpublished prices.

## Optional AI estimates

The UI's dining settings now include **Include AI estimates for missing prices and nutrition** (off by default). This sends `context.include_ai_estimates: true` to `/v1/live/plan`; direct `/v1/live/suggest` requests use `include_ai_estimates: true` at the top level. No estimator is called unless enabled. This option allows source-backed dishes with missing prices through extraction for estimation before budget filtering.

`recommend/estimates.py` sends a bounded, venue-balanced batch of at most 24 existing dish IDs to OpenAI. It requests low/high ranges and an assumed serving. Published price/macros remain immutable; `MealHit.ai_estimates` stores approximations separately. Arbitrary IDs, duplicates, reversed/nonfinite/out-of-bounds ranges and provider failures never create menu facts. Failed or missing estimates remain unknown. No allergen safety, dietary claims, menu availability or new dishes are estimated. USC hall admission prices are not estimated.

The frontend daily-plan adapter adds per-field nutrition quality, preserved published values, `estimated_ranges`, and estimated price ranges/status. Effective tracking values are range midpoints. A dish whose estimated price range overlaps the budget may be included, explicitly budget-uncertain; an estimate entirely above the budget is excluded. A price that cannot be estimated still needs the separate unpublished-price opt-in. Prices exclude taxes/fees.

Cards display AI-estimated ranges and assumed servings. Session logs retain published/estimated snapshots, and daily totals are labeled when they include estimates. Users can adjust the portion and override an estimated price with their actual total amount paid. Estimates are approximate and cannot recover blocked/missing restaurant menus. One real OpenAI estimation call succeeded; published nutrition remained null while estimates were stored separately.


AI estimates are now enabled by default for missing prices/macros on known menu dishes. The frontend no longer offers an estimation checkbox. Published values remain separate, and cards and totals retain AI-estimate labels, ranges and assumed portions. Backend clients may explicitly send `include_ai_estimates: false` for published-only behavior.

## Local provider response records

Maps and OpenAI response bodies are now saved locally for debugging, enabled by default. Files are `data/provider_records/YYYY-MM-DD.jsonl` (UTC date), one JSON object per provider response. Each record includes timestamp, record ID, provider, operation, model where relevant, HTTP status, provider request ID where available, and the response body. Success and HTTP error responses are recorded for Maps nearby search/location lookup and OpenAI menu extraction, recommendations and estimates.

Request headers, keys and request prompts are not recorded. Configured secret values and sensitive key/token fields are redacted from response bodies. The folder is Git-ignored and is not served by the frontend; new files have owner-only permissions. Records are debug history, not a menu cache or recommendation source. They can contain generated meal details and personalized explanations. No automatic retention/deletion is configured; files remain until you remove them.

Set `PROVIDER_RECORDS_ENABLED=false` in backend `.env` and restart to stop recording. `PROVIDER_RECORDS_DIR` optionally changes the directory (relative paths resolve under the backend). Existing past responses cannot be recovered; recording starts with new requests after the running server reloads/restarts. Requests that fail before receiving any HTTP response have no response body to record. Recording failures do not break meal requests. Automated tests disable recording outside dedicated temporary-file tests.


## Vercel deployment

Import this repository with the FastAPI preset and root directory `./`.
`pyproject.toml` declares the nested FastAPI entry point for Vercel.
Keep the existing Python project dependency installation enabled.

Set backend environment variables before deployment:

- `OPENAI_API_KEY` and `GOOGLE_MAPS_API_KEY`: server-side secrets.
- `OPENAI_MODEL=gpt-4.1-mini`
- `PROVIDER_RECORDS_ENABLED=false`
- `DATABASE_URL=sqlite:////tmp/trojanplate.db`

On Vercel, startup skips legacy catalog database initialization. Live recommendations
do not use that database. The SQLite setting only supports legacy endpoints that
initialize it lazily. `/tmp` is ephemeral and is not user
persistence. Do not run ingestion jobs or rely on local provider-record files on Vercel.
The separately deployed frontend is not included in this backend checkout.
Check `/health` and `/docs` after deployment, then test `/v1/live/plan` against the
function duration available on your Vercel plan. A successful build alone does not
verify external provider calls or request duration.
