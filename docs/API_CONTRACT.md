# Trojan Fork — API Contract

**Product:** TrojanPlate  
**Tagline:** Your goals. Your campus. Your plate.  
**Product scope:** USC University Park Campus daily diet planner  
**API version:** 0.5.0  
**Base URL (local):** `http://127.0.0.1:8000`  
**Interactive docs:** `http://127.0.0.1:8000/docs`  
**OpenAPI JSON:** `http://127.0.0.1:8000/openapi.json`  
**Judging:** [`JUDGING.md`](JUDGING.md) · **Demo:** `scripts/demo_usc.sh`  
**Last updated:** 2026-11-14  

## Conventions

- JSON request/response bodies (`Content-Type: application/json` for POST).
- Unknown facts are `null` (never invented).
- Menu `price.amount` is **menu price excluding tax and fees**.
- Distance is **straight-line miles** (`haversine_miles_straight_line`) unless noted.
- Nutrition filters require **restaurant_published** values; missing macros cannot satisfy constraints.
- Campus scoping is required for catalog/search endpoints: pass `campus_id` and/or resolvable `lat`/`lng`.
- CORS: open (`*`) for local pilot.

### Common error shapes

| HTTP | When |
|---|---|
| 400 | Invalid input (e.g. only one of lat/lng) |
| 401 | Ingestion token required/mismatch |
| 404 | Unknown campus / restaurant / job |
| 409 | Campus unresolved (needs confirmation); body includes candidates |
| 422 | FastAPI validation error |

---

## 1. Health

### `GET /health`  
### `GET /ready`

**Response 200**

```json
{
  "status": "ok",
  "product": "Trojan Fork",
  "database_url": "sqlite:///./data/trojanbites.db",
  "campuses": ["usc_upc", "ucla_westwood"],
  "ready": true
}
```

---

## 1b. Product plan API (primary)

### `POST /v1/plan/day`

Build a full-day plan for `usc_dining`, `off_campus`, or `hybrid`.

**Body:** `{ "profile": {...}, "situation": { "mode": "usc_dining"|"off_campus"|"hybrid", ... }, "locked": [] }`

**Response includes:**
- `periods[]` with ≤3 recommendations, `suggested_time`, `match_percent`, `walk_minutes_estimate`, `why[]`
- `daily_targets` (estimated student needs when height/weight provided)
- `daily_planned` (sum of known/estimated dish macros)
- `spending` (swipes + cash / Dining Dollars)
- Per card: `protein_g`, `calories_kcal`, `nutrition.confidence` (`confirmed`|`estimated`|`unavailable`)
- Optional `situation.min_protein` hard filter
- Dining-hall macros may be **estimated** heuristics (labeled); published values used when available

**Hybrid:** main meals from USC dining (swipe/AYCE); snacks from curated off-campus (cash/Dollars).

### `POST /v1/plan/swap`

Lock one meal (`meal_period` + `dish_id`) and replan the rest of the day.  
Returns `rebalance_delta` (`calories_kcal` / `protein_g` null when macros unknown).

### `POST /v1/profile/targets`

Estimated daily macro targets for Profile rings (`confidence: estimated|unavailable`).  
Not dish nutrition.

### `GET /v1/search?q=&mode=all|usc_dining|off_campus|hybrid&limit=`

Free-text search over grounded snapshot dishes.

### `GET /v1/menus/usc-dining` · `GET /v1/menus/off-campus`

Snapshot catalogs used by the planner.

### Frontend note

This repository is **backend-only**. The mobile UI lives in a separate frontend app; use this contract + `/docs` to integrate.

---

## 1c. USC overview (judging / partners)

### `GET /v1/usc/overview`

USC pitch, AI guarantees, and snapshot catalog counts.

**Response 200**

```json
{
  "product": "Trojan Fork",
  "scope": "usc_upc",
  "university": "University of Southern California",
  "friction": "Trojans need budget-, diet-, and macro-aware food near UPC...",
  "ai_guarantees": [
    "Claude runs only in background ingestion jobs — never on the student request path.",
    "Unknown calories/protein stay null; nutrition estimation is off."
  ],
  "catalog": {
    "restaurants": 10,
    "restaurants_in_dps_boundary": 10,
    "available_menu_items": 40,
    "hospitality_seeds": 3
  },
  "demo": {
    "script": "scripts/demo_usc.sh",
    "judging": "docs/JUDGING.md"
  }
}
```

---

## 2. Campuses

### `GET /v1/campuses`

List configured universities/campuses. Product scope is USC; other packs may appear as future expansion.

**Response 200**

```json
{
  "product_scope": "usc_only",
  "default_campus_id": "usc_upc",
  "judging_campus_id": "usc_upc",
  "count": 2,
  "campuses": [
    {
      "campus_id": "usc_upc",
      "university_id": "usc",
      "display_name": "USC University Park Campus",
      "short_name": "USC UPC",
      "center": { "lat": 34.0224, "lng": -118.2851 },
      "boundary": {
        "type": "official_patrol",
        "official": true,
        "boundary_id": "usc_upc_dps",
        "boundary_version": "v2025-01",
        "radius_miles": null,
        "notes": "...",
        "source_url": "https://dps.usc.edu/patrol/"
      },
      "discovery": {
        "default_walk_miles": 0.3,
        "max_walk_miles": 1.0
      }
    }
  ]
}
```

`boundary.type` is either `official_patrol` or `search_radius`. Radius boundaries are **not** official patrol zones.

---

### `GET /v1/campuses/resolve`

Resolve active campus from coordinates and/or manual id.

**Query**

| Param | Type | Required | Notes |
|---|---|---|---|
| `lat` | float | no* | User latitude |
| `lng` | float | no* | User longitude |
| `campus_id` | string | no* | Manual selection |

\* Provide `campus_id` **or** both `lat`/`lng`.

**Response 200**

```json
{
  "status": "resolved",
  "active_campus_id": "usc_upc",
  "message": "Auto-selected USC University Park Campus (0.0 mi)",
  "user": { "lat": 34.0224, "lng": -118.2851 },
  "candidates": [
    {
      "campus_id": "usc_upc",
      "university_id": "usc",
      "display_name": "USC University Park Campus",
      "distance_miles": 0.0,
      "boundary_type": "official_patrol",
      "boundary_official": true
    }
  ]
}
```

**`status` values**

| Value | Meaning |
|---|---|
| `resolved` | Exactly one nearby campus auto-selected |
| `manual` | `campus_id` provided and accepted |
| `needs_confirmation` | Multiple/plausible campuses — user must confirm |
| `unresolved` | No campus / missing input |

Never silently returns a distant campus as active without confirmation.

---

### `POST /v1/campuses/select`

Confirm / manually select campus.

**Body**

```json
{
  "campus_id": "ucla_westwood",
  "lat": 34.0689,
  "lng": -118.4452
}
```

**Response 200** — same shape as resolve (`status`, `active_campus_id`, `message`, `candidates`).  
**404** — unknown `campus_id`.

---

## 3. Restaurants

### `GET /v1/restaurants`

Campus-scoped restaurant catalog.

**Query**

| Param | Type | Default | Notes |
|---|---|---|---|
| `campus_id` | string | — | Or resolve via lat/lng |
| `lat` | float | — | |
| `lng` | float | — | |
| `boundary_only` | bool | `true` | Only `inside`/`boundary` status |

**Response 200**

```json
{
  "campus_id": "usc_upc",
  "count": 10,
  "restaurants": [
    {
      "restaurant_id": "tb-r-001",
      "campus_id": "usc_upc",
      "name": "Rosso Oro's Pizzeria",
      "branch_name": "USC Hotel / University Gardens",
      "lat": 34.0203,
      "lng": -118.2809,
      "boundary_status": "inside",
      "cuisines": ["pizza", "italian-american"],
      "website": "https://...",
      "menu_links": [],
      "business_status": "operational"
    }
  ]
}
```

**409** — campus unresolved.

---

### `GET /v1/restaurants/nearby`

Nearby restaurants when location is enabled (within campus).

**Query**

| Param | Type | Default | Notes |
|---|---|---|---|
| `lat` | float | required | |
| `lng` | float | required | |
| `campus_id` | string | optional | Else resolved from lat/lng |
| `max_miles` | float | `0.3` | Range 0.05–5.0 |

**Response 200**

```json
{
  "campus_id": "usc_upc",
  "user": { "lat": 34.0224, "lng": -118.2851 },
  "max_miles": 0.3,
  "distance_metric": "haversine_miles_straight_line",
  "count": 5,
  "restaurants": [
    {
      "restaurant_id": "...",
      "name": "Everybody's Kitchen",
      "branch_name": "EVK",
      "distance_miles": 0.098,
      "lat": 34.0211,
      "lng": -118.2858,
      "cuisines": ["american", "campus_dining"],
      "boundary_status": "inside",
      "menu_item_count": 0,
      "campus_id": "usc_upc"
    }
  ]
}
```

---

### `GET /v1/restaurants/{restaurant_id}`

Restaurant detail + menu + macros.

**Response 200**

```json
{
  "restaurant": {
    "restaurant_id": "tb-r-001",
    "campus_id": "usc_upc",
    "university_id": "usc",
    "name": "Rosso Oro's Pizzeria",
    "branch_name": "...",
    "address": { "formatted": "..." },
    "lat": 34.0203,
    "lng": -118.2809,
    "boundary_status": "inside",
    "cuisines": [],
    "website": "...",
    "service": {}
  },
  "menu_items": [
    {
      "item_id": "tb-i-0001",
      "name": "Fresh Mozzarella slice",
      "description": null,
      "category": "Pizza by the slice",
      "dietary_claims": [],
      "variants": [
        {
          "variant_id": "...",
          "size_label": null,
          "serving_label": "1 slice",
          "price": {
            "amount": 2.9,
            "currency": "USD",
            "note": "menu_price_excludes_tax_and_fees"
          },
          "nutrition": {
            "evidence_status": "unknown",
            "serving_basis": null,
            "published": {
              "calories_kcal": null,
              "protein_g": null,
              "carbohydrates_g": null,
              "fat_g": null,
              "fiber_g": null,
              "sugar_g": null,
              "sodium_mg": null
            },
            "estimated": null
          }
        }
      ]
    }
  ]
}
```

**404** — `restaurant_not_found`.

`nutrition.evidence_status`: `restaurant_published` | `estimated` | `unknown`.  
Pilot: estimation disabled; prefer `published` / `unknown`.

---

## 4. Meals / search

### `GET /v1/meals`  
### `GET /v1/search/dishes`

Deterministic dish search (aliases of the same handler).

**Query**

| Param | Type | Default | Notes |
|---|---|---|---|
| `campus_id` | string | — | Or lat/lng |
| `lat` / `lng` | float | — | Both or neither |
| `max_miles` | float | 0.3 if lat set | |
| `budget_max` | float | — | Max menu price |
| `diet` | string[] | [] | Required published claims (repeat param) |
| `cuisine` | string[] | [] | Any-match |
| `min_protein` | float | — | Published protein_g |
| `min_calories` / `max_calories` | float | — | Published kcal |
| `meal_period` | string | — | e.g. `lunch` |
| `allow_uncertain` | bool | false | If false, strict matches only |
| `limit` | int | 50 | 1–200 |

**Example**

`GET /v1/meals?campus_id=ucla_westwood&budget_max=12&diet=vegetarian&min_protein=15`

**Response 200**

```json
{
  "campus_id": "ucla_westwood",
  "query": {
    "lat": null,
    "lng": null,
    "max_miles": null,
    "budget_max": 12,
    "diet": ["vegetarian"],
    "cuisine": [],
    "min_protein": 15,
    "meal_period": null,
    "strict": true,
    "price_basis": "menu_price_excludes_tax_and_fees",
    "distance_metric": "haversine_miles_straight_line"
  },
  "count": 1,
  "total_matches": 1,
  "meals": [
    {
      "item_id": "...",
      "restaurant_id": "...",
      "restaurant_name": "UCLA Dining Fixture Café",
      "item_name": "Garden Veggie Wrap",
      "price_amount": 9.5,
      "currency": "USD",
      "published_protein_g": 18.0,
      "published_calories_kcal": 420.0,
      "match_class": "strict",
      "uncertain_reasons": [],
      "distance_miles": null,
      "restaurant_lat": 34.0705,
      "restaurant_lng": -118.4441,
      "campus_id": "ucla_westwood",
      "price_note": "menu_price_excludes_tax_and_fees",
      "distance_metric": "haversine_miles_straight_line"
    }
  ],
  "note": "Unknown nutrition cannot satisfy verified nutrition requirements."
}
```

`match_class`: `strict` | `uncertain_alternative`.

---

## 5. Recommendations

### `POST /v1/suggest`  
### `POST /v1/recommendations`

Location-on / campus-selected suggestions. Returns stored matches immediately; optionally queues background collection.

**Body**

```json
{
  "lat": 34.0224,
  "lng": -118.2851,
  "campus_id": null,
  "max_miles": 0.3,
  "budget_max": 12,
  "diet": ["vegetarian"],
  "cuisine": [],
  "min_protein": 25,
  "meal_period": "lunch",
  "limit": 20,
  "collect_missing": true
}
```

| Field | Type | Default | Notes |
|---|---|---|---|
| `lat` / `lng` | float | null | Location mode when both set |
| `campus_id` | string | null | Manual campus |
| `max_miles` | float | 0.3 | 0.05–5.0 |
| `budget_max` | float | null | |
| `diet` | string[] | [] | |
| `cuisine` | string[] | [] | |
| `min_protein` | float | null | |
| `meal_period` | string | null | |
| `limit` | int | 20 | 1–100 |
| `collect_missing` | bool | true | Start ingestion job |

**Response 200**

```json
{
  "mode": "location_enabled",
  "campus_id": "usc_upc",
  "user": { "lat": 34.0224, "lng": -118.2851 },
  "max_miles": 0.3,
  "distance_metric": "haversine_miles_straight_line",
  "price_basis": "menu_price_excludes_tax_and_fees",
  "nearby_restaurants": [],
  "suggested_meals": [],
  "counts": { "restaurants": 0, "meals": 0 },
  "ingestion_job": {
    "job_id": "job_...",
    "campus_id": "usc_upc",
    "status": "queued",
    "progress": { "stage": "queued", "percent": 0 }
  },
  "explanations": [
    {
      "type": "deterministic",
      "text": "Showing stored usc_upc matches only. Constraints are not silently relaxed. Missing calories/protein stay unknown."
    }
  ]
}
```

`mode`: `location_enabled` | `campus_selected`.

---

## 6. Ingestion jobs

### `POST /v1/ingestion/jobs`

Start (or return idempotent) campus collection job.

**Headers**

| Header | Required | Notes |
|---|---|---|
| `X-Ingest-Token` | if `INGEST_API_TOKEN` set | Must match env |

**Body**

```json
{
  "campus_id": "usc_upc",
  "run_async": true
}
```

**Response 200** — job object (see below).  
**401** — `ingestion_unauthorized`.  
**404** — unknown campus.

Idempotency key: `campus_slice:{campus_id}:{YYYY-MM-DD}` (one active/completed job per campus per day).

---

### `GET /v1/ingestion/jobs/{job_id}`

**Response 200**

```json
{
  "job_id": "job_...",
  "campus_id": "usc_upc",
  "job_type": "campus_slice",
  "status": "partial",
  "progress": { "stage": "partial", "percent": 100 },
  "errors": ["places_discovery_blocked: GOOGLE_MAPS_API_KEY missing"],
  "result": {
    "restaurants_upserted": 1,
    "menu_items_upserted": 1,
    "places_shells_added": 0,
    "claude_used": false,
    "nutrition_estimation": false,
    "notes": "..."
  },
  "idempotency_key": "campus_slice:usc_upc:2026-11-15",
  "created_at": "...",
  "started_at": "...",
  "finished_at": "..."
}
```

**`status` values:** `queued` | `running` | `partial` | `completed` | `failed`.

---

## 7. Frontend integration sequence

1. `GET /health` — confirm API up.  
2. If location on: `GET /v1/campuses/resolve?lat=&lng=`.  
3. If `needs_confirmation`: show candidates → `POST /v1/campuses/select`.  
4. `POST /v1/suggest` with lat/lng + diet/budget filters.  
5. Poll `GET /v1/ingestion/jobs/{id}` if `ingestion_job` returned.  
6. `GET /v1/restaurants/{id}` for dish detail.

---

## 8. Configured campuses (pilot)

| campus_id | university_id | Boundary |
|---|---|---|
| `usc_upc` | `usc` | Official DPS patrol GeoJSON |
| `ucla_westwood` | `ucla` | Search radius (not official) |

---

*Source of truth in code: `src/trojanbites_extract/api/app.py`*

## Live recommendation flow (Google Places + OpenAI)

`POST /v1/live/suggest` is the request-scoped route for the new application flow. It does not query the stored catalog or use Gemini. See README.md → On-demand live recommendations for the full Postman example.

Required body: `mode` (`off_campus` or `usc_dining`), `date` (`YYYY-MM-DD`), `meal_period` (`breakfast`, `brunch`, `lunch`, `dinner`, `snack`).

Off-campus location: both `lat`/`lng`, or a specific `location_name` resolved using Google Places. Optional `radius_miles` defaults to 0.3 (0.05–1). Optional `budget_max`, explicit `diet` claims, and existing `preferences` (goal, preferred_foods, targets, remaining). Coordinates take precedence over a supplied name. Location-name results include `resolved_location` so the client can show/verify the match.

USC: optional `dining_hall` (`evk`, `parkside`, `university-village`, `All halls`). Menus come from the official, date-specific USC Hospitality JSON feed, not restaurant discovery.

Response includes `data_mode: live`, `retrieved_at`, `suggested_meals`, `personalization`, `sources`, `warnings`, `resolved_location`, `distance_metric`. Unknown nutrition/prices are null. Source failures may produce partial or empty results; provider setup/extraction failures return 503 with a sanitized `detail`. Input schema violations return 422. No stored or invented menu fallback occurs. The original `/v1/suggest` and `/v1/recommendations` remain legacy catalog routes.


### Daily plan for the connected UI

`POST /v1/live/plan` accepts `{mode, date, profile, context}`. `profile` supports goal, dietary_preferences, allergies, disliked_ingredients, snacks, targets, remaining. `context` supports origin `{lat,lng}`, max_walk_m, per_meal_budget_cents, daily_budget_cents, meal_swipes_available, dining_hall. Response is the frontend `DailyPlan` type with source-attributed recommendations for breakfast/lunch/dinner and optional snack. Off-campus retrieval/extraction runs once within the request. Selections and locks are managed in the browser, and do not imply consumption. No user database is accessed.

The frontend is served at `/ui/`. It uses `/v1/live/plan`, not the legacy catalog `/v1/suggest`. Nutrition targets and eaten logs are session-local in the browser, with no calls to the previously proposed server `/api/nutrition/daily` or `/api/meals/log` routes. These routes are not implemented. No demo data is used in live mode.
