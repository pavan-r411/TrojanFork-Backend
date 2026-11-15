# Trojan Fork Backend

Multi-university restaurant / menu / nutrition extraction + recommendation API.

- Architecture: [`ARCHITECTURE.md`](ARCHITECTURE.md)
- Extraction blueprint: [`extraction_framework.md`](extraction_framework.md)
- Status (implemented / tested / deployed / blocked): [`STATUS.md`](STATUS.md)

## Setup

```bash
cd TrojanFork-Backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # add keys when available
```

## Quick start

```bash
trojanbites init-db
trojanbites import-pilot --skip-move
trojanbites ingest-campus usc_upc --sync
trojanbites ingest-campus ucla_westwood --sync

trojanbites resolve-campus --lat 34.0224 --lng -118.2851
trojanbites query --campus ucla_westwood --budget-max 12 --diet vegetarian

uvicorn trojanbites_extract.api.app:app --reload --port 8000
```

Open http://127.0.0.1:8000/docs

## Key API

| Endpoint | Use |
|---|---|
| `GET /v1/campuses/resolve?lat=&lng=` | Detect campus |
| `POST /v1/campuses/select` | Confirm campus |
| `GET /v1/restaurants/nearby` | Nearby restaurants |
| `POST /v1/suggest` | Recommendations + optional background job |
| `POST /v1/ingestion/jobs` | Start campus collection |
| `GET /health` | Readiness |

## Tests

```bash
pytest -q
```

## Notes

- Missing calories stay `null` (estimation off).
- Menu prices exclude tax/fees.
- Distance is straight-line miles unless Routes API is added later.
- Do not commit `.env`.
