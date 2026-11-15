from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationReport:
    passed: bool
    hard_fail: bool
    flags: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)


MACRO_FIELDS = (
    "calories_kcal",
    "protein_g",
    "carbohydrates_g",
    "fat_g",
    "fiber_g",
    "sugar_g",
    "sodium_mg",
)


def validate_extraction(
    result: dict[str, Any],
    *,
    boundary_status: str | None = None,
    restaurant_id: str | None = None,
) -> ValidationReport:
    flags: list[str] = []
    reasons: list[str] = []
    hard = False

    if "menu_items" not in result or not isinstance(result["menu_items"], list):
        return ValidationReport(
            passed=False,
            hard_fail=True,
            flags=["missing_menu_items"],
            reason_codes=["SCHEMA_INVALID"],
        )

    for item in result["menu_items"]:
        if not item.get("name"):
            hard = True
            reasons.append("SCHEMA_INVALID")
            flags.append("item_missing_name")
        if restaurant_id and item.get("restaurant_id") not in (None, restaurant_id):
            flags.append("restaurant_id_mismatch")
            reasons.append("BRANCH_AMBIGUOUS")

        variants = item.get("variants") or []
        if not variants:
            hard = True
            reasons.append("SCHEMA_INVALID")
            flags.append(f"no_variants:{item.get('name')}")
            continue

        for variant in variants:
            price = (variant.get("price") or {}).get("amount")
            currency = (variant.get("price") or {}).get("currency")
            if price is not None and price < 0:
                hard = True
                reasons.append("SCHEMA_INVALID")
                flags.append(f"negative_price:{item.get('name')}")
            if price is not None and currency and len(str(currency)) != 3:
                flags.append(f"bad_currency:{item.get('name')}")
                reasons.append("SCHEMA_INVALID")

        nut = item.get("nutrition")
        if nut:
            published = nut.get("published") or {}
            for field in MACRO_FIELDS:
                val = published.get(field)
                if val is not None and val < 0:
                    hard = True
                    reasons.append("SCHEMA_INVALID")
                    flags.append(f"negative_macro:{field}:{item.get('name')}")
            if nut.get("evidence_status") == "estimated" and nut.get("estimated") is None:
                flags.append(f"estimated_missing_payload:{item.get('name')}")
            # published must stay nulls if unknown — ok
            if nut.get("evidence_status") == "restaurant_published":
                if all(published.get(f) is None for f in MACRO_FIELDS):
                    flags.append(f"published_status_without_macros:{item.get('name')}")

        for claim in item.get("dietary_claims") or []:
            if claim.get("is_guarantee") is True:
                flags.append(f"dietary_guarantee_forbidden:{item.get('name')}")
                reasons.append("SCHEMA_INVALID")
                hard = True

    for conflict in result.get("conflicts") or []:
        flags.append(f"conflict:{conflict}")
        reasons.append("PRICE_CONFLICT" if "price" in conflict else "NUTRITION_SIZE_MISMATCH")

    if boundary_status == "unknown":
        flags.append("boundary_unknown")
        reasons.append("BOUNDARY_EDGE")

    # de-dupe reason codes
    reason_codes = sorted(set(reasons))
    passed = not hard and not any(
        r in reason_codes for r in ("SCHEMA_INVALID",)
    )
    # soft flags still pass but may need review
    needs_review_codes = {
        "PRICE_CONFLICT",
        "NUTRITION_SIZE_MISMATCH",
        "BOUNDARY_EDGE",
        "BRANCH_AMBIGUOUS",
    }
    if any(c in needs_review_codes for c in reason_codes):
        passed = passed and False if hard else True

    return ValidationReport(
        passed=not hard,
        hard_fail=hard,
        flags=flags,
        reason_codes=reason_codes,
    )