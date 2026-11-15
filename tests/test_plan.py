from fastapi.testclient import TestClient

from trojanbites_extract.api.app import app
from trojanbites_extract.plan.engine import plan_day, swap_meal
from trojanbites_extract.plan.menus import load_off_campus_menu, load_usc_dining_menu

client = TestClient(app)


def test_usc_dining_snapshot_has_three_halls():
    data = load_usc_dining_menu()
    ids = {v["venue_id"] for v in data["venues"]}
    assert {"usc_village_dh", "usc_evk", "usc_parkside"} <= ids
    assert len(data["dishes"]) >= 15


def test_off_campus_curated_within_walk_pin():
    data = load_off_campus_menu()
    assert data["venues"]
    assert data["dishes"]
    assert data["metadata"]["default_max_miles"] == 0.3


def test_plan_usc_vegetarian_three_periods():
    plan = plan_day(
        {
            "nutrition_goal": "training_muscle",
            "dietary_preference": "vegetarian",
            "prefer_high_protein": True,
            "allergies": [],
        },
        {
            "mode": "usc_dining",
            "meal_periods": ["breakfast", "lunch", "dinner"],
            "meal_swipes_remaining": 3,
        },
    )
    assert plan["product"] == "TrojanPlate"
    assert plan["mode"] == "usc_dining"
    assert len(plan["periods"]) == 3
    for block in plan["periods"]:
        assert block["count"] <= 3
        assert block["count"] >= 1
        for rec in block["recommendations"]:
            labels = {x.lower() for x in rec["dietary_labels"]}
            assert "vegetarian" in labels or "vegan" in labels
            assert rec["price"]["model"] == "meal_swipe_ayce"


def test_plan_off_campus_budget_and_distance():
    plan = plan_day(
        {"nutrition_goal": "balanced", "dietary_preference": "vegetarian"},
        {
            "mode": "off_campus",
            "lat": 34.0224,
            "lng": -118.2851,
            "max_miles": 0.3,
            "budget_per_meal": 12,
            "budget_daily": 30,
            "preferred_cuisines": ["Italian"],
            "meal_periods": ["lunch", "dinner"],
        },
    )
    assert plan["mode"] == "off_campus"
    for block in plan["periods"]:
        for rec in block["recommendations"]:
            assert rec["distance_miles"] is None or rec["distance_miles"] <= 0.3
            amt = rec["price"]["amount"]
            if amt is not None:
                assert amt <= 12


def test_swap_locks_and_replans():
    profile = {"dietary_preference": "vegetarian", "nutrition_goal": "balanced"}
    situation = {
        "mode": "usc_dining",
        "meal_periods": ["breakfast", "lunch", "dinner"],
        "meal_swipes_remaining": 3,
    }
    first = plan_day(profile, situation)
    lunch = next(p for p in first["periods"] if p["meal_period"] == "lunch")
    assert lunch["recommendations"]
    chosen = lunch["recommendations"][0]["dish_id"]
    # pick alternate if available
    alt = (
        lunch["recommendations"][1]["dish_id"]
        if len(lunch["recommendations"]) > 1
        else chosen
    )
    second = swap_meal(profile, situation, [], "lunch", alt, "selected")
    locked_lunch = next(p for p in second["periods"] if p["meal_period"] == "lunch")
    assert locked_lunch["locked"] is True
    assert locked_lunch["recommendations"][0]["dish_id"] == alt


def test_allergy_hard_filter():
    plan = plan_day(
        {
            "dietary_preference": None,
            "allergies": ["sesame"],
            "nutrition_goal": "balanced",
        },
        {
            "mode": "usc_dining",
            "meal_periods": ["lunch"],
        },
    )
    for rec in plan["periods"][0]["recommendations"]:
        allergens = " ".join(rec.get("allergens_published") or []).lower()
        assert "sesame" not in allergens


def test_api_plan_and_frontend():
    r = client.get("/")
    assert r.status_code == 200
    assert "TrojanPlate" in r.text

    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["product"] == "TrojanPlate"

    r = client.post(
        "/v1/plan/day",
        json={
            "profile": {"dietary_preference": "vegan", "nutrition_goal": "balanced"},
            "situation": {"mode": "usc_dining", "meal_swipes_remaining": 2},
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "usc_dining"
    assert body["periods"]

    ov = client.get("/v1/usc/overview")
    assert ov.status_code == 200
    assert ov.json()["product"] == "TrojanPlate"
    assert ov.json()["catalog"]["usc_dining_dishes"] >= 1
