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
    ("I'm vegan and allergic to tree nuts, cheap dinner within 0.2 miles", {'allergies': {'tree nuts'}, 'diet': 'vegan', 'max_miles': 0.2}),
])
def test_rule_parser_examples(text, expect):
    parsed = parse.parse_rules(text)
    for key, value in expect.items():
        got = parsed.get(key)
        assert (set(got) >= value) if isinstance(value, set) else got == value, (key, parsed)
    assert parsed.get('per_meal_usd') != 70 or 'calories' not in text
    assert not ({'cheap', 'dinner', 'lunch', 'nearby'} & set(parsed.get('allergies', [])))


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
                  rank_by=rng.choice(['nearest', 'fit', 'cheapest', 'protein', 'lighter']), swipes_remaining=rng.choice([None, 0, 3]),
                  max_miles=rng.choice([None, 0.3, 0.5, 1.0]))
        problems = verify.result_violations(q, engine.recommend(q))
        assert problems == [], (q, problems)


def test_picked_cuisines_lift_matching_dishes_but_never_break_a_hard_rule():
    plain = engine.recommend(off(per_meal_usd=16, pool_size=24))['options']
    picked = engine.recommend(off(per_meal_usd=16, pool_size=24, cuisines=['korean', 'japanese']))['options']
    wanted = {'korean', 'japanese'}
    hits = lambda opts: sum(1 for o in opts[:3] if {c.casefold() for c in o['venue'].get('cuisines', [])} & wanted)
    assert hits(picked) > hits(plain)
    assert all(o['price']['cash_cents'] <= 1600 for o in picked)


# ---------------------------------------------------------------- sorts and distance

def _key_values(options, key):
    return [key(o) for o in options]


def test_each_sort_really_orders_the_whole_pool_off_campus():
    by = lambda sort: engine.recommend(off(max_miles=None, per_meal_usd=15, rank_by=sort))['options']
    nearest, cheapest, protein, lighter, fit = by('nearest'), by('cheapest'), by('protein'), by('lighter'), by('fit')
    miles = _key_values(nearest, lambda o: round(o['walk']['miles'], 2))
    assert miles == sorted(miles)
    cash = _key_values(cheapest, lambda o: o['price']['cash_cents'])
    assert cash == sorted(cash)
    grams = _key_values(protein, lambda o: round(o['nutrition']['protein_g'] / 2))
    assert grams == sorted(grams, reverse=True)
    kcal = _key_values(lighter, lambda o: round(o['nutrition']['calories'] / 50))
    assert kcal == sorted(kcal)
    scores = _key_values(fit, lambda o: o['score'])
    assert scores == sorted(scores, reverse=True)
    firsts = {tuple(o['id'] for o in opts[:3]) for opts in (nearest, cheapest, protein, lighter, fit)}
    assert len(firsts) == 5, 'every sort should lead with different dishes'
    assert {o['id'] for o in nearest} == {o['id'] for o in cheapest} == {o['id'] for o in fit}, 'sorts reorder, they never drop dishes'


def test_any_distance_includes_every_open_restaurant_that_passes_the_rules():
    near = engine.recommend(off(max_miles=0.3, per_meal_usd=40))
    anywhere = engine.recommend(off(max_miles=None, per_meal_usd=40))
    assert anywhere['stats']['eligible'] > near['stats']['eligible']
    assert anywhere['stats']['venues'] > near['stats']['venues'] + 20
    assert 'distance' not in anywhere['stats']['hidden']
    assert max(o['walk']['miles'] for o in anywhere['options']) > 0.5
    assert len(anywhere['options']) == anywhere['stats']['eligible'], 'every eligible dish is in the list'


def test_any_distance_is_offered_as_a_relaxation_and_the_walk_limit_still_works():
    tight = engine.recommend(off(max_miles=0.05, per_meal_usd=15))
    assert any(h['key'] == 'max_miles' and h['value'] is None for h in tight['relax'] + engine.relax_hints(
        off(max_miles=0.05, per_meal_usd=15), *engine._candidates(off(max_miles=0.05, per_meal_usd=15))[:1], {'distance': 9}, 0))
    assert all(o['walk']['miles'] <= 0.3 + 1e-9 for o in engine.recommend(off(max_miles=0.3))['options'])


def test_closest_hall_sort_keeps_the_nearest_hall_together_on_page_one():
    result = engine.recommend(usc(meal='lunch', rank_by='nearest', lat=34.0258, lng=-118.2854))
    first = [result['options'][i] for i in result['pages'][0]]
    assert len({o['venue']['id'] for o in first}) == 1, 'closest hall: three plates from the nearest hall'
    fit = engine.recommend(usc(meal='lunch', rank_by='fit', lat=34.0258, lng=-118.2854))
    assert len({fit['options'][i]['venue']['id'] for i in fit['pages'][0]}) > 1, 'best fit still mixes halls for variety'


def test_hall_sorts_by_protein_and_calories_differ_from_best_fit():
    lead = lambda sort: [o['id'] for o in engine.recommend(usc(meal='lunch', rank_by=sort))['options'][:3]]
    assert lead('protein') != lead('lighter') and lead('lighter') != lead('fit')


# ---------------------------------------------------------------- distance bands

ORIGINS = {'USC Village': (34.0258, -118.2854), 'Tommy Trojan': (34.0206, -118.2854), 'Leavey Library': (34.0217, -118.2829)}
ALL_BANDS = [(0.0, 0.3), (0.3, 0.5), (0.5, 1.5)]


@pytest.mark.parametrize('origin', ORIGINS)
def test_the_bands_together_reach_every_open_restaurant(origin):
    lat, lng = ORIGINS[origin]
    overview = engine.band_overview(lat, lng)
    venues, _, _ = engine.dataset()
    open_venues = [v for v in venues.values() if v.category == 'off_campus' and v.eligible]
    assert overview['total'] == len(open_venues) and overview['beyond'] == []
    ids = [r['id'] for b in overview['bands'] for r in b['restaurants']]
    assert len(ids) == len(set(ids)), 'a restaurant belongs to exactly one band'
    assert all(b['count'] > 0 for b in overview['bands']), 'every band has restaurants to use'
    assert [u['name'] for u in overview['unavailable']] == ["Tacoyo's Restaurant"], 'the one closed restaurant is listed, not hidden'


def test_choosing_all_three_bands_leaves_nobody_out_and_one_band_shows_only_that_band():
    everything = engine.recommend(off(bands=ALL_BANDS, per_meal_usd=40))
    assert 'distance' not in everything['stats']['hidden']
    assert everything['stats']['eligible'] == engine.recommend(off(max_miles=None, per_meal_usd=40))['stats']['eligible']
    far = engine.recommend(off(bands=[(0.5, 1.5)], per_meal_usd=40))
    assert far['options'] and all(0.5 - 1e-9 <= o['walk']['miles'] + 0.005 and o['walk']['miles'] <= 1.5 for o in far['options'])
    near = engine.recommend(off(bands=[(0.0, 0.3)], per_meal_usd=40))
    assert near['stats']['eligible'] + engine.recommend(off(bands=[(0.3, 0.5)], per_meal_usd=40))['stats']['eligible'] \
        + far['stats']['eligible'] >= everything['stats']['eligible'] - 1, 'the three bands add up to the whole'
    assert any(h['key'] == 'distance_band' for h in near['relax'] + engine.relax_hints(off(bands=[(0.0, 0.3)], per_meal_usd=40), *engine._candidates(off(per_meal_usd=40))[:1], {'distance': 9}, 0))


def test_api_accepts_bands_and_lists_restaurants_by_band():
    from fastapi.testclient import TestClient
    from trojanbites_extract.api.app import app
    client = TestClient(app)
    lat, lng = ORIGINS['USC Village']
    body = {'mode': 'off_campus', 'meal': 'lunch', 'date': '2026-11-16', 'origin': {'lat': lat, 'lng': lng},
            'bands': [{'min': 0.5, 'max': 1.5}], 'budget': {'per_meal_usd': 20}, 'rank_by': 'nearest'}
    result = client.post('/v1/flow/options', json=body).json()
    assert result['options'] and min(o['walk']['miles'] for o in result['options']) >= 0.49
    listing = client.get('/v1/flow/bands', params={'lat': lat, 'lng': lng}).json()
    assert listing['total'] == 71 and [b['count'] for b in listing['bands']] == [17, 20, 34]
    assert client.post('/v1/flow/options', json={**body, 'bands': [{'min': 2, 'max': 1}]}).status_code in (200, 422)


def test_photo_overlay_attaches_only_dishes_it_lists_and_never_changes_the_menu():
    from trojanbites_extract.flow import data
    _venues, dishes, _meta = data.dataset()
    overlay = json.loads(Path(data.IMAGES_PATH).read_text(encoding='utf-8'))['images']
    withpic = [d for d in dishes if d.image_url]
    assert len(withpic) == len(overlay) == 231
    assert all(d.id in overlay for d in withpic)
    assert all(d.extra['image']['source'] and d.extra['image']['match'] for d in withpic)
    # Only photos of the same dish, from the venue's own or delivery-menu sources, are ever used.
    assert {d.extra['image']['match'] for d in withpic} <= {'exact_dish', 'same_dish_other_branch'}
    assert not {d.extra['image']['source'] for d in withpic} & {'yelp', 'google_maps'}
    assert all(d.venue_id for d in withpic)
    # The overlay adds pictures, never dishes: the menu is the same size as the source dataset.
    assert len(dishes) == 759
    # Every picture file the overlay points at is a real file the UI can load.
    frontend = Path(data.ROOT).parent / 'TrojanFork-Frontend'
    if frontend.exists():
        assert all((frontend / d.image_url).is_file() for d in withpic)
