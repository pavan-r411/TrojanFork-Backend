from trojanbites_extract.extract.merge import merge_extractions
from trojanbites_extract.query.filters import MealQuery, filter_meals
from trojanbites_extract.store.db import init_db, session_scope
from trojanbites_extract.store.upserts import replace_menu_for_restaurant, upsert_restaurant


def test_merge_price_conflict_nulls():
    a = {
        "menu_items": [
            {
                "name": "Tofu Bowl",
                "menu_section": "Lunch",
                "variants": [{"size_label": "Regular", "price": {"amount": 11.5, "currency": "USD"}}],
            }
        ],
        "conflicts": [],
        "ambiguities": [],
    }
    b = {
        "menu_items": [
            {
                "name": "Tofu Bowl",
                "menu_section": "Lunch",
                "variants": [{"size_label": "Regular", "price": {"amount": 12.0, "currency": "USD"}}],
            }
        ],
        "conflicts": [],
        "ambiguities": [],
    }
    merged = merge_extractions(a, b)
    assert any("price_conflict" in c for c in merged["conflicts"])
    assert merged["menu_items"][0]["variants"][0]["price"]["amount"] is None


def test_strict_protein_filter_excludes_missing_macros(tmp_path, monkeypatch):
    db_url = f"sqlite:///{tmp_path / 't.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    # bypass cached settings
    from trojanbites_extract import settings as settings_mod

    settings_mod.get_settings.cache_clear()
    init_db(db_url)
    with session_scope() as session:
        upsert_restaurant(
            session,
            {
                "restaurant_id": "rest_test_1",
                "name": "Test",
                "boundary_status": "inside",
                "boundary_id": "usc_upc_dps",
                "boundary_version": "v2025-01",
                "cuisines": ["american"],
                "categories": [],
                "menu_links": [],
                "business_status": "operational",
            },
        )
        replace_menu_for_restaurant(
            session,
            "rest_test_1",
            {
                "menu_items": [
                    {
                        "item_id": "item_1",
                        "name": "Mystery Bowl",
                        "variants": [
                            {
                                "variant_id": "var_1",
                                "price": {"amount": 10, "currency": "USD"},
                            }
                        ],
                        "dietary_claims": [
                            {
                                "claim": "vegetarian",
                                "raw_text": "Vegetarian",
                                "evidence_status": "restaurant_published",
                                "is_guarantee": False,
                            }
                        ],
                        "availability": {"status": "available", "meal_periods": ["lunch"]},
                        "nutrition": None,
                    },
                    {
                        "item_id": "item_2",
                        "name": "Protein Bowl",
                        "variants": [
                            {
                                "variant_id": "var_2",
                                "price": {"amount": 11, "currency": "USD"},
                            }
                        ],
                        "dietary_claims": [
                            {
                                "claim": "vegetarian",
                                "raw_text": "Vegetarian",
                                "evidence_status": "restaurant_published",
                                "is_guarantee": False,
                            }
                        ],
                        "availability": {"status": "available", "meal_periods": ["lunch"]},
                        "nutrition": {
                            "nutrition_id": "nut_2",
                            "item_id": "item_2",
                            "variant_id": "var_2",
                            "evidence_status": "restaurant_published",
                            "serving_basis": "1 bowl",
                            "published": {
                                "calories_kcal": 500,
                                "protein_g": 28,
                                "carbohydrates_g": 60,
                                "fat_g": 15,
                                "fiber_g": 8,
                                "sugar_g": 6,
                                "sodium_mg": 700,
                            },
                            "estimated": None,
                        },
                    },
                ]
            },
        )
        hits = filter_meals(
            session,
            MealQuery(
                budget_max=12,
                diet_claims_required=["vegetarian"],
                min_published_protein_g=25,
                meal_period="lunch",
                strict=True,
            ),
        )
    assert len(hits) == 1
    assert hits[0].item_name == "Protein Bowl"
    assert hits[0].published_protein_g == 28