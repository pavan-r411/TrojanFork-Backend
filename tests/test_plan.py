from fastapi.testclient import TestClient

from trojanbites_extract.api.app import app
from trojanbites_extract.plan.engine import plan_day, swap_meal
from trojanbites_extract.plan.menus import load_off_campus_menu, load_usc_dining_menu
from trojanbites_extract.plan.search import search_menus
from trojanbites_extract.plan.targets import estimate_daily_targets, normalize_nutrition_goal

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


def test_goal_aliases_and_targets():
    assert normalize_nutrition_goal("Build muscle") == "training_muscle"
    assert normalize_nutrition_goal("lose_body_fat") == "gradual_loss"
    missing = estimate_daily_targets({"nutrition_goal": "balanced"})
    assert missing["confidence"] == "unavailable"
    est = estimate_daily_targets(
        {
            "nutrition_goal": "build_muscle",
            "height_cm": 173,
            "weight_kg": 68,
            "activity_level": "moderate",
            "prefer_high_protein": True,
        }
    )
    assert est["confidence"] == "estimated"
    assert est["targets"]["calories_kcal"] > 1000
    assert est["targets"]["protein_g"] > 50


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
    assert "daily_targets" in plan
    assert "spending" in plan
    assert len(plan["periods"]) == 3
    for block in plan["periods"]:
        assert block["count"] <= 3
        assert block["count"] >= 1
        assert block.get("suggested_time")
        for rec in block["recommendations"]:
            labels = {x.lower() for x in rec["dietary_labels"]}
            assert "vegetarian" in labels or "vegan" in labels
            assert rec["price"]["model"] == "meal_swipe_ayce"
            assert 55 <= rec["match_percent"] <= 99
            assert rec.get("protein_g") is not None
            assert rec["nutrition"]["confidence"] in {"estimated", "confirmed"}


def test_min_protein_filter_and_daily_planned_protein():
    plan = plan_day(
        {"nutrition_goal": "build_muscle", "prefer_high_protein": True},
        {
            "mode": "usc_dining",
            "meal_periods": ["lunch"],
            "min_protein": 20,
            "allow_estimated_nutrition": True,
        },
    )
    for rec in plan["periods"][0]["recommendations"]:
        assert rec["protein_g"] is not None
        assert rec["protein_g"] >= 20
    assert plan["daily_planned"]["protein_g"] is not None
    assert plan["daily_planned"]["protein_g"] >= 20


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
            assert rec.get("walk_minutes_estimate") is None or rec["walk_minutes_estimate"] >= 1
            amt = rec["price"]["amount"]
            if amt is not None:
                assert amt <= 12


def test_pescatarian_excludes_obvious_meat():
    plan = plan_day(
        {"dietary_preference": "pescatarian", "nutrition_goal": "balanced"},
        {"mode": "usc_dining", "meal_periods": ["lunch", "dinner"]},
    )
    for block in plan["periods"]:
        for rec in block["recommendations"]:
            name = (rec.get("name") or "").lower()
            # turkey burger / chicken should not appear
            assert "turkey" not in name
            assert "chicken" not in name or "fish" in name


def test_hybrid_mode_main_and_snack():
    plan = plan_day(
        {"dietary_preference": "vegetarian", "nutrition_goal": "feel_balanced"},
        {
            "mode": "hybrid",
            "meal_swipes_remaining": 3,
            "budget_per_meal": 15,
            "budget_daily": 25,
            "dining_dollars_remaining": 10,
            "lat": 34.0224,
            "lng": -118.2851,
            "max_miles": 0.3,
        },
    )
    assert plan["mode"] == "hybrid"
    periods = {p["meal_period"]: p for p in plan["periods"]}
    assert "breakfast" in periods and "snack" in periods
    for meal in ("breakfast", "lunch", "dinner"):
        if periods[meal]["recommendations"]:
            assert periods[meal]["recommendations"][0]["price"]["model"] == "meal_swipe_ayce"


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
    alt = (
        lunch["recommendations"][1]["dish_id"]
        if len(lunch["recommendations"]) > 1
        else lunch["recommendations"][0]["dish_id"]
    )
    second = swap_meal(profile, situation, [], "lunch", alt, "selected")
    locked_lunch = next(p for p in second["periods"] if p["meal_period"] == "lunch")
    assert locked_lunch["locked"] is True
    assert locked_lunch["recommendations"][0]["dish_id"] == alt
    assert "rebalance_delta" in second
    # When macros unavailable, delta fields may be null — still present
    assert second["rebalance_delta"] is not None
    assert "calories_kcal" in second["rebalance_delta"]


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


def test_search_menus():
    hits = search_menus("tofu", mode="usc_dining", limit=10)
    assert hits["count"] >= 1
    assert all("tofu" in (r["name"] or "").lower() or "tofu" in str(r).lower() for r in hits["results"])


def test_api_plan_endpoints():
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
    assert "match_percent" in body["periods"][0]["recommendations"][0]

    t = client.post(
        "/v1/profile/targets",
        json={
            "nutrition_goal": "lose_body_fat",
            "height_cm": 170,
            "weight_kg": 70,
            "activity_level": "light",
        },
    )
    assert t.status_code == 200
    assert t.json()["confidence"] == "estimated"

    s = client.get("/v1/search", params={"q": "bowl", "mode": "all"})
    assert s.status_code == 200
    assert s.json()["count"] >= 1

    ov = client.get("/v1/usc/overview")
    assert ov.status_code == 200
    assert ov.json()["product"] == "TrojanPlate"
    assert ov.json()["catalog"]["usc_dining_dishes"] >= 1
    assert "ui" not in ov.json().get("demo", {})
