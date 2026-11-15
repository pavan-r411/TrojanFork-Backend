from trojanbites_extract.query.filters import haversine_miles, nearby_restaurants
from trojanbites_extract.store.db import init_db, session_scope
from trojanbites_extract.store.upserts import upsert_restaurant


def test_haversine_short_distance():
    # ~0.3 mi east-west near USC
    d = haversine_miles(34.0224, -118.2851, 34.0224, -118.2800)
    assert 0.2 < d < 0.4


def test_nearby_filters_by_radius(tmp_path, monkeypatch):
    db_url = f"sqlite:///{tmp_path / 'n.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    from trojanbites_extract import settings as settings_mod

    settings_mod.get_settings.cache_clear()
    init_db(db_url)
    with session_scope() as session:
        upsert_restaurant(
            session,
            {
                "restaurant_id": "near_1",
                "name": "Near Spot",
                "lat": 34.0224,
                "lng": -118.2851,
                "boundary_status": "inside",
                "boundary_id": "usc_upc_dps",
                "boundary_version": "v2025-01",
                "cuisines": ["american"],
                "categories": [],
                "menu_links": [],
                "business_status": "operational",
            },
        )
        upsert_restaurant(
            session,
            {
                "restaurant_id": "far_1",
                "name": "Far Spot",
                "lat": 34.05,
                "lng": -118.25,
                "boundary_status": "inside",
                "boundary_id": "usc_upc_dps",
                "boundary_version": "v2025-01",
                "cuisines": ["american"],
                "categories": [],
                "menu_links": [],
                "business_status": "operational",
            },
        )
        rows = nearby_restaurants(
            session, user_lat=34.0224, user_lng=-118.2851, max_distance_miles=0.3
        )
    assert [r.restaurant_id for r in rows] == ["near_1"]
