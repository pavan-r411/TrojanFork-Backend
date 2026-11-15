from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session, joinedload

from trojanbites_extract.settings import load_extraction_config
from trojanbites_extract.store.models import MenuItem, MenuVariant, Restaurant, Source


def build_canonical_snapshot(session: Session) -> dict[str, Any]:
    cfg = load_extraction_config()
    restaurants = session.query(Restaurant).all()
    items = (
        session.query(MenuItem)
        .options(joinedload(MenuItem.variants).joinedload(MenuVariant.nutrition))
        .all()
    )
    sources = session.query(Source).filter(Source.export_allowed.is_(True)).all()

    rest_out = []
    in_boundary = 0
    with_menu = set()
    with_pub_nut = 0

    for r in restaurants:
        if r.boundary_status in {"inside", "boundary"}:
            in_boundary += 1
        rest_out.append(
            {
                "restaurant_id": r.restaurant_id,
                "provider_refs": {
                    # place ids only — no Places display payload
                },
                "name": r.name,
                "branch_name": r.branch_name,
                "address": r.address_json,
                "coordinates": {
                    "lat": r.lat,
                    "lng": r.lng,
                    "geocode_provider": r.geocode_provider,
                    "geocoded_at": r.geocoded_at.isoformat() if r.geocoded_at else None,
                }
                if r.lat is not None and r.lng is not None
                else None,
                "boundary": {
                    "status": r.boundary_status,
                    "boundary_id": r.boundary_id,
                    "boundary_version": r.boundary_version,
                    "near_uncertain_edge": r.near_uncertain_edge,
                },
                "categories": r.categories_json,
                "cuisines": r.cuisines_json,
                "website": r.website,
                "menu_links": r.menu_links_json,
                "business_status": r.business_status,
                "service": r.service_json,
                "export_restrictions": ["omit_runtime_google_places_display_fields"],
            }
        )

    menu_out = []
    nutrition_out = []
    for item in items:
        with_menu.add(item.restaurant_id)
        variants_out = []
        for v in item.variants:
            variants_out.append(
                {
                    "variant_id": v.variant_id,
                    "size_label": v.size_label,
                    "serving_label": v.serving_label,
                    "price": {"amount": v.price_amount, "currency": v.currency},
                    "addons": v.addons_json,
                }
            )
            if v.nutrition:
                n = v.nutrition
                if n.evidence_status == "restaurant_published" and n.protein_g is not None:
                    with_pub_nut += 1
                nutrition_out.append(
                    {
                        "nutrition_id": n.nutrition_id,
                        "item_id": n.item_id,
                        "variant_id": n.variant_id,
                        "evidence_status": n.evidence_status,
                        "serving_basis": n.serving_basis,
                        "published": {
                            "calories_kcal": n.calories_kcal,
                            "protein_g": n.protein_g,
                            "carbohydrates_g": n.carbohydrates_g,
                            "fat_g": n.fat_g,
                            "fiber_g": n.fiber_g,
                            "sugar_g": n.sugar_g,
                            "sodium_mg": n.sodium_mg,
                        },
                        "estimated": n.estimated_json,
                    }
                )
        menu_out.append(
            {
                "item_id": item.item_id,
                "restaurant_id": item.restaurant_id,
                "name": item.name,
                "raw_name": item.raw_name,
                "description": item.description,
                "category": item.category,
                "menu_section": item.menu_section,
                "variants": variants_out,
                "ingredients_published": item.ingredients_json,
                "dietary_claims": item.dietary_claims_json,
                "allergen_claims": item.allergen_claims_json,
                "availability": item.availability_json,
                "ambiguities": item.ambiguities_json,
            }
        )

    return {
        "meta": {
            "product": cfg.get("product_name", "Trojan Fork"),
            "campus_id": cfg.get("campus_id"),
            "boundary_id": cfg.get("boundary_id"),
            "boundary_version": cfg.get("boundary_version"),
            "boundary_source_url": "https://dps.usc.edu/patrol/",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "methodology": (
                "Boundary verification → seed/Places discovery → permitted retrieval → "
                "parse/OCR → deterministic+Claude extraction → validation → storage → export. "
                "Unknown values remain null. Nutrition macros are restaurant-published only "
                "unless estimation is explicitly enabled."
            ),
            "limitations": [
                "Places display fields omitted per Google Maps Platform terms",
                "Boundary GeoJSON is a street-intersection approximation of the DPS narrative",
                "Nutrition estimation disabled by default",
                "Dietary/allergen claims are restaurant-published, not guarantees",
            ],
            "coverage": {
                "restaurants_total": len(restaurants),
                "restaurants_in_boundary": in_boundary,
                "with_menu": len(with_menu),
                "menu_items": len(menu_out),
                "nutrition_records": len(nutrition_out),
                "with_published_protein_samples": with_pub_nut,
            },
            "macros_fields": [
                "calories_kcal",
                "protein_g",
                "carbohydrates_g",
                "fat_g",
                "fiber_g",
                "sugar_g",
                "sodium_mg",
            ],
        },
        "restaurants": rest_out,
        "menu_items": menu_out,
        "nutrition": nutrition_out,
        "sources": [
            {
                "source_id": s.source_id,
                "restaurant_id": s.restaurant_id,
                "url": s.url,
                "publisher": s.publisher,
                "source_type": s.source_type,
                "retrieved_at": s.retrieved_at.isoformat() if s.retrieved_at else None,
                "limitations": s.limitations,
                "priority_tier": s.priority_tier,
            }
            for s in sources
        ],
    }


def write_json_export(session: Session, out_path: Path) -> Path:
    snapshot = build_canonical_snapshot(session)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    return out_path