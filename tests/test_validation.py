from trojanbites_extract.validate.rules import validate_extraction


def test_negative_price_hard_fail():
    result = {
        "menu_items": [
            {
                "name": "Bowl",
                "restaurant_id": "r1",
                "variants": [{"price": {"amount": -1, "currency": "USD"}}],
                "dietary_claims": [],
            }
        ],
        "conflicts": [],
        "ambiguities": [],
    }
    report = validate_extraction(result, restaurant_id="r1")
    assert report.hard_fail


def test_macros_negative_hard_fail():
    result = {
        "menu_items": [
            {
                "name": "Bowl",
                "restaurant_id": "r1",
                "variants": [{"price": {"amount": 10, "currency": "USD"}}],
                "nutrition": {
                    "evidence_status": "restaurant_published",
                    "published": {"protein_g": -5, "calories_kcal": 100},
                },
                "dietary_claims": [],
            }
        ],
        "conflicts": [],
        "ambiguities": [],
    }
    report = validate_extraction(result, restaurant_id="r1")
    assert report.hard_fail


def test_dietary_guarantee_forbidden():
    result = {
        "menu_items": [
            {
                "name": "Bowl",
                "restaurant_id": "r1",
                "variants": [{"price": {"amount": 10, "currency": "USD"}}],
                "dietary_claims": [
                    {
                        "claim": "vegan",
                        "raw_text": "Vegan",
                        "evidence_status": "restaurant_published",
                        "is_guarantee": True,
                    }
                ],
            }
        ],
        "conflicts": [],
        "ambiguities": [],
    }
    report = validate_extraction(result, restaurant_id="r1")
    assert report.hard_fail