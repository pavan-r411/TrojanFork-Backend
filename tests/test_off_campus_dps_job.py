from datetime import datetime, timezone

from trojanbites_extract.campus.registry import clear_campus_cache
from trojanbites_extract.discovery.base import DiscoveryCandidate
from trojanbites_extract.geocoding.adapter import GeocodeResult
from trojanbites_extract.jobs import off_campus_dps as jobmod
from trojanbites_extract.store import db as dbmod
from trojanbites_extract.store.db import init_db, session_scope
from trojanbites_extract.store.models import MenuItem, Restaurant


class _FakeArtifact:
    def __init__(self, ok=True, path=None, content_type="text/html", error=None, url="https://good.test/menu"):
        self.ok = ok
        self.bytes_path = path
        self.content_type = content_type
        self.error = error
        self.url = url
        self.final_url = url
        self.content_hash = "abc"
        self.http_status = 200 if ok else 404
        self.robots_status = "allowed"
        self.fetched_at = datetime.utcnow()


def test_off_campus_dps_job_end_to_end(tmp_path, monkeypatch):
    clear_campus_cache()
    db_path = tmp_path / "offcampus.db"
    db_url = f"sqlite:///{db_path}"

    from trojanbites_extract import settings as settings_mod

    settings_mod.get_settings.cache_clear()
    monkeypatch.setenv("DATABASE_URL", db_url)
    settings_mod.get_settings.cache_clear()
    settings = settings_mod.get_settings()
    object.__setattr__(settings, "database_url", db_url)
    object.__setattr__(settings, "google_maps_api_key", "test-key")
    object.__setattr__(settings, "gemini_api_key", "test-gemini")

    dbmod.SessionLocal = None
    init_db(db_url)

    html = tmp_path / "menu.html"
    html.write_text(
        "<html><body><h1>Menu</h1><p>Veggie Bowl $11.50</p><p>Calories: 520 Protein: 22g</p></body></html>",
        encoding="utf-8",
    )

    cand = DiscoveryCandidate(
        provider="google_places",
        provider_place_id="places/ChIJtestVillageBowl",
        display_name="Village Test Bowl",
        formatted_address="3201 S Hoover St, Los Angeles, CA 90007",
        website_uri="https://good.test/",
        business_status="OPERATIONAL",
        raw_types=["restaurant"],
        lat=34.0256,
        lng=-118.2852,
    )

    monkeypatch.setattr(jobmod, "_discover_candidates", lambda campus, max_tiles=12: [cand])

    class FakeGeo:
        def geocode(self, address):
            return GeocodeResult(
                lat=34.0256,
                lng=-118.2852,
                provider="google_geocoding_api",
                geocoded_at=datetime.now(timezone.utc),
                precision="ROOFTOP",
                formatted_address=address,
            )

    monkeypatch.setattr(jobmod, "GoogleGeocoder", FakeGeo)

    class FakeFinder:
        def find_menu_links(self, **kwargs):
            return (
                {
                    "official_website": "https://good.test/",
                    "menu_urls": [
                        {"url": "https://good.test/menu", "kind": "html_menu", "confidence": "high"}
                    ],
                    "ordering_urls": [],
                    "nutrition_urls": [],
                    "attempts": ["mocked_search"],
                    "notes": None,
                },
                {"provider": "gemini", "operation": "gemini_menu_find"},
            )

    class FakeExtractor:
        def extract(self, doc, **kwargs):
            return (
                {
                    "menu_items": [
                        {
                            "name": "Veggie Bowl",
                            "description": None,
                            "category": "Bowls",
                            "variants": [
                                {
                                    "size_label": None,
                                    "serving_label": None,
                                    "price": {"amount": 11.5, "currency": "USD"},
                                    "addons": [],
                                }
                            ],
                            "dietary_claims": [],
                            "allergen_claims": [],
                            "nutrition": {
                                "evidence_status": "restaurant_published",
                                "published": {
                                    "calories_kcal": 520,
                                    "protein_g": 22,
                                    "carbohydrates_g": None,
                                    "fat_g": None,
                                },
                            },
                        }
                    ],
                    "conflicts": [],
                    "ambiguities": [],
                },
                {"provider": "gemini"},
            )

    monkeypatch.setattr(jobmod, "GeminiMenuFinder", lambda: FakeFinder())
    monkeypatch.setattr(jobmod, "GeminiExtractor", lambda: FakeExtractor())
    monkeypatch.setattr(jobmod, "SafeFetcher", lambda: SimpleFetcher(html))

    out = jobmod.create_off_campus_dps_job("usc_upc", batch_limit=1, run_async=False, force=True)
    assert out["status"] in {"completed", "partial"}, out
    result = out["result"]
    assert result["restaurants_upserted"] == 1
    assert result["dishes_extracted"] >= 1
    assert result["off_campus_dps_matched"] == 1

    with session_scope() as session:
        rows = (
            session.query(Restaurant)
            .filter(Restaurant.restaurant_id.like("rest_offcampus_%"))
            .all()
        )
        assert len(rows) == 1
        assert (rows[0].service_json or {}).get("location_zone") == "off_campus_dps"
        assert (
            session.query(MenuItem)
            .filter(MenuItem.restaurant_id == rows[0].restaurant_id)
            .count()
            >= 1
        )


class SimpleFetcher:
    def __init__(self, path):
        self.path = path

    def fetch(self, url):
        return _FakeArtifact(ok=True, path=self.path, url=url)
