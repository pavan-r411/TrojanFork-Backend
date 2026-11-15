"""Off-campus breakfast may use a name match, and that match stays unverified."""
from dataclasses import asdict, replace
from datetime import date

from trojanbites_extract.recommend import frontend
from trojanbites_extract.recommend.service import RecommendationResult
from trojanbites_extract.query.filters import MealHit


def hit(**kwargs):
    base = MealHit(
        item_id="food",
        restaurant_id="venue",
        restaurant_name="Live Venue",
        item_name="Live tofu bowl",
        price_amount=11,
        currency="USD",
        published_calories_kcal=None,
        published_protein_g=None,
        match_class="strict",
        uncertain_reasons=[],
        distance_miles=0.2,
    )
    return replace(base, **kwargs)


def plan(monkeypatch, meals, sources):
    monkeypatch.setattr(frontend, "_offcampus", lambda body: (meals, sources, []))
    monkeypatch.setattr(
        frontend,
        "select_meals",
        lambda hits, *a, **kw: RecommendationResult(
            provider="openai", status="completed", meals=[asdict(item) for item in hits[:3]]
        ),
    )
    return frontend.daily_plan(
        frontend.PlanRequest(
            mode="off_campus",
            date=date(2026, 11, 15),
            profile={"allergies": ["peanut"]},
            context={"origin": {"lat": 34.0224, "lng": -118.2851}},
        )
    )


def test_unlabeled_breakfast_name_is_included_as_unverified(monkeypatch):
    meals = [hit(item_id="pan", item_name="Blueberry Pancakes"), hit(item_id="tofu", item_name="Live tofu bowl")]
    sources = [
        {
            "item_id": "pan",
            "menu_url": "https://venue.test/menu",
            "meal_periods": [],
            "evidence": "Blueberry Pancakes",
            "place_id": "place-pan",
            "lat": 34.021,
            "lng": -118.286,
            "address": "1 Breakfast Ave",
        },
        {"item_id": "tofu", "menu_url": "https://venue.test/menu", "meal_periods": [], "evidence": "Live tofu bowl"},
    ]
    data = plan(monkeypatch, meals, sources)
    breakfast = data["slots"][0]
    assert [card["meal_title"] for card in breakfast["recommendations"]] == ["Blueberry Pancakes"]
    card = breakfast["recommendations"][0]
    assert card["meal_period_evidence"] == "inferred"
    assert card["nutrition"]["calories"] is None
    assert card["nutrition"]["display_status"] == "Nutrition unavailable"
    assert "unverified" in card["reason"].lower()
    assert "unverified" in breakfast["availability_note"].lower()
    assert breakfast["empty_state"]["reason_code"] is None
    assert card["directions"]["available"] is True
    assert card["directions"]["destination"]["place_id"] == "place-pan"
    assert card["directions"]["destination"]["lat"] == 34.021
    assert card["directions"]["destination"]["address"] == "1 Breakfast Ave"
    assert "travelmode=walking" in (card["directions_url"] or "")
    titles = [card["meal_title"] for slot in data["slots"] for card in slot["recommendations"]]
    assert titles.count("Blueberry Pancakes") == 1
    assert "Live tofu bowl" in titles
    assert "Live tofu bowl" not in [card["meal_title"] for card in breakfast["recommendations"]]


def test_explicit_lunch_label_is_not_reclassified_as_breakfast(monkeypatch):
    meals = [hit(item_id="pan", item_name="Blueberry Pancakes")]
    sources = [{"item_id": "pan", "menu_url": "https://venue.test/menu", "meal_periods": ["lunch"], "evidence": "Blueberry Pancakes"}]
    data = plan(monkeypatch, meals, sources)
    breakfast = data["slots"][0]
    assert breakfast["recommendations"] == []
    state = breakfast["empty_state"]
    assert state["reason_code"] == "NO_BREAKFAST_MENU_PUBLISHED"
    assert state["diagnostics"]["allergies_applied"] == ["peanut"]
    assert state["diagnostics"]["allergies_kept"] is True
    labels = " ".join(action["label"].lower() for action in state["actions"])
    assert "allerg" not in labels and "remove" not in labels
    lunch = data["slots"][1]["recommendations"]
    assert lunch and lunch[0]["meal_period_evidence"] == "labeled"
    assert lunch[0]["meal_title"] == "Blueberry Pancakes"


def test_plain_unlabeled_dish_still_does_not_count_as_breakfast(monkeypatch):
    data = plan(
        monkeypatch,
        [hit()],
        [{"item_id": "food", "menu_url": "https://venue.test/menu", "meal_periods": []}],
    )
    assert data["slots"][0]["recommendations"] == []
    assert "breakfast menu" in data["slots"][0]["availability_note"]
    assert data["slots"][0]["empty_state"]["reason_code"] == "NO_BREAKFAST_MENU_PUBLISHED"
