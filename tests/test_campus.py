from trojanbites_extract.campus.registry import list_campuses, load_campus
from trojanbites_extract.campus.resolve import resolve_campus
from trojanbites_extract.jobs.ingestion import create_ingestion_job
from trojanbites_extract.query.filters import MealQuery, filter_meals
from trojanbites_extract.store.db import init_db, session_scope
from trojanbites_extract.store.models import Restaurant


def test_campuses_configured():
    ids = {c.campus_id for c in list_campuses()}
    assert "usc_upc" in ids
    assert "ucla_westwood" in ids
    ucla = load_campus("ucla_westwood")
    assert ucla.boundary_type == "search_radius"
    assert ucla.boundary_official is False
    usc = load_campus("usc_upc")
    assert usc.boundary_type == "official_patrol"
    assert usc.boundary_official is True


def test_resolve_usc_from_coordinates():
    result = resolve_campus(lat=34.0224, lng=-118.2851)
    assert result.status == "resolved"
    assert result.active_campus_id == "usc_upc"


def test_resolve_ucla_from_coordinates():
    result = resolve_campus(lat=34.0689, lng=-118.4452)
    assert result.status == "resolved"
    assert result.active_campus_id == "ucla_westwood"


def test_resolve_manual():
    result = resolve_campus(campus_id="ucla_westwood")
    assert result.status == "manual"
    assert result.active_campus_id == "ucla_westwood"


def test_no_silent_distant_campus():
    # Downtown LA-ish — may need confirmation or unresolved, must not auto-pick wrong campus silently as USC if far
    result = resolve_campus(lat=34.05, lng=-118.25)
    if result.status == "resolved":
        # If auto-selected, must be within auto range of that campus center
        assert result.active_campus_id is not None
        assert result.candidates
        assert result.candidates[0].distance_miles <= 2.0


def test_ucla_slice_and_campus_isolation(tmp_path, monkeypatch):
    db_url = f"sqlite:///{tmp_path / 'multi.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    from trojanbites_extract import settings as settings_mod

    settings_mod.get_settings.cache_clear()
    init_db(db_url)

    job = create_ingestion_job("ucla_westwood", run_async=False)
    assert job["status"] in {"completed", "partial"}
    assert job["result"]["menu_items_upserted"] >= 1

    with session_scope() as session:
        ucla_rows = (
            session.query(Restaurant).filter(Restaurant.campus_id == "ucla_westwood").all()
        )
        assert ucla_rows
        # Insert a fake USC restaurant and ensure meals don't leak across campuses
        from trojanbites_extract.store.upserts import replace_menu_for_restaurant, upsert_restaurant

        upsert_restaurant(
            session,
            {
                "restaurant_id": "usc_only_1",
                "campus_id": "usc_upc",
                "university_id": "usc",
                "name": "USC Only Spot",
                "lat": 34.0224,
                "lng": -118.2851,
                "boundary_status": "inside",
                "cuisines": ["american"],
                "categories": [],
                "menu_links": [],
                "business_status": "operational",
            },
        )
        replace_menu_for_restaurant(
            session,
            "usc_only_1",
            {
                "menu_items": [
                    {
                        "item_id": "usc_item_1",
                        "name": "USC Secret Bowl",
                        "variants": [
                            {"variant_id": "v1", "price": {"amount": 8, "currency": "USD"}}
                        ],
                        "dietary_claims": [
                            {
                                "claim": "vegetarian",
                                "raw_text": "Vegetarian",
                                "evidence_status": "restaurant_published",
                                "is_guarantee": False,
                            }
                        ],
                        "availability": {"status": "available", "meal_periods": ["lunch"]},
                        "nutrition": {
                            "nutrition_id": "n1",
                            "item_id": "usc_item_1",
                            "variant_id": "v1",
                            "evidence_status": "restaurant_published",
                            "serving_basis": "1",
                            "published": {
                                "calories_kcal": 400,
                                "protein_g": 20,
                                "carbohydrates_g": 40,
                                "fat_g": 10,
                                "fiber_g": 4,
                                "sugar_g": 5,
                                "sodium_mg": 500,
                            },
                        },
                    }
                ]
            },
        )
        ucla_hits = filter_meals(
            session,
            MealQuery(
                campus_id="ucla_westwood",
                budget_max=12,
                diet_claims_required=["vegetarian"],
                strict=True,
            ),
        )
        assert all(h.campus_id == "ucla_westwood" for h in ucla_hits)
        assert all(h.item_name != "USC Secret Bowl" for h in ucla_hits)
