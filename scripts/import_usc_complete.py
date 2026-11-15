#!/usr/bin/env python3
"""Convert restaurants_usc_complete.json into TrojanPlate menu snapshots.

Keeps published vs estimated nutrition separate. Does not invent dishes.
Writes:
  data/menus/off_campus/curated_usc_complete.json
  data/menus/usc_dining/<today>/snapshot.json  (from usc_dining category only)
Also copies the off-campus file over curated_upc_0_3mi.json so live supplement
and plan/day pick it up without code changes.
"""
from __future__ import annotations

import json
import math
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "restaurants_usc_complete.json"
OFF_OUT = ROOT / "data" / "menus" / "off_campus" / "curated_usc_complete.json"
OFF_ACTIVE = ROOT / "data" / "menus" / "off_campus" / "curated_upc_0_3mi.json"
TOMMY = (34.0224, -118.2851)


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _diet_labels(compat: dict | None, dish: dict) -> list[str]:
    labels: list[str] = []
    c = compat or {}
    if c.get("is_vegan"):
        labels.append("vegan")
    if c.get("is_vegetarian"):
        labels.append("vegetarian")
    if c.get("is_gluten_free"):
        labels.append("gluten-free")
    if c.get("is_dairy_free"):
        labels.append("dairy-free")
    if c.get("halal_status") == "halal":
        labels.append("halal")
    for tag in dish.get("goal_tags") or []:
        if isinstance(tag, str) and tag.strip():
            labels.append(tag.strip().lower())
    return sorted(set(labels))


def _nutrition_block(dish: dict) -> dict:
    raw = dish.get("nutrition_per_serving") or {}
    macros = {
        "serving": (dish.get("serving") or {}).get("serving_unit"),
        "calories_kcal": raw.get("calories_kcal"),
        "protein_g": raw.get("protein_g"),
        "carbohydrates_g": raw.get("carbohydrates_g"),
        "fat_g": raw.get("total_fat_g"),
        "fiber_g": raw.get("fiber_g"),
        "sugar_g": raw.get("sugar_g"),
        "sodium_mg": raw.get("sodium_mg"),
        "note": None,
    }
    source = str(dish.get("nutrition_source") or "estimated").lower()
    published_like = source in {
        "published_by_chain",
        "published",
        "restaurant_published",
        "usc_published",
    } or "published" in source
    if published_like:
        return {"confidence": "confirmed", "published": macros, "estimated": None}
    # Estimated stays labeled — never silently treated as published.
    return {
        "confidence": "estimated",
        "published": {k: None for k in macros},
        "estimated": macros,
        "estimation_note": (
            f"Source={dish.get('nutrition_source')}; "
            f"confidence={dish.get('nutrition_confidence_0_to_1')}; "
            "not restaurant-verified medical nutrition."
        ),
    }


def _ingredients(dish: dict) -> list[str]:
    out = []
    for item in dish.get("ingredients") or []:
        if isinstance(item, dict) and item.get("name"):
            out.append(str(item["name"]))
        elif isinstance(item, str):
            out.append(item)
    if not out and dish.get("ingredients_text"):
        out = [x.strip() for x in str(dish["ingredients_text"]).split(",") if x.strip()]
    return out


def convert(src: dict) -> tuple[dict, dict]:
    meta = src.get("metadata") or {}
    ref = meta.get("reference_point") or {}
    pin_lat = float(ref.get("latitude") or TOMMY[0])
    pin_lng = float(ref.get("longitude") or TOMMY[1])
    now = datetime.now(timezone.utc).isoformat()

    off_venues, off_dishes = [], []
    usc_venues, usc_dishes = [], []

    for rest in src.get("restaurants") or []:
        loc = rest.get("location") or {}
        lat = loc.get("latitude")
        lng = loc.get("longitude")
        category = rest.get("category") or "off_campus"
        # USC Hospitality retail cafes often omit coords in the seed file; pin them to
        # campus center so they remain selectable with an honest location note.
        coords_provisional = False
        if lat is None or lng is None:
            if category != "usc_dining":
                continue
            lat, lng = pin_lat, pin_lng
            coords_provisional = True
        lat, lng = float(lat), float(lng)
        vid = str(rest.get("restaurant_id") or f"rest-{len(off_venues)+len(usc_venues)}")
        name = rest.get("restaurant_name") or vid
        contact = rest.get("contact") or {}
        address = loc.get("formatted_address")
        distance = round(haversine_miles(pin_lat, pin_lng, lat, lng), 3)
        usc_spec = rest.get("usc_dining_specific") or {}
        subcategory = rest.get("usc_subcategory") or ""
        ayce = bool(usc_spec.get("all_you_care_to_eat")) or subcategory == "residential_dining_hall"
        # Only residential AYCE halls burn a meal swipe; USC retail/restaurants are cash / Dining Dollars.
        if category == "usc_dining" and ayce:
            payment_model = "meal_swipe_ayce"
            venue_type = "usc_dining_hall"
        elif category == "usc_dining":
            payment_model = "dining_dollars_or_cash"
            venue_type = "usc_retail"
        else:
            payment_model = "cash_card"
            venue_type = "off_campus_restaurant"
        venue = {
            "venue_id": vid,
            "name": name,
            "branch": loc.get("building") or subcategory or None,
            "lat": lat,
            "lng": lng,
            "address": address,
            "formatted_address": address,
            "place_id": contact.get("google_place_id") or contact.get("place_id"),
            "distance_miles_from_tommy_trojan": distance,
            "cuisines": list(rest.get("cuisines") or []),
            "website": contact.get("website") or contact.get("menu_url"),
            "menu_url": contact.get("menu_url") or contact.get("website"),
            "source_ids": [f"usc-complete:{vid}"],
            "venue_type": venue_type,
            "payment_model": payment_model,
            "usc_subcategory": subcategory or None,
            "hours": rest.get("opening_hours"),
            "dataset_category": category,
            "coords_provisional": coords_provisional,
            "location_note": (
                "Coordinates approximated to USC UPC reference point; verify entrance."
                if coords_provisional
                else None
            ),
        }
        target_venues = usc_venues if category == "usc_dining" else off_venues
        target_dishes = usc_dishes if category == "usc_dining" else off_dishes
        target_venues.append(venue)

        for dish in rest.get("dishes") or []:
            price = dish.get("price") or {}
            amount = price.get("amount_usd")
            periods = [str(p).lower() for p in (dish.get("meal_times") or []) if p]
            # dessert is not a planner slot; keep as snack-adjacent signal only
            periods = [p if p != "dessert" else "snack" for p in periods]
            evidence = dish.get("menu_evidence")
            nutrition = _nutrition_block(dish)
            # Live supplement currently only reads published macros. Keep published
            # macros for published sources; estimated stay in estimated only.
            row = {
                "dish_id": dish.get("dish_id") or f"{vid}-{len(target_dishes)}",
                "venue_id": vid,
                "venue_name": name,
                "name": dish.get("dish_name") or dish.get("name"),
                "description": dish.get("description"),
                "meal_periods": periods,
                "price_amount": float(amount) if amount is not None else None,
                "currency": price.get("currency") or "USD",
                "price_basis": "menu_price_excludes_tax_and_fees",
                "price_source": price.get("price_source"),
                "pricing_model": price.get("pricing_model"),
                "payment_model": venue["payment_model"],
                "cuisines": list(rest.get("cuisines") or []),
                "dietary_labels": _diet_labels(dish.get("dietary_compatibility"), dish),
                "allergens_published": list(dish.get("allergens_contains") or []),
                "ingredients_published": _ingredients(dish),
                "nutrition": nutrition,
                "nutrition_source": dish.get("nutrition_source"),
                "menu_evidence": evidence,
                "availability": dish.get("availability"),
                "source_ids": [f"usc-complete:{dish.get('dish_id')}"],
                "lat": lat,
                "lng": lng,
            }
            if row["name"]:
                target_dishes.append(row)

    shared_meta = {
        "product": "TrojanPlate",
        "imported_from": "restaurants_usc_complete.json",
        "dataset_version": meta.get("version"),
        "generated_at": meta.get("generated_at"),
        "imported_at": now,
        "demo_pin": {"label": ref.get("name") or "USC UPC", "lat": pin_lat, "lng": pin_lng},
        "default_max_miles": float(meta.get("radius_miles") or 1.0),
        "distance_metric": "haversine_miles_straight_line",
        "record_policy": (
            "Imported seed DB. Published nutrition only when nutrition_source is published*; "
            "otherwise macros are estimated and labeled. Prices exclude tax/fees. "
            "Null means unknown."
        ),
        "nutrition_disclaimer": meta.get("nutrition_disclaimer"),
        "price_disclaimer": meta.get("price_disclaimer"),
        "coverage_note": meta.get("coverage_note_v6"),
        "counts": {
            "restaurants_total": meta.get("counts", {}).get("restaurants_total"),
            "source_dishes_total": meta.get("counts", {}).get("dishes_total"),
        },
    }

    off = {
        "metadata": {
            **shared_meta,
            "mode": "off_campus",
            "version": "usc-complete-off-campus",
            "venues_count": len(off_venues),
            "dishes_count": len(off_dishes),
        },
        "venues": off_venues,
        "dishes": off_dishes,
    }
    usc = {
        "metadata": {
            **shared_meta,
            "mode": "usc_dining",
            "menu_date": date.today().isoformat(),
            "version": "usc-complete-dining",
            "venues_count": len(usc_venues),
            "dishes_count": len(usc_dishes),
        },
        "venues": usc_venues,
        "dishes": usc_dishes,
    }
    return off, usc


def main() -> None:
    src = json.loads(SRC.read_text(encoding="utf-8"))
    off, usc = convert(src)
    OFF_OUT.parent.mkdir(parents=True, exist_ok=True)
    OFF_OUT.write_text(json.dumps(off, indent=2), encoding="utf-8")
    # Keep previous curated file as backup once.
    if OFF_ACTIVE.exists() and not (OFF_ACTIVE.parent / "curated_upc_0_3mi.prev.json").exists():
        shutil.copy2(OFF_ACTIVE, OFF_ACTIVE.parent / "curated_upc_0_3mi.prev.json")
    shutil.copy2(OFF_OUT, OFF_ACTIVE)

    day = date.today().isoformat()
    usc_dir = ROOT / "data" / "menus" / "usc_dining" / day
    usc_dir.mkdir(parents=True, exist_ok=True)
    (usc_dir / "snapshot.json").write_text(json.dumps(usc, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "source": str(SRC.name),
                "off_campus": {
                    "path": str(OFF_ACTIVE.relative_to(ROOT)),
                    "venues": len(off["venues"]),
                    "dishes": len(off["dishes"]),
                    "with_published_macros": sum(
                        1
                        for d in off["dishes"]
                        if (d.get("nutrition") or {}).get("confidence") == "confirmed"
                    ),
                    "with_estimated_macros": sum(
                        1
                        for d in off["dishes"]
                        if (d.get("nutrition") or {}).get("confidence") == "estimated"
                    ),
                    "priced": sum(1 for d in off["dishes"] if d.get("price_amount") is not None),
                    "breakfast_tagged": sum(
                        1 for d in off["dishes"] if "breakfast" in (d.get("meal_periods") or [])
                    ),
                },
                "usc_dining": {
                    "path": str((usc_dir / "snapshot.json").relative_to(ROOT)),
                    "venues": len(usc["venues"]),
                    "dishes": len(usc["dishes"]),
                    "breakfast_tagged": sum(
                        1 for d in usc["dishes"] if "breakfast" in (d.get("meal_periods") or [])
                    ),
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
