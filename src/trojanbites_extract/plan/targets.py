from __future__ import annotations

from typing import Any

GOAL_ALIASES: dict[str, str] = {
    "balanced": "balanced",
    "feel_balanced": "balanced",
    "maintenance": "maintenance",
    "weight_maintenance": "maintenance",
    "training": "training_muscle",
    "training_muscle": "training_muscle",
    "build_muscle": "training_muscle",
    "muscle": "training_muscle",
    "gradual_gain": "gradual_gain",
    "weight_gain": "gradual_gain",
    "gradual_loss": "gradual_loss",
    "lose_body_fat": "gradual_loss",
    "lose_fat": "gradual_loss",
    "weight_loss": "gradual_loss",
}

ACTIVITY_FACTORS: dict[str, float] = {
    "sedentary": 1.2,
    "light": 1.375,
    "lightly_active": 1.375,
    "moderate": 1.55,
    "moderately_active": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}


def _norm(s: str | None) -> str:
    return (s or "").strip().lower().replace("-", "_").replace(" ", "_")


def normalize_nutrition_goal(raw: str | None) -> str:
    key = _norm(raw) or "balanced"
    return GOAL_ALIASES.get(key, key if key in GOAL_ALIASES.values() else "balanced")


def _age_years(age_range: str | None) -> int:
    """Assume a mid-band adult age when only a range/label is provided."""
    text = _norm(age_range)
    if not text:
        return 21  # typical USC undergrad band for hackathon estimates
    digits = "".join(ch if ch.isdigit() else " " for ch in text).split()
    if digits:
        try:
            return int(digits[0])
        except ValueError:
            pass
    return 21


def _activity_factor(level: str | None) -> float:
    key = _norm(level)
    if key in ACTIVITY_FACTORS:
        return ACTIVITY_FACTORS[key]
    if "very" in key:
        return 1.9
    if "active" in key or "moderate" in key:
        return 1.55
    if "light" in key:
        return 1.375
    return 1.55


def estimate_daily_targets(profile: dict[str, Any] | None) -> dict[str, Any]:
    """
    Estimate daily macro *targets* for UI rings.
    Not dish nutrition — confidence is estimated|unavailable.
    Uses Mifflin–St Jeor (male equation as default adult estimate when sex unknown).
    """
    data = profile or {}
    goal = normalize_nutrition_goal(data.get("nutrition_goal"))
    height_cm = data.get("height_cm")
    weight_kg = data.get("weight_kg")
    goal_weight_kg = data.get("goal_weight_kg")
    activity = data.get("activity_level")
    age = _age_years(data.get("age_range"))
    prefer_high_protein = bool(
        data.get("prefer_high_protein")
        or goal == "training_muscle"
        or "muscle" in _norm(data.get("nutrition_goal"))
    )

    if height_cm is None or weight_kg is None:
        return {
            "nutrition_goal_normalized": goal,
            "confidence": "unavailable",
            "method": None,
            "note": "Provide height_cm and weight_kg to estimate daily targets.",
            "targets": {
                "calories_kcal": None,
                "protein_g": None,
                "carbohydrates_g": None,
                "fat_g": None,
            },
            "inputs_used": {
                "height_cm": height_cm,
                "weight_kg": weight_kg,
                "goal_weight_kg": goal_weight_kg,
                "activity_level": activity,
                "age_years_assumed": age,
            },
        }

    h = float(height_cm)
    w = float(weight_kg)
    # Mifflin–St Jeor (male) as default when sex not collected
    bmr = 10 * w + 6.25 * h - 5 * age + 5
    tdee = bmr * _activity_factor(activity)

    calories = tdee
    if goal in {"gradual_loss"}:
        calories = tdee - 350
    elif goal in {"gradual_gain", "training_muscle"}:
        calories = tdee + 250
    elif goal == "maintenance":
        calories = tdee

    # lean toward goal weight midpoint for protein if provided
    protein_basis = w
    if goal_weight_kg is not None:
        try:
            protein_basis = (w + float(goal_weight_kg)) / 2.0
        except (TypeError, ValueError):
            protein_basis = w

    if prefer_high_protein or goal == "training_muscle":
        protein_g = protein_basis * 1.8
    elif goal == "gradual_loss":
        protein_g = protein_basis * 1.6
    else:
        protein_g = protein_basis * 1.2

    # remaining calories → carbs/fats (approx 50% carb / 30% fat of leftover after protein)
    protein_kcal = protein_g * 4
    remain = max(calories - protein_kcal, calories * 0.35)
    carbs_g = (remain * 0.55) / 4
    fat_g = (remain * 0.45) / 9

    return {
        "nutrition_goal_normalized": goal,
        "confidence": "estimated",
        "method": "mifflin_st_jeor_tdee_hackathon",
        "note": (
            "Estimated daily targets for planning UI only — not medical advice. "
            "Dish macros are never invented from this."
        ),
        "targets": {
            "calories_kcal": int(round(calories)),
            "protein_g": int(round(protein_g)),
            "carbohydrates_g": int(round(carbs_g)),
            "fat_g": int(round(fat_g)),
        },
        "inputs_used": {
            "height_cm": h,
            "weight_kg": w,
            "goal_weight_kg": goal_weight_kg,
            "activity_level": activity,
            "age_years_assumed": age,
            "prefer_high_protein": prefer_high_protein,
        },
    }
