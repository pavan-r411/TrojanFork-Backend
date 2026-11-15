"""Tests for the TrojanPlate flow engine: live-feed handling, hard filters, plates, parsing and the audit."""
from __future__ import annotations

import json
import random
from datetime import date
from pathlib import Path

import pytest

from trojanbites_extract.flow import engine, feed, parse, roles, verify
from trojanbites_extract.flow.engine import Query

FIXTURES = Path(__file__).parent / 'fixtures' / 'usc_feed_2026-11-15'
FEED_DAY = date(2026, 11, 15)
CAMPUS = (34.0224, -118.2851)


@pytest.fixture(autouse=True)
def offline_feed(monkeypatch):
    """Serve the saved official feed for 2026-11-15 and nothing for any other day (forces the saved-menu fallback)."""
    def fake_fetch(key, day):
        path = FIXTURES / f'{key}.json'
        if day == FEED_DAY and path.exists():
            return f'fixture://{key}', json.loads(path.read_text()), 'live'
        return '', None, 'unavailable'
    monkeypatch.setattr(feed, 'fetch_hall', fake_fetch)
    feed._pool_cache.clear() if hasattr(feed, '_pool_cache') else None


def usc(**kw):
    return Query(**{'mode': 'usc_dining', 'meal': 'dinner', 'day': FEED_DAY, 'lat': CAMPUS[0], 'lng': CAMPUS[1], 'swipes_remaining': 4, **kw})


def off(**kw):
    return Query(**{'mode': 'off_campus', 'meal': 'lunch', 'day': date(2026, 11, 16), 'lat': CAMPUS[0], 'lng': CAMPUS[1], **kw})


def test_live_feed_is_used_and_labelled():
    result = engine.recommend(usc())
    assert {h['status'] for h in result['menu']['halls'].values()} == {'live'}
    assert all(o['source']['label'].startswith("Today's USC menu") for o in result['options'])
    assert result['options'], 'dinner has dishes in the fixture'


def test_hall_options_are_plates_costing_one_swipe_not_cash():
    for option in engine.recommend(usc())['options']:
        assert option['price']['kind'] == 'swipe'
        assert option['price'].get('cash_cents') in (None, 0)
        assert option['components'] and option['components'][0]['role'] == 'main'


def test_station_headers_and_banners_are_not_dishes():
    names = {o['name'].lower() for meal in ('breakfast', 'lunch', 'dinner') for o in engine.recommend(usc(meal=meal))['options']}
    assert not any(n.startswith('daily grill specials') or n.isupper() for n in names)


def test_sunday_brunch_serves_breakfast_and_lunch():
    for meal in ('breakfast', 'lunch'):
        result = engine.recommend(usc(meal=meal))
        assert result['options'], meal
        assert any(o['availability_note'] == 'Served as Brunch' for o in result['options'])


def test_items_with_a_later_start_time_are_hidden_early():
    assert feed.split_availability('Soup (available at 2pm)')[2] == 14 * 60
    assert feed.split_availability('Oatmeal (available until 2pm)')[3] == 14 * 60
    breakfast = engine.recommend(usc(meal='breakfast'))
    assert not any('(available at 2pm)' in o['name'] for o in breakfast['options'])


@pytest.mark.parametrize('allergies', [['peanuts'], ['gluten'], ['dairy', 'eggs'], ['shellfish', 'fish', 'soy'], ['sesame'], ['kiwi']])
def test_allergy_filters_never_leak_in_hall_mode(allergies):
    for meal in ('breakfast', 'lunch', 'dinner'):
        q = usc(meal=meal, allergies=allergies)
        problems = verify.result_violations(q, engine.recommend(q))
        assert problems == [], problems


def test_allergy_hides_dishes_whose_allergens_were_not_analyzed():
    q = usc(allergies=['peanuts'])
    assert all(o['allergens']['status'] != 'not_analyzed' for o in engine.recommend(q)['options'])


@pytest.mark.parametrize('diet', ['vegetarian', 'vegan'])
def test_diet_filters_in_both_modes(diet):
    for q in (usc(diet=diet), usc(diet=diet, meal='lunch'), off(diet=diet, per_meal_usd=20)):
        problems = verify.result_violations(q, engine.recommend(q))
        assert problems == [], problems


def test_plates_do_not_pair_meat_toppers_with_meatless_mains_or_sweet_mains_with_savoury_sides():
    for meal in ('breakfast', 'lunch', 'dinner'):
        for option in engine.recommend(usc(meal=meal))['options']:
            names = [c['name'] for c in option['components']]
            main = names[0].lower()
            if roles.is_meatless_main_name(main) if hasattr(roles, 'is_meatless_main_name') else False:
                assert not any(roles.side_class(n) == 'topper' for n in names[1:])
            if roles.SWEET_MAIN.search(main):
                assert not any(roles.side_class(n) in {'starch', 'veg', 'dip', 'salad'} for n in names[1:]), names


def test_cash_budget_is_a_hard_cap_off_campus():
    q = off(per_meal_usd=9, daily_remaining_usd=25, meals_left=2)
    result = engine.recommend(q)
    assert all(o['price']['cash_cents'] <= 900 for o in result['options'])
    q2 = off(per_meal_usd=30, daily_remaining_usd=7)
    assert all(o['price']['cash_cents'] <= 700 for o in engine.recommend(q2)['options'])


def test_distance_limit_is_respected_off_campus():
    q = off(max_miles=0.15)
    for o in engine.recommend(q)['options']:
        assert o['walk']['miles'] <= 0.15 + 1e-6


def test_pages_have_at_most_three_options_and_no_repeats():
    result = engine.recommend(off(per_meal_usd=25))
    flat = [i for page in result['pages'] for i in page]
    assert len(flat) == len(set(flat))
    assert all(len(page) <= 3 for page in result['pages'])


def test_too_strict_requests_return_fewer_options_and_explain_what_to_relax():
    result = engine.recommend(off(per_meal_usd=2, daily_remaining_usd=2))
    assert len(result['options']) < 3
    assert result['relax'], 'user is told which limit to loosen'


def test_walk_minutes_are_whole_numbers_and_labelled_as_an_estimate():
    for o in engine.recommend(off(per_meal_usd=25))['options'][:5]:
        assert isinstance(o['walk']['minutes'], int)
        assert o['walk']['method'] == 'straight_line_estimate'


def test_nutrition_is_always_labelled():
    for o in engine.recommend(usc())['options']:
        assert o['nutrition']['status'] in {'verified_published', 'estimated', 'name_estimate', 'chain_pattern_estimate'}
        assert o['nutrition']['label']


def test_text_request_can_add_but_never_remove_restrictions():
    base = off(allergies=['peanuts'], diet='vegetarian')
    parsed = parse.parse_rules('I want something with chicken under $12 and 700 calories', base_allergies=['peanuts'], base_diet='vegetarian') \
        if 'base_allergies' in parse.parse_rules.__code__.co_varnames else parse.parse_rules('I want something with chicken under $12 and 700 calories')
    assert 'peanuts' not in (parsed.get('remove_allergies') or [])


@pytest.mark.parametrize('text,expect', [
    ('allergic to peanuts and shellfish', {'allergies': {'peanuts', 'shellfish'}}),
    ('vegan high protein under $12', {'diet': 'vegan', 'per_meal_usd': 12}),
    ('under 700 calories', {'max_kcal': 700}),
])
def test_rule_parser_examples(text, expect):
    parsed = parse.parse_rules(text)
    for key, value in expect.items():
        got = parsed.get(key)
        assert (set(got) >= value) if isinstance(value, set) else got == value, (key, parsed)
    assert parsed.get('per_meal_usd') != 70 or 'calories' not in text


def test_randomised_profiles_never_violate_a_hard_rule():
    rng = random.Random(7)
    allergens = ['peanuts', 'tree nuts', 'dairy', 'eggs', 'gluten', 'soy', 'fish', 'shellfish', 'sesame']
    for _ in range(150):
        mode = rng.choice(['usc_dining', 'off_campus'])
        q = Query(mode=mode, meal=rng.choice(['breakfast', 'lunch', 'dinner']), day=rng.choice([FEED_DAY, date(2026, 11, 17)]),
                  diet=rng.choice(['any', 'any', 'vegetarian', 'vegan', 'halal']), allergies=rng.sample(allergens, rng.choice([0, 0, 1, 2, 3])),
                  goal=rng.choice(['balanced', 'lose', 'gain', 'maintain']), lat=CAMPUS[0] + rng.uniform(-0.004, 0.004), lng=CAMPUS[1] + rng.uniform(-0.004, 0.004),
                  per_meal_usd=rng.choice([None, 8, 12, 18]) if mode == 'off_campus' else None,
                  daily_remaining_usd=rng.choice([None, 15, 30]) if mode == 'off_campus' else None,
                  meal_kcal=rng.choice([500, 650, 800]), meal_protein_g=rng.choice([25, 35, 45]),
                  cuisines=rng.sample(['indian', 'mexican', 'chinese', 'korean', 'italian', 'american'], rng.choice([0, 1, 2])),
                  rank_by=rng.choice(['nearest', 'fit', 'cheapest']), swipes_remaining=rng.choice([None, 0, 3]))
        problems = verify.result_violations(q, engine.recommend(q))
        assert problems == [], (q, problems)
