# TrojanPlate UI ↔ Backend cross-comparison

**UI source:** uploaded design PDF (onboarding, home, My Plan, swap, profile)  
**Backend:** local FastAPI (TrojanPlate plan APIs)  
**Date:** 2026-11-14 · **Updated after backend gap fill**

## Verdict

UI and backend share the same product story. Wire **`POST /v1/plan/day`**, **`POST /v1/plan/swap`**, **`POST /v1/profile/targets`**, and **`GET /v1/search`**. Dish calories are still never invented; daily **targets** may be estimated and labeled.

| Status | Meaning |
|---|---|
| Ready | Direct API support |
| Partial | Present with honest limits |
| Gap | Still frontend / out of scope |
| FE-only | Stay in frontend |

## Coverage table

| UI area | UI expects | Backend today | Status |
|---|---|---|---|
| Goal chips | Build muscle / lose fat / balanced | `nutrition_goal` aliases + targets | Ready |
| Diet style | Veg / Vegan / Pescatarian / Halal | `dietary_preference` incl. pescatarian | Ready |
| Allergies | Multi-select | `allergies[]` hard filter | Ready |
| Body metrics | Height/weight/activity | `POST /v1/profile/targets` estimated | Ready |
| Cuisines | Multi-select | `preferred_cuisines[]` | Ready |
| Two modes | USC / Off-Campus | `usc_dining` / `off_campus` | Ready |
| Hybrid day | Hall + cash snack | `mode=hybrid` | Ready |
| Search bar | Free-text | `GET /v1/search?q=` | Ready |
| 3 picks / meal | AI cards + Swap | `plan/day` ≤3 + `match_percent` | Ready |
| Swap rebalance | Day updates, cal delta | `plan/swap` + `rebalance_delta` | Ready |
| Clock times | 8:30 / 12:30 / … | `suggested_time` per period | Ready |
| Walk estimate | Minutes | `walk_minutes_estimate` (mi×20) | Ready |
| Daily rings | Targets + planned | `daily_targets` + `daily_planned` | Ready |
| Swipes / $ | Swipes + Dining Dollars | `spending` object | Ready |
| Card macros | Always show cal/protein | Known only; else `unavailable` | Partial |
| Week calendar | Multi-day | Stateless (`menu_date` only) | Gap |
| Account | Name / email store | None | Gap |
| Privacy | Privacy & data | None | FE-only |

## Wire sequence

1. Onboarding → `POST /v1/profile/targets` for rings  
2. Mode tab → `POST /v1/plan/day` (`usc_dining` / `off_campus` / `hybrid`)  
3. Render `periods[].recommendations` (`match_percent`, `why`, `suggested_time`)  
4. Swap → `POST /v1/plan/swap` (read `rebalance_delta`)  
5. Search → `GET /v1/search?q=`

## Still out of scope

Auth, real walking routes, inventing dish nutrition, multi-day persistence.

## Examples

- `data/menus/examples/plan_day_usc.json`  
- `data/menus/examples/plan_day_off_campus.json`  
- `data/menus/examples/plan_day_hybrid.json`  
- OpenAPI: `/docs`
