from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from trojanbites_extract.ids import new_id
from trojanbites_extract.settings import ROOT
from trojanbites_extract.store.db import init_db, session_scope
from trojanbites_extract.store.upserts import (
    replace_menu_for_restaurant,
    upsert_restaurant,
    upsert_source,
)

DEFAULT_PILOT_JSON = ROOT / "data" / "pilot" / "usc_restaurants.json"


def _norm_business_status(raw: str | None) -> str:
    if not raw:
        return "unknown"
    s = raw.lower()
    if "operational" in s:
        return "operational"
    if "permanently" in s or "closed_permanently" in s:
        return "closed_permanently"
    if "temporary" in s:
        return "closed_temporarily"
    return "unknown"


def _diet_claims(labels: Any) -> list[dict[str, Any]]:
    if not labels:
        return []
    if isinstance(labels, str):
        labels = [labels]
    out = []
    for label in labels:
        if not label:
            continue
        out.append(
            {
                "claim": str(label).strip().lower(),
                "raw_text": str(label),
                "evidence_status": "restaurant_published",
                "is_guarantee": False,
            }
        )
    return out


def _allergen_claims(labels: Any) -> list[dict[str, Any]]:
    if not labels:
        return []
    if isinstance(labels, str):
        labels = [labels]
    return [
        {
            "claim": str(x).strip().lower(),
            "raw_text": str(x),
            "evidence_status": "restaurant_published",
        }
        for x in labels
        if x
    ]


def _map_variants(item: dict[str, Any]) -> list[dict[str, Any]]:
    variants_in = item.get("variants") or []
    currency = item.get("currency") or "USD"
    addons = item.get("addons") or []
    mapped_addons = []
    for a in addons:
        if isinstance(a, dict):
            mapped_addons.append(
                {
                    "name": a.get("name") or a.get("label") or "addon",
                    "price_amount": a.get("price") if a.get("price") is not None else a.get("price_amount"),
                    "currency": currency,
                }
            )
        elif isinstance(a, str):
            mapped_addons.append({"name": a, "price_amount": None, "currency": currency})

    if variants_in:
        out = []
        for v in variants_in:
            if not isinstance(v, dict):
                continue
            out.append(
                {
                    "variant_id": new_id("var"),
                    "size_label": v.get("name") or v.get("size_label"),
                    "serving_label": item.get("serving"),
                    "price": {
                        "amount": v.get("price"),
                        "currency": currency,
                    },
                    "addons": mapped_addons,
                }
            )
        return out or [
            {
                "variant_id": new_id("var"),
                "size_label": None,
                "serving_label": item.get("serving"),
                "price": {"amount": item.get("price"), "currency": currency},
                "addons": mapped_addons,
            }
        ]

    return [
        {
            "variant_id": new_id("var"),
            "size_label": None,
            "serving_label": item.get("serving"),
            "price": {"amount": item.get("price"), "currency": currency},
            "addons": mapped_addons,
        }
    ]


def _map_nutrition(item: dict[str, Any], item_id: str, variant_id: str) -> dict[str, Any] | None:
    nut = item.get("nutrition")
    if not nut or not isinstance(nut, dict):
        return None
    status = nut.get("status") or "unknown"
    # Map Claude status → our evidence_status
    if status in {"restaurant_published", "estimated", "unknown"}:
        evidence = status
    elif status == "published":
        evidence = "restaurant_published"
    else:
        evidence = "unknown"

    published = nut.get("published") or {}
    estimated_raw = nut.get("estimated") or {}
    estimated = None
    if evidence == "estimated" or any(
        estimated_raw.get(k) is not None
        for k in ("calories_kcal", "protein_g", "carbohydrates_g", "fat_g")
    ):
        if any(
            estimated_raw.get(k) is not None
            for k in ("calories_kcal", "protein_g", "carbohydrates_g", "fat_g")
        ):
            estimated = {
                "calories_kcal": estimated_raw.get("calories_kcal"),
                "protein_g": estimated_raw.get("protein_g"),
                "carbohydrates_g": estimated_raw.get("carbohydrates_g"),
                "fat_g": estimated_raw.get("fat_g"),
                "fiber_g": estimated_raw.get("fiber_g"),
                "sugar_g": estimated_raw.get("sugar_g"),
                "sodium_mg": estimated_raw.get("sodium_mg"),
                "method": estimated_raw.get("method"),
                "assumptions": estimated_raw.get("assumptions") or [],
                "references": [],
                "uncertainty_notes": estimated_raw.get("uncertainty"),
            }

    return {
        "nutrition_id": new_id("nut"),
        "item_id": item_id,
        "variant_id": variant_id,
        "evidence_status": evidence,
        "serving_basis": published.get("serving") or item.get("serving"),
        "published": {
            "calories_kcal": published.get("calories_kcal"),
            "protein_g": published.get("protein_g"),
            "carbohydrates_g": published.get("carbohydrates_g"),
            "fat_g": published.get("fat_g"),
            "fiber_g": published.get("fiber_g"),
            "sugar_g": published.get("sugar_g"),
            "sodium_mg": published.get("sodium_mg"),
        },
        "estimated": estimated,
    }


def _availability(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {"status": "unknown", "meal_periods": [], "days": None}
    if isinstance(raw, dict):
        return {
            "status": raw.get("status") or "unknown",
            "meal_periods": raw.get("meal_periods") or [],
            "days": raw.get("days"),
        }
    # free text note from pilot
    text = str(raw).lower()
    periods = []
    for p in ("breakfast", "lunch", "dinner", "snack"):
        if p in text:
            periods.append(p)
    return {
        "status": "available" if "not confirmed" not in text else "unknown",
        "meal_periods": periods,
        "days": None,
        "raw_note": str(raw),
    }


def map_menu_item(item: dict[str, Any]) -> dict[str, Any]:
    item_id = item.get("dish_id") or new_id("item")
    # normalize dish ids to our prefix style but keep stable
    if not str(item_id).startswith("item_") and not str(item_id).startswith("tb-i-"):
        item_id = f"item_{item_id}"
    variants = _map_variants(item)
    nutrition = _map_nutrition(item, item_id, variants[0]["variant_id"])
    # If multiple variants, attach nutrition only to first (pilot usually has item-level nutrition)
    return {
        "item_id": item_id,
        "restaurant_id": item["restaurant_id"],
        "name": item["name"],
        "raw_name": item["name"],
        "description": item.get("description"),
        "category": item.get("menu_category"),
        "menu_section": item.get("menu_category"),
        "variants": variants,
        "ingredients_published": item.get("ingredients_published"),
        "dietary_claims": _diet_claims(item.get("dietary_labels_published")),
        "allergen_claims": _allergen_claims(item.get("allergens_published")),
        "availability": _availability(item.get("availability")),
        "nutrition": nutrition,
        "ambiguities": (
            ["price_conflict"] if item.get("price_conflict") else []
        )
        + (["needs_review"] if item.get("needs_review") else []),
        "field_sources": {
            "source_ids": item.get("source_ids") or [],
            "last_checked": item.get("last_checked"),
            "price_note": item.get("price_note"),
            "alternate_prices": item.get("alternate_prices") or [],
        },
    }


def import_pilot_json(
    path: Path | None = None,
    *,
    clear_menus: bool = True,
) -> dict[str, int]:
    """Import Claude/Trojan Fork pilot JSON into SQLite."""
    path = path or DEFAULT_PILOT_JSON
    data = json.loads(path.read_text(encoding="utf-8"))
    init_db()

    restaurants = data.get("restaurants") or []
    menu_items = data.get("menu_items") or []
    sources = data.get("sources") or []

    by_rest: dict[str, list[dict[str, Any]]] = {}
    for item in menu_items:
        by_rest.setdefault(item["restaurant_id"], []).append(map_menu_item(item))

    counts = {"restaurants": 0, "menu_items": 0, "sources": 0, "nutrition": 0}

    with session_scope() as session:
        # Sources first (global)
        for src in sources:
            sid = src.get("source_id") or new_id("src")
            # Attach to first restaurant later if needed; store restaurant_id optional
            # Our Source model requires restaurant_id — bind to a sentinel or skip orphans
            # Attach sources to restaurants that reference them after restaurants exist.
            session  # keep linter calm
            _ = sid

        for r in restaurants:
            rid = r["restaurant_id"]
            menu_links = []
            if r.get("menu_url"):
                menu_links.append(
                    {"url": r["menu_url"], "label": "menu", "priority_tier": 1}
                )
            upsert_restaurant(
                session,
                {
                    "restaurant_id": rid,
                    "campus_id": "usc_upc",
                    "university_id": "usc",
                    "name": r["name"],
                    "branch_name": r.get("branch"),
                    "address": {
                        "formatted": r.get("address"),
                        "source": r.get("coordinate_source") or "pilot",
                    },
                    "lat": r.get("latitude"),
                    "lng": r.get("longitude"),
                    "geocode_provider": r.get("coordinate_source") or "pilot_manual",
                    "geocoded_at": datetime.utcnow(),
                    "boundary_status": r.get("boundary_status") or "unknown",
                    "boundary_id": "usc_upc_dps",
                    "boundary_version": "v2025-01",
                    "near_uncertain_edge": (r.get("distance_to_boundary_m") or 9999) <= 150,
                    "categories": [r["service_category"]] if r.get("service_category") else [],
                    "cuisines": [c.lower() for c in (r.get("cuisine") or [])],
                    "website": r.get("website"),
                    "menu_links": menu_links,
                    "business_status": _norm_business_status(r.get("business_status")),
                    "service": {
                        "dine_in": r.get("dine_in"),
                        "takeout": r.get("pickup"),
                        "delivery": r.get("delivery"),
                        "meal_swipe_accepted": None,
                        "is_campus_dining": r.get("is_campus_dining"),
                    },
                },
            )
            counts["restaurants"] += 1

            # restaurant-linked sources
            for src_id in r.get("source_ids") or []:
                src = next((s for s in sources if s.get("source_id") == src_id), None)
                if not src:
                    continue
                upsert_source(
                    session,
                    {
                        "source_id": f"{src_id}__{rid}",
                        "restaurant_id": rid,
                        "url": src.get("url"),
                        "publisher": src.get("publisher"),
                        "source_type": src.get("source_type") or "other_permitted",
                        "priority_tier": 1,
                        "export_allowed": True,
                        "limitations": src.get("limitations"),
                    },
                )
                counts["sources"] += 1

            mapped_items = by_rest.get(rid, [])
            if clear_menus or mapped_items:
                replace_menu_for_restaurant(
                    session,
                    rid,
                    {"menu_items": mapped_items},
                )
            counts["menu_items"] += len(mapped_items)
            counts["nutrition"] += sum(1 for i in mapped_items if i.get("nutrition"))

    return counts


def ensure_pilot_files_in_place(
    src_json: Path | None = None,
    src_md: Path | None = None,
) -> tuple[Path, Path | None]:
    """Move/copy pilot artifacts into data/pilot/ and brand as Trojan Fork."""
    dest_dir = ROOT / "data" / "pilot"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_json = dest_dir / "usc_restaurants.json"
    dest_md = dest_dir / "usc_restaurants.md"

    json_src = src_json or (ROOT / "usc_restaurants.json")
    md_src = src_md or (ROOT / "usc_restaurants.md")

    if json_src.exists():
        raw = json.loads(json_src.read_text(encoding="utf-8"))
        meta = raw.setdefault("metadata", {})
        meta["project"] = "Trojan Fork"
        dest_json.write_text(json.dumps(raw, indent=1) + "\n", encoding="utf-8")
        if json_src.resolve() != dest_json.resolve():
            json_src.unlink()

    if md_src.exists():
        text = md_src.read_text(encoding="utf-8")
        text = re.sub(r"Trojan Bites", "Trojan Fork", text)
        dest_md.write_text(text, encoding="utf-8")
        if md_src.resolve() != dest_md.resolve():
            md_src.unlink()

    return dest_json, dest_md if dest_md.exists() else None
