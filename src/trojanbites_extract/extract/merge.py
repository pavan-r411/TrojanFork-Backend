from __future__ import annotations

import re
from typing import Any


def _norm_key(name: str, section: str | None, size: str | None) -> str:
    base = re.sub(r"\s+", " ", name.strip().lower())
    return f"{section or ''}::{base}::{size or ''}"


def merge_extractions(*results: dict[str, Any]) -> dict[str, Any]:
    by_key: dict[str, dict[str, Any]] = {}
    conflicts: list[str] = []
    ambiguities: list[str] = []

    for result in results:
        conflicts.extend(result.get("conflicts") or [])
        ambiguities.extend(result.get("ambiguities") or [])
        for item in result.get("menu_items") or []:
            variants = item.get("variants") or [{}]
            size = variants[0].get("size_label") if variants else None
            key = _norm_key(item.get("name") or "", item.get("menu_section"), size)
            if key not in by_key:
                by_key[key] = item
                continue
            existing = by_key[key]
            # Price conflict → flag, null contested
            ep = ((existing.get("variants") or [{}])[0].get("price") or {}).get("amount")
            np_ = ((item.get("variants") or [{}])[0].get("price") or {}).get("amount")
            if ep is not None and np_ is not None and ep != np_:
                conflicts.append(
                    f"price_conflict:{item.get('name')}:{ep} vs {np_}"
                )
                if existing.get("variants"):
                    existing["variants"][0]["price"]["amount"] = None
            # Prefer non-null nutrition macros
            if not existing.get("nutrition") and item.get("nutrition"):
                existing["nutrition"] = item["nutrition"]
            elif existing.get("nutrition") and item.get("nutrition"):
                _merge_nutrition(existing["nutrition"], item["nutrition"], conflicts, item.get("name"))

    return {
        "menu_items": list(by_key.values()),
        "conflicts": conflicts,
        "ambiguities": ambiguities,
    }


def _merge_nutrition(
    a: dict[str, Any], b: dict[str, Any], conflicts: list[str], name: str | None
) -> None:
    ap = a.get("published") or {}
    bp = b.get("published") or {}
    for field in (
        "calories_kcal",
        "protein_g",
        "carbohydrates_g",
        "fat_g",
        "fiber_g",
        "sugar_g",
        "sodium_mg",
    ):
        if ap.get(field) is not None and bp.get(field) is not None and ap[field] != bp[field]:
            conflicts.append(f"nutrition_conflict:{name}:{field}:{ap[field]} vs {bp[field]}")
            ap[field] = None
        elif ap.get(field) is None and bp.get(field) is not None:
            ap[field] = bp[field]
    a["published"] = ap