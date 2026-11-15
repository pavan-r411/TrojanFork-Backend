from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from trojanbites_extract.plan.menus import load_off_campus_menu, load_usc_dining_menu
from trojanbites_extract.plan.targets import estimate_daily_targets, normalize_nutrition_goal
from trojanbites_extract.query.filters import DEFAULT_MAX_DISTANCE_MILES, haversine_miles

Mode = Literal["usc_dining", "off_campus", "hybrid"]
MealPeriod = Literal["breakfast", "lunch", "dinner", "snack"]

DEFAULT_PERIODS: list[MealPeriod] = ["breakfast", "lunch", "dinner"]

PERIOD_TIMES: dict[str, str] = {
    "breakfast": "08:30",
    "lunch": "12:30",
    "snack": "15:30",
    "dinner": "18:30",
}

MEAT_KEYWORDS = (
    "chicken",
    "beef",
    "pork",
    "turkey",
    "lamb",
    "bacon",
    "sausage",
    "steak",
    "meatball",
    "pepperoni",
    "ham",
    "prosciutto",
    "burger",
)
FISH_KEYWORDS = ("fish", "salmon", "tuna", "cod", "shrimp", "seafood", "pescatarian")


@dataclass
class StudentProfile:
    nutrition_goal: str = "balanced"
    dietary_preference: str | None = None
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
    ranking_priority: str = "balanced"
    min_protein: float | None = None
    allow_estimated_nutrition: bool = True


@dataclass
class LockedChoice:
    meal_period: MealPeriod
    dish_id: str
    status: Literal["selected", "eaten", "locked"] = "selected"


def _norm(s: str) -> str:
    return s.strip().lower().replace("-", "_").replace(" ", "_")


def _dish_text(dish: dict[str, Any]) -> str:
    return " ".join(
        [
            str(dish.get("name") or "").lower(),
            str(dish.get("description") or "").lower(),
            " ".join(str(x).lower() for x in (dish.get("ingredients_published") or [])),
            " ".join(str(x).lower() for x in (dish.get("dietary_labels") or [])),
        ]
    )


def _diet_ok(dish: dict[str, Any], preference: str | None) -> bool:
    if not preference:
        return True
    pref = _norm(preference)
    labels = {_norm(x) for x in (dish.get("dietary_labels") or [])}
    text = _dish_text(dish)

    if pref in {"none", "no_preference", "omnivore"}:
        return True
    if pref in labels:
        return True
    if pref == "vegetarian" and "vegan" in labels:
        return True
    if pref in {"halal", "halal_friendly"} and (
        "halal_friendly" in labels or "halal" in labels
    ):
        return True
    if pref == "pescatarian":
        if "vegan" in labels or "vegetarian" in labels or "pescatarian" in labels:
            return True
        if any(k in text for k in FISH_KEYWORDS):
            return True
        if any(k in text for k in MEAT_KEYWORDS):
            return False
        # unlabeled non-meat dish — allow cautiously
        return True
    return False


def _allergy_hit(dish: dict[str, Any], allergies: list[str]) -> str | None:
    published = " ".join(str(a).lower() for a in (dish.get("allergens_published") or []))
    text = _dish_text(dish) + " " + published
    for a in allergies:
        key = a.strip().lower()
        if key and key in text:
            return key
    return None


def _exclusion_hit(dish: dict[str, Any], exclusions: list[str]) -> str | None:
    text = _dish_text(dish)
    for ex in exclusions:
        key = ex.strip().lower()
        if key and key in text:
            return key
    return None


def _macro(dish: dict[str, Any], key: str, allow_estimated: bool = True) -> float | None:
    nut = dish.get("nutrition") or {}
    published = nut.get("published") or {}
    if isinstance(published, dict) and published.get(key) is not None:
        try:
            return float(published[key])
        except (TypeError, ValueError):
            pass
    if allow_estimated:
        estimated = nut.get("estimated") or {}
        if isinstance(estimated, dict) and estimated.get(key) is not None:
            try:
                return float(estimated[key])
            except (TypeError, ValueError):
                return None
    return None


def _protein_g(dish: dict[str, Any], allow_estimated: bool = True) -> float | None:
    return _macro(dish, "protein_g", allow_estimated)


def _calories(dish: dict[str, Any], allow_estimated: bool = True) -> float | None:
    return _macro(dish, "calories_kcal", allow_estimated)


def _carbs(dish: dict[str, Any], allow_estimated: bool = True) -> float | None:
    return _macro(dish, "carbohydrates_g", allow_estimated)


def _fat(dish: dict[str, Any], allow_estimated: bool = True) -> float | None:
    return _macro(dish, "fat_g", allow_estimated)


def _nutrition_confidence(dish: dict[str, Any]) -> str:
    nut = dish.get("nutrition") or {}
    conf = nut.get("confidence")
    if conf in {"confirmed", "estimated", "unavailable"}:
        return str(conf)
    if isinstance(nut.get("published"), dict) and any(
        nut["published"].get(k) is not None
        for k in ("protein_g", "calories_kcal")
    ):
        return "confirmed"
    if isinstance(nut.get("estimated"), dict) and any(
        nut["estimated"].get(k) is not None
        for k in ("protein_g", "calories_kcal")
    ):
        return "estimated"
    return "unavailable"


def _distance(dish: dict[str, Any], lat: float | None, lng: float | None) -> float | None:
    if lat is None or lng is None:
        return None
    dlat, dlng = dish.get("lat"), dish.get("lng")
    if dlat is None or dlng is None:
        return None
    return haversine_miles(lat, lng, float(dlat), float(dlng))


def _walk_minutes(dist: float | None) -> int | None:
    if dist is None:
        return None
    return max(1, int(round(float(dist) * 20)))


def _match_percent(score: float) -> int:
    # Typical scores ~40–110 → UI-friendly 55–99
    return int(min(99, max(55, round(score))))


def _uses_cash(situation: DaySituation, period: MealPeriod, dish: dict[str, Any]) -> bool:
    model = str(dish.get("payment_model") or "")
    if model == "meal_swipe_ayce":
        return False
    if situation.mode == "off_campus":
        return True
    if situation.mode == "hybrid" and period == "snack":
        return True
    if model == "cash_card":
        return True
    return False


def _uses_swipe(situation: DaySituation, period: MealPeriod, dish: dict[str, Any]) -> bool:
    model = str(dish.get("payment_model") or "")
    if model == "meal_swipe_ayce":
        return True
    if situation.mode == "usc_dining":
        return True
    if situation.mode == "hybrid" and period in {"breakfast", "lunch", "dinner"}:
        return model != "cash_card"
    return False


def _catalog_source_for_period(situation: DaySituation, period: MealPeriod) -> str:
    if situation.mode == "hybrid":
        return "off_campus" if period == "snack" else "usc_dining"
    return situation.mode


def _load_dishes(
    situation: DaySituation,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, list[dict[str, Any]]]]:
    dining = load_usc_dining_menu(situation.menu_date)
    off = load_off_campus_menu()
    by_source = {
        "usc_dining": list(dining.get("dishes") or []),
        "off_campus": list(off.get("dishes") or []),
    }
    if situation.mode == "usc_dining":
        return by_source["usc_dining"], dining, by_source
    if situation.mode == "off_campus":
        return by_source["off_campus"], off, by_source
    # hybrid: union for locking lookups; period filtering picks source
    merged = by_source["usc_dining"] + by_source["off_campus"]
    catalog = {
        "metadata": {
            "mode": "hybrid",
            "menu_date": (dining.get("metadata") or {}).get("menu_date"),
            "source_note": (
                "Hybrid: residential dining for main meals; "
                "curated off-campus for snacks/cash items."
            ),
            "usc_path": dining.get("_path"),
            "off_campus_path": off.get("_path"),
        },
        "_path": f"{dining.get('_path')}+{off.get('_path')}",
        "venues": (dining.get("venues") or []) + (off.get("venues") or []),
    }
    return merged, catalog, by_source


def _eligible(
    dish: dict[str, Any],
    profile: StudentProfile,
    situation: DaySituation,
    period: MealPeriod,
    remaining_cash: float | None,
) -> tuple[bool, list[str]]:
    periods = dish.get("meal_periods") or []
    if period not in periods:
        # Hybrid snacks may reuse lunch/dinner off-campus items when snack tags are sparse
        if not (
            situation.mode == "hybrid"
            and period == "snack"
            and set(periods) & {"lunch", "dinner", "snack"}
        ):
            return False, ["wrong_meal_period"]

    if not _diet_ok(dish, profile.dietary_preference):
        return False, ["diet_mismatch"]

    hit = _allergy_hit(dish, profile.allergies)
    if hit:
        return False, [f"allergy:{hit}"]

    ex = _exclusion_hit(dish, profile.exclusions)
    if ex:
        return False, [f"exclusion:{ex}"]

    source = _catalog_source_for_period(situation, period)
    # hybrid: enforce source split
    if situation.mode == "hybrid":
        is_hall = str(dish.get("payment_model") or "") == "meal_swipe_ayce" or str(
            dish.get("venue_id") or ""
        ).startswith("usc_")
        if period == "snack" and is_hall and dish.get("price_amount") is None:
            # allow hall snacks in hybrid only if they exist; prefer cash later via ranking
            pass
        if period != "snack" and not is_hall and source == "usc_dining":
            # off-campus dish during main meal in hybrid — skip
            if str(dish.get("venue_id") or "").startswith("tb-r-"):
                return False, ["hybrid_main_meals_usc_only"]

    needs_geo = situation.mode == "off_campus" or (
        situation.mode == "hybrid" and period == "snack" and dish.get("lat") is not None
    )
    if needs_geo and dish.get("lat") is not None:
        dist = _distance(dish, situation.lat, situation.lng)
        if dist is None:
            return False, ["missing_coordinates"]
        if dist > situation.max_miles:
            return False, ["too_far"]

    if _uses_cash(situation, period, dish):
        price = dish.get("price_amount")
        cap = situation.budget_per_meal
        if remaining_cash is not None and cap is not None:
            cap = min(cap, remaining_cash)
        elif remaining_cash is not None:
            cap = remaining_cash
        if cap is not None:
            if price is None:
                return False, ["price_unknown_hard_budget"]
            if float(price) > float(cap):
                return False, ["over_budget"]

    if situation.min_protein is not None:
        prot = _protein_g(dish, allow_estimated=situation.allow_estimated_nutrition)
        if prot is None:
            return False, ["protein_unknown"]
        if float(prot) < float(situation.min_protein):
            return False, ["below_min_protein"]

    return True, []


def _score(
    dish: dict[str, Any],
    profile: StudentProfile,
    situation: DaySituation,
    period: MealPeriod,
    used_venues: set[str],
    used_names: set[str],
) -> tuple[float, list[str]]:
    score = 50.0
    why: list[str] = []
    labels = {_norm(x) for x in (dish.get("dietary_labels") or [])}

    if profile.dietary_preference and _diet_ok(dish, profile.dietary_preference):
        score += 18
        why.append(f"Matches {profile.dietary_preference} preference")

    goal = _norm(profile.nutrition_goal)
    if profile.prefer_high_protein or "training" in goal or "muscle" in goal:
        if "high_protein" in labels:
            score += 12
            why.append("Labeled high-protein on the menu")
        prot = _protein_g(dish, allow_estimated=situation.allow_estimated_nutrition)
        if prot is not None:
            score += min(prot / 5.0, 15)
            conf = _nutrition_confidence(dish)
            label = "Published" if conf == "confirmed" else "Estimated"
            why.append(f"{label} protein {prot:g}g")

    if "balanced" in goal or goal == "maintenance":
        score += 4
        why.append("Fits a balanced daily plate")

    cash_like = _uses_cash(situation, period, dish)
    if cash_like and situation.preferred_cuisines:
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

    if cash_like:
        price = dish.get("price_amount")
        if price is not None and situation.budget_per_meal is not None:
            headroom = float(situation.budget_per_meal) - float(price)
            if headroom >= 0:
                score += min(headroom, 10)
                why.append(f"${price:g} within ${situation.budget_per_meal:g} meal budget")
        dist = _distance(dish, situation.lat, situation.lng)
        if dist is not None:
            score += max(0, 10 - dist * 20)
            mins = _walk_minutes(dist)
            why.append(f"{dist:.2f} mi ≈ {mins} min walk (estimate)")
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
        score -= 6
    name = _norm(str(dish.get("name") or ""))
    if name in used_names:
        score -= 20

    conf = _nutrition_confidence(dish)
    if conf == "unavailable":
        why.append("Nutrition figures unavailable from source")
    elif conf == "estimated":
        why.append("Macros are estimated for planning — not restaurant-published")

    if not why:
        why.append("Eligible under your hard constraints")
    return score, why


def _payment_payload(
    dish: dict[str, Any], situation: DaySituation, period: MealPeriod
) -> dict[str, Any]:
    swipe = _uses_swipe(situation, period, dish)
    model = dish.get("payment_model") or ("meal_swipe_ayce" if swipe else "cash_card")
    return {
        "amount": dish.get("price_amount"),
        "currency": dish.get("currency") or "USD",
        "model": model,
        "note": (
            "Residential dining visit uses a meal swipe / AYCE — no per-dish purchase price."
            if swipe
            else "Menu price excludes tax and fees. May use Dining Dollars when provided."
        ),
    }


def _rec_from_dish(
    dish: dict[str, Any],
    situation: DaySituation,
    period: MealPeriod,
    score: float,
    why: list[str],
    rank: int,
    status: str | None = None,
) -> dict[str, Any]:
    nut = dish.get("nutrition") or {}
    allow = situation.allow_estimated_nutrition
    conf = _nutrition_confidence(dish)
    dist = _distance(dish, situation.lat, situation.lng)
    protein = _protein_g(dish, allow_estimated=allow)
    calories = _calories(dish, allow_estimated=allow)
    out: dict[str, Any] = {
        "rank": rank,
        "score": round(score, 2),
        "match_percent": _match_percent(score),
        "dish_id": dish.get("dish_id"),
        "name": dish.get("name"),
        "venue_id": dish.get("venue_id"),
        "venue_name": dish.get("venue_name"),
        "meal_period": period,
        "suggested_time": PERIOD_TIMES.get(period),
        "description": dish.get("description"),
        "dietary_labels": dish.get("dietary_labels") or [],
        "allergens_published": dish.get("allergens_published") or [],
        "allergens_note": (
            "Allergens as published; cross-contact may occur. Not a medical guarantee."
        ),
        "price": _payment_payload(dish, situation, period),
        "nutrition": {
            "confidence": conf,
            "published": nut.get("published"),
            "estimated": nut.get("estimated"),
            "protein_g": protein,
            "calories_kcal": calories,
            "carbohydrates_g": _carbs(dish, allow_estimated=allow),
            "fat_g": _fat(dish, allow_estimated=allow),
        },
        # Flat convenience fields for UI cards
        "protein_g": protein,
        "calories_kcal": calories,
        "distance_miles": None if dist is None else round(dist, 3),
        "distance_metric": "haversine_miles_straight_line",
        "walk_minutes_estimate": _walk_minutes(dist),
        "walk_estimate_note": "Straight-line miles × 20; not a walking-route ETA.",
        "why": why[:4],
    }
    if status:
        out["status"] = status
    return out


def _recommend_period(
    dishes: list[dict[str, Any]],
    profile: StudentProfile,
    situation: DaySituation,
    period: MealPeriod,
    remaining_cash: float | None,
    used_venues: set[str],
    used_names: set[str],
    by_source: dict[str, list[dict[str, Any]]],
    limit: int = 3,
) -> dict[str, Any]:
    source = _catalog_source_for_period(situation, period)
    pool = by_source.get(source) or dishes
    if situation.mode == "hybrid" and period == "snack":
        off = by_source.get("off_campus") or []
        snackish = [d for d in off if "snack" in (d.get("meal_periods") or [])]
        if not snackish:
            # Allow lunch/dinner off-campus items as snack candidates when no snack tags
            snackish = [
                d
                for d in off
                if set(d.get("meal_periods") or []) & {"lunch", "dinner", "snack"}
            ]
        pool = snackish or [
            d
            for d in by_source.get("usc_dining") or []
            if "snack" in (d.get("meal_periods") or [])
        ]

    scored: list[tuple[float, dict[str, Any], list[str]]] = []
    for dish in pool:
        ok, _reasons = _eligible(dish, profile, situation, period, remaining_cash)
        if not ok:
            continue
        s, why = _score(dish, profile, situation, period, used_venues, used_names)
        scored.append((s, dish, why))

    scored.sort(key=lambda t: t[0], reverse=True)
    picks: list[dict[str, Any]] = []
    seen: set[str] = set()
    for s, dish, why in scored:
        did = str(dish.get("dish_id"))
        if did in seen:
            continue
        seen.add(did)
        picks.append(_rec_from_dish(dish, situation, period, s, why, len(picks) + 1))
        if len(picks) >= limit:
            break

    notes: list[str] = []
    if len(picks) < limit:
        notes.append(
            f"Only {len(picks)} option(s) met hard constraints for {period}; "
            "not inventing fillers. Try relaxing cuisine, budget, or diet filters."
        )

    return {
        "meal_period": period,
        "suggested_time": PERIOD_TIMES.get(period),
        "recommendations": picks,
        "count": len(picks),
        "notes": notes,
    }


def _profile_from_dict(data: dict[str, Any] | None) -> StudentProfile:
    data = data or {}
    goal = normalize_nutrition_goal(str(data.get("nutrition_goal") or "balanced"))
    return StudentProfile(
        nutrition_goal=goal,
        dietary_preference=data.get("dietary_preference"),
        allergies=list(data.get("allergies") or []),
        exclusions=list(data.get("exclusions") or []),
        preferred_foods=list(data.get("preferred_foods") or []),
        prefer_high_protein=bool(
            data.get("prefer_high_protein")
            or goal == "training_muscle"
            or "muscle" in _norm(str(data.get("nutrition_goal") or ""))
        ),
        age_range=data.get("age_range"),
        activity_level=data.get("activity_level"),
        height_cm=data.get("height_cm"),
        weight_kg=data.get("weight_kg"),
        goal_weight_kg=data.get("goal_weight_kg"),
    )


def _situation_from_dict(data: dict[str, Any]) -> DaySituation:
    periods = data.get("meal_periods") or list(DEFAULT_PERIODS)
    mode = data["mode"]
    if data.get("include_snacks") and "snack" not in periods:
        periods = list(periods) + ["snack"]
    if mode == "hybrid" and "snack" not in periods:
        periods = list(periods) + ["snack"]
    return DaySituation(
        mode=mode,
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
        min_protein=(
            float(data["min_protein"]) if data.get("min_protein") is not None else None
        ),
        allow_estimated_nutrition=bool(data.get("allow_estimated_nutrition", True)),
    )


def _sum_known(values: list[float | None]) -> tuple[float | None, str]:
    known = [v for v in values if v is not None]
    if not known:
        return None, "unavailable"
    if len(known) < len(values):
        return float(sum(known)), "partial"
    return float(sum(known)), "confirmed"


def _daily_planned(periods_out: list[dict[str, Any]]) -> dict[str, Any]:
    tops: list[dict[str, Any]] = []
    for block in periods_out:
        recs = block.get("recommendations") or []
        if recs:
            tops.append(recs[0])
    cals = [_rec_cal(r) for r in tops]
    prots = [_rec_prot(r) for r in tops]
    carbs = [
        (r.get("nutrition") or {}).get("carbohydrates_g")
        if isinstance(r.get("nutrition"), dict)
        else None
        for r in tops
    ]
    fats = [
        (r.get("nutrition") or {}).get("fat_g")
        if isinstance(r.get("nutrition"), dict)
        else None
        for r in tops
    ]
    cal_sum, cal_conf = _sum_known(cals)
    prot_sum, prot_conf = _sum_known(prots)
    carb_sum, carb_conf = _sum_known(carbs)
    fat_sum, fat_conf = _sum_known(fats)
    return {
        "confidence": (
            "unavailable"
            if all(c == "unavailable" for c in (cal_conf, prot_conf, carb_conf, fat_conf))
            else "partial"
        ),
        "note": "Sums known macros from top/locked pick per period only; missing dish macros stay null.",
        "calories_kcal": None if cal_sum is None else round(cal_sum),
        "protein_g": None if prot_sum is None else round(prot_sum, 1),
        "carbohydrates_g": None if carb_sum is None else round(carb_sum, 1),
        "fat_g": None if fat_sum is None else round(fat_sum, 1),
        "field_confidence": {
            "calories_kcal": cal_conf,
            "protein_g": prot_conf,
            "carbohydrates_g": carb_conf,
            "fat_g": fat_conf,
        },
    }


def _rec_macro(rec: dict[str, Any], key: str) -> float | None:
    if rec.get(key) is not None:
        try:
            return float(rec[key])
        except (TypeError, ValueError):
            pass
    nut = rec.get("nutrition") or {}
    if not isinstance(nut, dict):
        return None
    if nut.get(key) is not None:
        try:
            return float(nut[key])
        except (TypeError, ValueError):
            pass
    for bucket in ("published", "estimated"):
        block = nut.get(bucket) or {}
        if isinstance(block, dict) and block.get(key) is not None:
            try:
                return float(block[key])
            except (TypeError, ValueError):
                return None
    return None


def _rec_cal(rec: dict[str, Any]) -> float | None:
    return _rec_macro(rec, "calories_kcal")


def _rec_prot(rec: dict[str, Any]) -> float | None:
    return _rec_macro(rec, "protein_g")


def _initial_cash_pool(sit: DaySituation) -> float | None:
    parts: list[float] = []
    if sit.budget_daily is not None:
        parts.append(float(sit.budget_daily))
    if sit.dining_dollars_remaining is not None:
        parts.append(float(sit.dining_dollars_remaining))
    if not parts:
        return None
    # Prefer Dining Dollars first conceptually, but pool is max available cash-like spend
    if sit.budget_daily is not None and sit.dining_dollars_remaining is not None:
        return float(sit.budget_daily) + float(sit.dining_dollars_remaining)
    return parts[0]


def plan_day(
    profile: dict[str, Any] | StudentProfile,
    situation: dict[str, Any] | DaySituation,
    locked: list[dict[str, Any] | LockedChoice] | None = None,
    previous_plan: dict[str, Any] | None = None,
    swap_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prof = profile if isinstance(profile, StudentProfile) else _profile_from_dict(profile)
    sit = (
        situation
        if isinstance(situation, DaySituation)
        else _situation_from_dict(situation)
    )
    from trojanbites_extract.plan.menus import clear_menu_cache

    clear_menu_cache()
    dishes, catalog, by_source = _load_dishes(sit)
    targets = estimate_daily_targets(
        {
            "nutrition_goal": prof.nutrition_goal,
            "prefer_high_protein": prof.prefer_high_protein,
            "age_range": prof.age_range,
            "activity_level": prof.activity_level,
            "height_cm": prof.height_cm,
            "weight_kg": prof.weight_kg,
            "goal_weight_kg": prof.goal_weight_kg,
        }
    )

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
    remaining_cash = _initial_cash_pool(sit)
    remaining_swipes = sit.meal_swipes_remaining
    remaining_dollars = sit.dining_dollars_remaining
    remaining_budget = sit.budget_daily
    swipes_used = 0
    cash_spent = 0.0

    periods_out: list[dict[str, Any]] = []

    for period in sit.meal_periods:
        lock = next((L for L in locked_objs if L.meal_period == period), None)
        if lock and lock.dish_id in dish_by_id:
            dish = dish_by_id[lock.dish_id]
            used_venues.add(str(dish.get("venue_id") or ""))
            used_names.add(_norm(str(dish.get("name") or "")))
            price = dish.get("price_amount")
            if _uses_cash(sit, period, dish) and price is not None:
                amt = float(price)
                cash_spent += amt
                if remaining_dollars is not None:
                    take = min(amt, float(remaining_dollars))
                    remaining_dollars = float(remaining_dollars) - take
                    amt -= take
                if remaining_budget is not None and amt > 0:
                    remaining_budget = max(0.0, float(remaining_budget) - amt)
                remaining_cash = _recompute_cash(remaining_budget, remaining_dollars)
            if _uses_swipe(sit, period, dish) and remaining_swipes is not None:
                remaining_swipes = max(0, int(remaining_swipes) - 1)
                swipes_used += 1
            choice = _rec_from_dish(
                dish,
                sit,
                period,
                score=90.0,
                why=[f"Locked as {lock.status} — remaining day replanned around this"],
                rank=1,
                status=lock.status,
            )
            periods_out.append(
                {
                    "meal_period": period,
                    "suggested_time": PERIOD_TIMES.get(period),
                    "recommendations": [choice],
                    "count": 1,
                    "locked": True,
                    "notes": [],
                }
            )
            continue

        block = _recommend_period(
            dishes,
            prof,
            sit,
            period,
            remaining_cash,
            used_venues,
            used_names,
            by_source,
        )
        periods_out.append(block)
        if block["recommendations"]:
            top = block["recommendations"][0]
            used_venues.add(str(top.get("venue_id") or ""))
            used_names.add(_norm(str(top.get("name") or "")))
            amt = (top.get("price") or {}).get("amount")
            model = (top.get("price") or {}).get("model")
            if model != "meal_swipe_ayce" and amt is not None and remaining_cash is not None:
                cash_spent += float(amt)
                left = float(amt)
                if remaining_dollars is not None:
                    take = min(left, float(remaining_dollars))
                    remaining_dollars = float(remaining_dollars) - take
                    left -= take
                if remaining_budget is not None and left > 0:
                    remaining_budget = max(0.0, float(remaining_budget) - left)
                remaining_cash = _recompute_cash(remaining_budget, remaining_dollars)
            if model == "meal_swipe_ayce" and remaining_swipes is not None:
                remaining_swipes = max(0, int(remaining_swipes) - 1)
                swipes_used += 1

    meta = catalog.get("metadata") or {}
    rebalance_delta = None
    if previous_plan and swap_meta:
        rebalance_delta = _compute_rebalance_delta(
            previous_plan, periods_out, swap_meta.get("meal_period")
        )

    return {
        "product": "TrojanPlate",
        "tagline": "Your goals. Your campus. Your plate.",
        "mode": sit.mode,
        "menu": {
            "path": catalog.get("_path"),
            "menu_date": meta.get("menu_date") or meta.get("version"),
            "source_url": meta.get("source_url") or meta.get("curated_from"),
            "source_note": meta.get("source_note") or meta.get("record_policy"),
        },
        "profile_summary": {
            "nutrition_goal": prof.nutrition_goal,
            "dietary_preference": prof.dietary_preference,
            "allergies": prof.allergies,
            "prefer_high_protein": prof.prefer_high_protein,
        },
        "daily_targets": targets,
        "daily_planned": _daily_planned(periods_out),
        "spending": {
            "meal_swipes_used": swipes_used,
            "meal_swipes_remaining": remaining_swipes,
            "cash_spent": round(cash_spent, 2),
            "budget_daily_remaining": remaining_budget,
            "dining_dollars_remaining": remaining_dollars,
            "note": "Swipe for AYCE halls; cash/Dining Dollars for priced items.",
        },
        "situation": asdict(sit),
        "periods": periods_out,
        "remaining_after_plan": {
            "budget_daily": remaining_budget,
            "meal_swipes": remaining_swipes,
            "dining_dollars": remaining_dollars,
        },
        "rebalance_delta": rebalance_delta,
        "locked": [asdict(x) for x in locked_objs],
        "limitations": [
            "Not medical nutrition advice.",
            "Allergen labels are as published; cross-contact may occur.",
            "Off-campus distance is straight-line miles; walk minutes are estimates.",
            "USC dining uses a dated snapshot — live menus change daily.",
            "Dish macros are never invented; daily targets may be estimated.",
        ],
    }


def _recompute_cash(
    budget_daily: float | None, dining_dollars: float | None
) -> float | None:
    parts = [p for p in (budget_daily, dining_dollars) if p is not None]
    if not parts:
        return None
    return float(sum(parts))


def _compute_rebalance_delta(
    previous_plan: dict[str, Any],
    new_periods: list[dict[str, Any]],
    meal_period: str | None,
) -> dict[str, Any]:
    def top_for(plan_periods: list[dict[str, Any]], period: str) -> dict[str, Any] | None:
        for b in plan_periods:
            if b.get("meal_period") == period and b.get("recommendations"):
                return b["recommendations"][0]
        return None

    old_periods = previous_plan.get("periods") or []
    # Compare full-day known macros when possible
    old_daily = previous_plan.get("daily_planned") or {}
    new_daily = _daily_planned(new_periods)
    cal_delta = None
    prot_delta = None
    if old_daily.get("calories_kcal") is not None and new_daily.get("calories_kcal") is not None:
        cal_delta = int(new_daily["calories_kcal"] - old_daily["calories_kcal"])
    if old_daily.get("protein_g") is not None and new_daily.get("protein_g") is not None:
        prot_delta = round(float(new_daily["protein_g"]) - float(old_daily["protein_g"]), 1)

    meal_delta = None
    if meal_period:
        old_top = top_for(old_periods, meal_period)
        new_top = top_for(new_periods, meal_period)
        if old_top and new_top:
            oc, nc = _rec_cal(old_top), _rec_cal(new_top)
            op, np_ = _rec_prot(old_top), _rec_prot(new_top)
            meal_delta = {
                "meal_period": meal_period,
                "calories_kcal": None
                if oc is None or nc is None
                else int(round(nc - oc)),
                "protein_g": None
                if op is None or np_ is None
                else round(np_ - op, 1),
            }

    return {
        "calories_kcal": cal_delta,
        "protein_g": prot_delta,
        "meal": meal_delta,
        "note": (
            "Null when either side lacks published macros — never invent deltas."
        ),
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
    previous = plan_day(profile, situation, locked)
    new_locked = [
        L
        for L in locked
        if (L.get("meal_period") if isinstance(L, dict) else L.meal_period) != meal_period
    ]
    new_locked.append(
        {"meal_period": meal_period, "dish_id": dish_id, "status": status}
    )
    return plan_day(
        profile,
        situation,
        new_locked,
        previous_plan=previous,
        swap_meta={"meal_period": meal_period, "dish_id": dish_id},
    )
