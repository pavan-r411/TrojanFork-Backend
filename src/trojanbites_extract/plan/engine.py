from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from trojanbites_extract.plan.menus import load_off_campus_menu, load_usc_dining_menu
from trojanbites_extract.query.filters import DEFAULT_MAX_DISTANCE_MILES, haversine_miles

Mode = Literal["usc_dining", "off_campus"]
MealPeriod = Literal["breakfast", "lunch", "dinner", "snack"]

DEFAULT_PERIODS: list[MealPeriod] = ["breakfast", "lunch", "dinner"]


@dataclass
class StudentProfile:
    nutrition_goal: str = "balanced"
    dietary_preference: str | None = None  # vegetarian, vegan, etc.
    allergies: list[str] = field(default_factory=list)
    exclusions: list[str] = field(default_factory=list)
    preferred_foods: list[str] = field(default_factory=list)
    prefer_high_protein: bool = False
    age_range: str | None = None
    activity_level: str | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    goal_weight_kg: float | None = None


@dataclass
class DaySituation:
    mode: Mode
    meal_periods: list[MealPeriod] = field(default_factory=lambda: list(DEFAULT_PERIODS))
    lat: float | None = 34.0224
    lng: float | None = -118.2851
    max_miles: float = DEFAULT_MAX_DISTANCE_MILES
    preferred_cuisines: list[str] = field(default_factory=list)
    budget_per_meal: float | None = None
    budget_daily: float | None = None
    meal_swipes_remaining: int | None = None
    dining_dollars_remaining: float | None = None
    include_snacks: bool = False
    menu_date: str | None = None
    ranking_priority: str = "balanced"  # nutrition | affordability | cuisine | convenience


@dataclass
class LockedChoice:
    meal_period: MealPeriod
    dish_id: str
    status: Literal["selected", "eaten", "locked"] = "selected"


def _norm(s: str) -> str:
    return s.strip().lower().replace("-", "_").replace(" ", "_")


def _diet_ok(dish: dict[str, Any], preference: str | None) -> bool:
    if not preference:
        return True
    pref = _norm(preference)
    labels = {_norm(x) for x in (dish.get("dietary_labels") or [])}
    if pref in labels:
        return True
    # vegan satisfies vegetarian request only one way
    if pref == "vegetarian" and "vegan" in labels:
        return True
    if pref in {"halal", "halal_friendly"} and (
        "halal_friendly" in labels or "halal" in labels
    ):
        return True
    return False


def _allergy_hit(dish: dict[str, Any], allergies: list[str]) -> str | None:
    published = " ".join(str(a).lower() for a in (dish.get("allergens_published") or []))
    text = " ".join(
        [
            published,
            str(dish.get("name") or "").lower(),
            str(dish.get("description") or "").lower(),
            " ".join(str(x).lower() for x in (dish.get("ingredients_published") or [])),
        ]
    )
    for a in allergies:
        key = a.strip().lower()
        if not key:
            continue
        if key in text or key in published:
            return key
    return None


def _exclusion_hit(dish: dict[str, Any], exclusions: list[str]) -> str | None:
    text = " ".join(
        [
            str(dish.get("name") or "").lower(),
            str(dish.get("description") or "").lower(),
            " ".join(str(x).lower() for x in (dish.get("ingredients_published") or [])),
        ]
    )
    for ex in exclusions:
        key = ex.strip().lower()
        if key and key in text:
            return key
    return None


def _protein_g(dish: dict[str, Any]) -> float | None:
    nut = (dish.get("nutrition") or {}).get("published") or {}
    if isinstance(nut, dict) and nut.get("protein_g") is not None:
        try:
            return float(nut["protein_g"])
        except (TypeError, ValueError):
            return None
    return None


def _calories(dish: dict[str, Any]) -> float | None:
    nut = (dish.get("nutrition") or {}).get("published") or {}
    if isinstance(nut, dict) and nut.get("calories_kcal") is not None:
        try:
            return float(nut["calories_kcal"])
        except (TypeError, ValueError):
            return None
    return None


def _distance(dish: dict[str, Any], lat: float | None, lng: float | None) -> float | None:
    if lat is None or lng is None:
        return None
    dlat, dlng = dish.get("lat"), dish.get("lng")
    if dlat is None or dlng is None:
        return None
    return haversine_miles(lat, lng, float(dlat), float(dlng))


def _load_dishes(situation: DaySituation) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if situation.mode == "usc_dining":
        catalog = load_usc_dining_menu(situation.menu_date)
        dishes = list(catalog.get("dishes") or [])
        return dishes, catalog
    catalog = load_off_campus_menu()
    dishes = list(catalog.get("dishes") or [])
    return dishes, catalog


def _eligible(
    dish: dict[str, Any],
    profile: StudentProfile,
    situation: DaySituation,
    period: MealPeriod,
    remaining_budget: float | None,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    periods = dish.get("meal_periods") or []
    if period not in periods:
        return False, ["wrong_meal_period"]

    if not _diet_ok(dish, profile.dietary_preference):
        return False, ["diet_mismatch"]

    hit = _allergy_hit(dish, profile.allergies)
    if hit:
        return False, [f"allergy:{hit}"]

    ex = _exclusion_hit(dish, profile.exclusions)
    if ex:
        return False, [f"exclusion:{ex}"]

    if situation.mode == "off_campus":
        dist = _distance(dish, situation.lat, situation.lng)
        if dist is None:
            return False, ["missing_coordinates"]
        if dist > situation.max_miles:
            return False, ["too_far"]
        price = dish.get("price_amount")
        cap = situation.budget_per_meal
        if remaining_budget is not None and cap is not None:
            cap = min(cap, remaining_budget)
        elif remaining_budget is not None:
            cap = remaining_budget
        if cap is not None:
            if price is None:
                return False, ["price_unknown_hard_budget"]
            if float(price) > float(cap):
                return False, ["over_budget"]

    return True, reasons


def _score(
    dish: dict[str, Any],
    profile: StudentProfile,
    situation: DaySituation,
    used_venues: set[str],
    used_names: set[str],
) -> tuple[float, list[str]]:
    score = 50.0
    why: list[str] = []

    labels = {_norm(x) for x in (dish.get("dietary_labels") or [])}
    if profile.dietary_preference and _diet_ok(dish, profile.dietary_preference):
        score += 18
        why.append(f"Matches {profile.dietary_preference} preference")

    if profile.prefer_high_protein or "training" in _norm(profile.nutrition_goal):
        if "high_protein" in labels:
            score += 12
            why.append("Labeled high-protein on the menu")
        prot = _protein_g(dish)
        if prot is not None:
            score += min(prot / 5.0, 15)
            why.append(f"Published protein {prot:g}g")

    if "balanced" in _norm(profile.nutrition_goal):
        score += 4
        why.append("Fits a balanced daily plate")

    if situation.mode == "off_campus" and situation.preferred_cuisines:
        cuisines = " ".join(_norm(c) for c in (dish.get("cuisines") or []))
        matched = [
            c
            for c in situation.preferred_cuisines
            if _norm(c) in cuisines or _norm(c).rstrip("s") in cuisines
        ]
        if matched:
            score += 14
            why.append(f"Cuisine match: {', '.join(matched)}")
        elif situation.ranking_priority == "cuisine":
            score -= 8

    if situation.mode == "off_campus":
        price = dish.get("price_amount")
        if price is not None and situation.budget_per_meal is not None:
            headroom = float(situation.budget_per_meal) - float(price)
            if headroom >= 0:
                score += min(headroom, 10)
                why.append(f"${price:g} within ${situation.budget_per_meal:g} meal budget")
        dist = _distance(dish, situation.lat, situation.lng)
        if dist is not None:
            score += max(0, 10 - dist * 20)
            why.append(f"{dist:.2f} mi walk (straight-line)")
    else:
        why.append(
            f"Available at {dish.get('venue_name')} with a meal swipe (AYCE — no per-dish price)"
        )
        if situation.meal_swipes_remaining is not None:
            why.append(f"{situation.meal_swipes_remaining} swipe(s) remaining today")

    for pref in profile.preferred_foods:
        if pref and pref.lower() in str(dish.get("name") or "").lower():
            score += 8
            why.append(f"Includes preferred food “{pref}”")

    venue_id = str(dish.get("venue_id") or "")
    if venue_id and venue_id in used_venues:
        score -= 6  # variety across halls/venues
    name = _norm(str(dish.get("name") or ""))
    if name in used_names:
        score -= 20

    nut = dish.get("nutrition") or {}
    conf = nut.get("confidence") or "unavailable"
    if conf == "unavailable":
        why.append("Nutrition figures unavailable from source — not estimated")

    if not why:
        why.append("Eligible under your hard constraints")
    return score, why


def _recommend_period(
    dishes: list[dict[str, Any]],
    profile: StudentProfile,
    situation: DaySituation,
    period: MealPeriod,
    remaining_budget: float | None,
    used_venues: set[str],
    used_names: set[str],
    limit: int = 3,
) -> dict[str, Any]:
    scored: list[tuple[float, dict[str, Any], list[str]]] = []
    rejected_notes: list[str] = []
    for dish in dishes:
        ok, reasons = _eligible(dish, profile, situation, period, remaining_budget)
        if not ok:
            continue
        s, why = _score(dish, profile, situation, used_venues, used_names)
        scored.append((s, dish, why))

    scored.sort(key=lambda t: t[0], reverse=True)
    # unique dishes
    picks: list[dict[str, Any]] = []
    seen: set[str] = set()
    for s, dish, why in scored:
        did = str(dish.get("dish_id"))
        if did in seen:
            continue
        seen.add(did)
        nut = dish.get("nutrition") or {}
        dist = _distance(dish, situation.lat, situation.lng)
        picks.append(
            {
                "rank": len(picks) + 1,
                "score": round(s, 2),
                "dish_id": dish.get("dish_id"),
                "name": dish.get("name"),
                "venue_id": dish.get("venue_id"),
                "venue_name": dish.get("venue_name"),
                "meal_period": period,
                "description": dish.get("description"),
                "dietary_labels": dish.get("dietary_labels") or [],
                "allergens_published": dish.get("allergens_published") or [],
                "allergens_note": (
                    "Allergens as published; cross-contact may occur. "
                    "Not a medical guarantee."
                ),
                "price": {
                    "amount": dish.get("price_amount"),
                    "currency": dish.get("currency") or "USD",
                    "model": dish.get("payment_model")
                    or (
                        "meal_swipe_ayce"
                        if situation.mode == "usc_dining"
                        else "cash_card"
                    ),
                    "note": (
                        "Residential dining visit uses a meal swipe / AYCE — "
                        "no per-dish purchase price."
                        if situation.mode == "usc_dining"
                        else "Menu price excludes tax and fees."
                    ),
                },
                "nutrition": {
                    "confidence": nut.get("confidence") or "unavailable",
                    "published": nut.get("published"),
                    "protein_g": _protein_g(dish),
                    "calories_kcal": _calories(dish),
                },
                "distance_miles": None if dist is None else round(dist, 3),
                "distance_metric": "haversine_miles_straight_line",
                "why": why[:4],
            }
        )
        if len(picks) >= limit:
            break

    if len(picks) < limit:
        rejected_notes.append(
            f"Only {len(picks)} option(s) met hard constraints for {period}; "
            "not inventing fillers. Try relaxing cuisine, budget, or diet filters."
        )

    return {
        "meal_period": period,
        "recommendations": picks,
        "count": len(picks),
        "notes": rejected_notes,
    }


def _profile_from_dict(data: dict[str, Any] | None) -> StudentProfile:
    data = data or {}
    return StudentProfile(
        nutrition_goal=str(data.get("nutrition_goal") or "balanced"),
        dietary_preference=data.get("dietary_preference"),
        allergies=list(data.get("allergies") or []),
        exclusions=list(data.get("exclusions") or []),
        preferred_foods=list(data.get("preferred_foods") or []),
        prefer_high_protein=bool(
            data.get("prefer_high_protein")
            or "training" in str(data.get("nutrition_goal") or "").lower()
            or "muscle" in str(data.get("nutrition_goal") or "").lower()
        ),
        age_range=data.get("age_range"),
        activity_level=data.get("activity_level"),
        height_cm=data.get("height_cm"),
        weight_kg=data.get("weight_kg"),
        goal_weight_kg=data.get("goal_weight_kg"),
    )


def _situation_from_dict(data: dict[str, Any]) -> DaySituation:
    periods = data.get("meal_periods") or list(DEFAULT_PERIODS)
    if data.get("include_snacks") and "snack" not in periods:
        periods = list(periods) + ["snack"]
    return DaySituation(
        mode=data["mode"],
        meal_periods=list(periods),
        lat=data.get("lat", 34.0224),
        lng=data.get("lng", -118.2851),
        max_miles=float(data.get("max_miles") or DEFAULT_MAX_DISTANCE_MILES),
        preferred_cuisines=list(data.get("preferred_cuisines") or []),
        budget_per_meal=data.get("budget_per_meal"),
        budget_daily=data.get("budget_daily"),
        meal_swipes_remaining=data.get("meal_swipes_remaining"),
        dining_dollars_remaining=data.get("dining_dollars_remaining"),
        include_snacks=bool(data.get("include_snacks")),
        menu_date=data.get("menu_date"),
        ranking_priority=str(data.get("ranking_priority") or "balanced"),
    )


def plan_day(
    profile: dict[str, Any] | StudentProfile,
    situation: dict[str, Any] | DaySituation,
    locked: list[dict[str, Any] | LockedChoice] | None = None,
) -> dict[str, Any]:
    prof = profile if isinstance(profile, StudentProfile) else _profile_from_dict(profile)
    sit = (
        situation
        if isinstance(situation, DaySituation)
        else _situation_from_dict(situation)
    )
    dishes, catalog = _load_dishes(sit)

    locked_objs: list[LockedChoice] = []
    for item in locked or []:
        if isinstance(item, LockedChoice):
            locked_objs.append(item)
        else:
            locked_objs.append(
                LockedChoice(
                    meal_period=item["meal_period"],
                    dish_id=item["dish_id"],
                    status=item.get("status") or "selected",
                )
            )

    dish_by_id = {str(d.get("dish_id")): d for d in dishes}
    used_venues: set[str] = set()
    used_names: set[str] = set()
    remaining_budget = sit.budget_daily
    remaining_swipes = sit.meal_swipes_remaining

    periods_out: list[dict[str, Any]] = []
    daily_chosen: list[dict[str, Any]] = []

    for period in sit.meal_periods:
        lock = next((L for L in locked_objs if L.meal_period == period), None)
        if lock and lock.dish_id in dish_by_id:
            dish = dish_by_id[lock.dish_id]
            used_venues.add(str(dish.get("venue_id") or ""))
            used_names.add(_norm(str(dish.get("name") or "")))
            price = dish.get("price_amount")
            if sit.mode == "off_campus" and remaining_budget is not None and price is not None:
                remaining_budget = max(0.0, float(remaining_budget) - float(price))
            if sit.mode == "usc_dining" and remaining_swipes is not None:
                remaining_swipes = max(0, int(remaining_swipes) - 1)
            choice = {
                "rank": 1,
                "dish_id": dish.get("dish_id"),
                "name": dish.get("name"),
                "venue_name": dish.get("venue_name"),
                "meal_period": period,
                "status": lock.status,
                "price": {"amount": price, "model": dish.get("payment_model")},
                "why": [f"Locked as {lock.status} — remaining day replanned around this"],
                "nutrition": dish.get("nutrition") or {"confidence": "unavailable"},
            }
            periods_out.append(
                {
                    "meal_period": period,
                    "recommendations": [choice],
                    "count": 1,
                    "locked": True,
                    "notes": [],
                }
            )
            daily_chosen.append(choice)
            continue

        block = _recommend_period(
            dishes,
            prof,
            sit,
            period,
            remaining_budget,
            used_venues,
            used_names,
        )
        periods_out.append(block)
        if block["recommendations"]:
            top = block["recommendations"][0]
            used_venues.add(str(top.get("venue_id") or ""))
            used_names.add(_norm(str(top.get("name") or "")))
            # tentatively account top suggestion for day coherence preview
            if sit.mode == "off_campus" and remaining_budget is not None:
                amt = (top.get("price") or {}).get("amount")
                if amt is not None:
                    remaining_budget = max(0.0, float(remaining_budget) - float(amt))
            if sit.mode == "usc_dining" and remaining_swipes is not None:
                remaining_swipes = max(0, int(remaining_swipes) - 1)

    meta = catalog.get("metadata") or {}
    return {
        "product": "TrojanPlate",
        "tagline": "Your goals. Your campus. Your plate.",
        "mode": sit.mode,
        "menu": {
            "path": catalog.get("_path"),
            "menu_date": meta.get("menu_date") or meta.get("version"),
            "source_url": meta.get("source_url") or meta.get("curated_from"),
            "source_note": meta.get("source_note")
            or meta.get("record_policy"),
        },
        "profile_summary": {
            "nutrition_goal": prof.nutrition_goal,
            "dietary_preference": prof.dietary_preference,
            "allergies": prof.allergies,
            "prefer_high_protein": prof.prefer_high_protein,
        },
        "situation": asdict(sit),
        "periods": periods_out,
        "remaining_after_plan": {
            "budget_daily": remaining_budget,
            "meal_swipes": remaining_swipes,
        },
        "locked": [asdict(x) for x in locked_objs],
        "limitations": [
            "Not medical nutrition advice.",
            "Allergen labels are as published; cross-contact may occur.",
            "Off-campus distance is straight-line miles unless Routes API is added.",
            "USC dining uses a dated snapshot — live menus change daily.",
        ],
    }


def swap_meal(
    profile: dict[str, Any],
    situation: dict[str, Any],
    locked: list[dict[str, Any]],
    meal_period: MealPeriod,
    dish_id: str,
    status: str = "selected",
) -> dict[str, Any]:
    """Lock a choice for one period and replan the rest of the day."""
    new_locked = [
        L
        for L in locked
        if (L.get("meal_period") if isinstance(L, dict) else L.meal_period) != meal_period
    ]
    new_locked.append(
        {"meal_period": meal_period, "dish_id": dish_id, "status": status}
    )
    return plan_day(profile, situation, new_locked)
