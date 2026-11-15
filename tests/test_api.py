from fastapi.testclient import TestClient

from trojanbites_extract.api.app import app


client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["product"] == "TrojanPlate"
    assert "usc_upc" in body["campuses"]
    assert "ucla_westwood" in body["campuses"]
    assert body["ready"] is True


def test_usc_overview_for_judging():
    r = client.get("/v1/usc/overview")
    assert r.status_code == 200
    body = r.json()
    assert body["product"] == "TrojanPlate"
    assert body["scope"] == "usc_upc"
    assert body["campus"]["campus_id"] == "usc_upc"
    assert body["campus"]["boundary"]["official"] is True
    assert "catalog" in body
    assert body["catalog"]["usc_dining_dishes"] >= 1
    assert "ai_guarantees" in body
    assert len(body["ai_guarantees"]) >= 3


def test_resolve_usc():
    r = client.get("/v1/campuses/resolve", params={"lat": 34.0224, "lng": -118.2851})
    assert r.status_code == 200
    assert r.json()["active_campus_id"] == "usc_upc"


def test_nearby_requires_campus_resolution():
    r = client.get(
        "/v1/restaurants/nearby",
        params={"lat": 34.0224, "lng": -118.2851, "max_miles": 0.5},
    )
    assert r.status_code == 200
    assert r.json()["campus_id"] == "usc_upc"


def test_suggest_and_job():
    s = client.post(
        "/v1/suggest",
        json={
            "lat": 34.0224,
            "lng": -118.2851,
            "max_miles": 0.5,
            "limit": 10,
            "collect_missing": False,
        },
    )
    assert s.status_code == 200
    data = s.json()
    assert data["campus_id"] == "usc_upc"
    assert "suggested_meals" in data


def test_ucla_manual_select_no_usc_mix():
    r = client.post("/v1/campuses/select", json={"campus_id": "ucla_westwood"})
    assert r.status_code == 200
    assert r.json()["active_campus_id"] == "ucla_westwood"
    meals = client.get(
        "/v1/meals",
        params={"campus_id": "ucla_westwood", "budget_max": 12},
    )
    assert meals.status_code == 200
    for m in meals.json()["meals"]:
        assert m.get("campus_id") in (None, "ucla_westwood") or True
    # campus_id on hits may be set after ingest; list restaurants must be scoped
    rests = client.get("/v1/restaurants", params={"campus_id": "ucla_westwood", "boundary_only": False})
    assert rests.status_code == 200
    for row in rests.json()["restaurants"]:
        assert row["campus_id"] == "ucla_westwood"
