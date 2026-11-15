# Off-campus DPS restaurant pipeline

Owns businesses **outside** the USC University Park Campus academic core and **inside** the USC DPS UPC patrol area. Campus hospitality dining halls (EVK, Parkside, Village Dining Hall) stay with the on-campus teammate pipeline.

## Boundaries (official sources)

| Layer | ID | Source |
|---|---|---|
| DPS patrol | `usc_upc_dps` / `v2025-01` | https://dps.usc.edu/patrol/ · [UPC PDF](https://dps.usc.edu/wp-content/uploads/2025/01/UPC-Patrol-Area.pdf) |
| Campus academic core | `usc_upc_campus` / `v2025-01` | [LA City USC UPC Specific Plan](https://planning.lacity.gov/EIR/USC/SpecificPlans/USC%20Specific%20Plan%20(as%20approved%20by%20City%20Council).pdf) · [USC FPM RFQ](https://fpm.usc.edu/wp-content/uploads/2023/06/RFQ-Contractors-060123_FINAL.pdf) |

Both GeoJSON files are **approximations** (`approximation: true`). USC Village commercial is **outside** the campus-core polygon so Village retail is ingested here. Village Dining Hall is still teammate-owned via hospitality seed rules.

Configurable per campus in `config/campuses/<campus_id>.yaml` (`boundary`, `campus_boundary`, `patrol_boundary`, `pipeline_ownership`, `discovery.off_campus_dps`).

## Credentials (never commit)

Required in backend `.env`:

- `GOOGLE_MAPS_API_KEY` — Places API (New) + Geocoding
- `GEMINI_API_KEY` — menu URL discovery (Google Search grounding) + menu extraction

Optional: `ANTHROPIC_API_KEY` for other extract paths; not required for this job.

## Run (small pilot batch)

```bash
cd TrojanFork-Backend
source .venv/bin/activate
trojanbites init-db
# First live batch (default limit=5 from campus config)
trojanbites ingest-off-campus-dps --campus usc_upc --limit 3 --force
# Inspect
trojanbites list-restaurants
trojanbites export
```

Resume / status:

```bash
trojanbites ingest-off-campus-dps --job-id <job_id>
```

## Pipeline steps

1. Tile DPS polygon → Places Nearby Search (store Place IDs only for membership).
2. Independently geocode Places address hints via Geocoding API (PiP must not use Places lat/lng).
3. Classify: inside DPS ∧ outside campus core ∧ not hospitality → `off_campus_dps`.
4. Deduplicate by Place ID and name against existing teammate/pilot rows.
5. Gemini + Google Search grounding → official website / menu / nutrition / ordering URLs.
6. SafeFetcher follows robots/size/timeout rules; HTML nav + PDF links inspected.
7. Deterministic parse + Gemini evidence-only extraction → validate → SQLite upsert.
8. Missing menus recorded with attempt log; job continues.

## Honesty / ToS

- Unknown prices/nutrition stay `null`.
- No scraping of Google Maps HTML result pages.
- Places display fields are runtime hints; export coordinates come from geocoding.
- AI nutrition estimates (if ever enabled elsewhere) stay separate from restaurant-published values.
