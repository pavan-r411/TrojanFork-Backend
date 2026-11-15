from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from trojanbites_extract.ids import new_id
from trojanbites_extract.store.models import (
    MenuItem,
    MenuVariant,
    Nutrition,
    Restaurant,
    Source,
)


def upsert_restaurant(session: Session, data: dict[str, Any]) -> Restaurant:
    rid = data["restaurant_id"]
    row = session.get(Restaurant, rid)
    if row is None:
        row = Restaurant(restaurant_id=rid, name=data["name"])
        session.add(row)
    row.name = data["name"]
    if data.get("campus_id") is not None:
        row.campus_id = data.get("campus_id")
    if data.get("university_id") is not None:
        row.university_id = data.get("university_id")
    row.branch_name = data.get("branch_name")
    row.address_json = data.get("address") or {}
    row.lat = data.get("lat")
    row.lng = data.get("lng")
    row.geocode_provider = data.get("geocode_provider")
    row.geocoded_at = data.get("geocoded_at")
    row.boundary_status = data.get("boundary_status", "unknown")
    row.boundary_id = data.get("boundary_id")
    row.boundary_version = data.get("boundary_version")
    row.near_uncertain_edge = bool(data.get("near_uncertain_edge", False))
    row.categories_json = data.get("categories") or []
    row.cuisines_json = data.get("cuisines") or []
    row.website = data.get("website")
    row.menu_links_json = data.get("menu_links") or []
    row.business_status = data.get("business_status", "unknown")
    row.service_json = data.get("service") or {}
    row.updated_at = datetime.utcnow()
    return row


def upsert_source(session: Session, data: dict[str, Any]) -> Source:
    sid = data.get("source_id") or new_id("src")
    row = session.get(Source, sid)
    if row is None:
        row = Source(source_id=sid, restaurant_id=data["restaurant_id"], source_type=data["source_type"])
        session.add(row)
    row.restaurant_id = data["restaurant_id"]
    row.url = data.get("url")
    row.publisher = data.get("publisher")
    row.source_type = data["source_type"]
    row.content_hash = data.get("content_hash")
    row.retention_class = data.get("retention_class", "retain_exportable")
    row.export_allowed = bool(data.get("export_allowed", True))
    row.limitations = data.get("limitations")
    row.priority_tier = int(data.get("priority_tier", 5))
    row.retrieved_at = data.get("retrieved_at") or datetime.utcnow()
    return row


def replace_menu_for_restaurant(
    session: Session, restaurant_id: str, extraction: dict[str, Any]
) -> None:
    """Idempotent replace of active menu items for a restaurant from one extraction."""
    existing_items = (
        session.query(MenuItem).filter(MenuItem.restaurant_id == restaurant_id).all()
    )
    for item in existing_items:
        for variant in list(item.variants):
            if variant.nutrition:
                session.delete(variant.nutrition)
            session.delete(variant)
        session.delete(item)
    session.flush()

    for item in extraction.get("menu_items") or []:
        mi = MenuItem(
            item_id=item.get("item_id") or new_id("item"),
            restaurant_id=restaurant_id,
            name=item["name"],
            raw_name=item.get("raw_name") or item["name"],
            description=item.get("description"),
            category=item.get("category"),
            menu_section=item.get("menu_section"),
            ingredients_json=item.get("ingredients_published"),
            dietary_claims_json=item.get("dietary_claims") or [],
            allergen_claims_json=item.get("allergen_claims") or [],
            availability_json=item.get("availability")
            or {"status": "unknown", "meal_periods": []},
            ambiguities_json=item.get("ambiguities") or [],
            field_sources_json=item.get("field_sources") or {},
            available=True,
        )
        session.add(mi)
        for variant in item.get("variants") or []:
            mv = MenuVariant(
                variant_id=variant.get("variant_id") or new_id("var"),
                item_id=mi.item_id,
                size_label=variant.get("size_label"),
                serving_label=variant.get("serving_label"),
                price_amount=(variant.get("price") or {}).get("amount"),
                currency=(variant.get("price") or {}).get("currency") or "USD",
                addons_json=variant.get("addons") or [],
            )
            session.add(mv)
            nut = item.get("nutrition")
            # Attach nutrition to first variant if variant_id matches or only one variant
            if nut and (
                nut.get("variant_id") in (None, mv.variant_id)
                or len(item.get("variants") or []) == 1
            ):
                published = nut.get("published") or {}
                session.add(
                    Nutrition(
                        nutrition_id=nut.get("nutrition_id") or new_id("nut"),
                        item_id=mi.item_id,
                        variant_id=mv.variant_id,
                        evidence_status=nut.get("evidence_status") or "unknown",
                        serving_basis=nut.get("serving_basis"),
                        calories_kcal=published.get("calories_kcal"),
                        protein_g=published.get("protein_g"),
                        carbohydrates_g=published.get("carbohydrates_g"),
                        fat_g=published.get("fat_g"),
                        fiber_g=published.get("fiber_g"),
                        sugar_g=published.get("sugar_g"),
                        sodium_mg=published.get("sodium_mg"),
                        estimated_json=nut.get("estimated"),
                        field_sources_json=nut.get("field_sources") or {},
                    )
                )
    session.flush()