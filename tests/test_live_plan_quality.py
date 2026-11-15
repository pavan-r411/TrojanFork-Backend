"""Live plan behaviour against the real shape of USC's feed (captured 2026-11-15) and flaky restaurant sites."""
from dataclasses import asdict
from datetime import date
from types import SimpleNamespace
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from trojanbites_extract.api.app import app
from trojanbites_extract.recommend import frontend, live, web
from trojanbites_extract.recommend.service import RecommendationResult


def item(name, allergens=(), preferences=(), labels=()):
    return {'item':name,'dietary_preferences':list(labels),'allergens':list(allergens),'preferences':list(preferences)}


FEED={'date':'20261115','location':'parkside-restaurant-grill','meals':[
    {'name':'Breakfast'},
    {'name':'Brunch','stations':[
        {'station':'Pizza/Salad Bar','subtitle':'','menu':[item('SALAD AND DELI BAR'),item('Assorted Fruits',preferences=['halal-ingredients','vegan']),
            item('PIZZA AVAILABLE AT 11 AM'),item('Cheese Pizza',['dairy','soy','gluten'],['halal-ingredients','vegetarian']),
            item('Grape Jelly',preferences=['vegan']),item('Plain Cream Cheese',['dairy'],['vegetarian'])]},
        {'station':'Eurasia','subtitle':'','menu':[item('Scrambled Eggs',['eggs'],['vegetarian']),item('Chicken Sausage Link',preferences=['halal-ingredients']),
            item('Roasted Jackfruit with Mango Salsa',preferences=['vegan']),item('Sliced Mushrooms',preferences=['vegan']),
            item('Daily Grill Specials (including Veggie Burgers)',['not-analyzed'],labels=['Food Not Analyzed for Allergens'])]},
        {'station':'Allergen Awareness Zone','subtitle':'must register for access','menu':[item('AAZ Steamed Millet',preferences=['vegan'])]}]},
    {'name':'Lunch'},
    {'name':'Dinner','stations':[{'station':'Bistro','subtitle':'','menu':[item('MEXICAN STREET CORN AND BARBACOA BAR'),
        item('Mexican Street Corn Bowl with Barbacoa Beef',['soy']),item('Cotija Cheese',['dairy'],['vegetarian']),
        item('Sauteed Chipotle Butter Shrimp',['dairy','shellfish'],['halal-ingredients']),item('Spanish Rice',preferences=['vegan'])]}]}]}


@pytest.fixture
def usc(monkeypatch):
    monkeypatch.setattr(live,'fetch_page',lambda url:web.Page(url,json.dumps(FEED),[]))
    first_three=lambda hits,*a,**kw:RecommendationResult(provider='openai',status='completed',meals=[asdict(h) for h in hits[:3]])
    monkeypatch.setattr(live,'select_meals',first_three)
    monkeypatch.setattr(frontend,'select_meals',first_three)


def usc_request(period='breakfast',**preferences):
    return live.LiveRequest(mode='usc_dining',date='2026-11-15',meal_period=period,dining_hall='parkside',preferences=preferences)


def names(hits): return [hit.item_name for hit in hits]


def test_usc_feed_keeps_dishes_and_drops_headers_condiments_and_registered_station(usc):
    hits,sources,notes=live._usc(usc_request())
    assert set(names(hits))=={'Assorted Fruits','Cheese Pizza','Scrambled Eggs','Chicken Sausage Link','Roasted Jackfruit with Mango Salsa',
        'Daily Grill Specials (including Veggie Burgers)'}
    assert names(hits)[-1]=='Assorted Fruits'  # mains are offered before sides
    assert any('Brunch' in note for note in notes)
    pizza=next(s for s in sources if s['item_id']==hits[names(hits).index('Cheese Pizza')].item_id)
    assert pizza['allergens']==['dairy','gluten','soy'] and pizza['station']=='Pizza/Salad Bar' and pizza['allergen_status']=='published'


def test_usc_allergies_use_published_tags_instead_of_clearing_the_plan(usc):
    hits,sources,notes=live._usc(usc_request(allergies=['milk','shellfish']))
    assert 'Cheese Pizza' not in names(hits) and 'Scrambled Eggs' in names(hits)
    assert any('dairy, shellfish' in note for note in notes)
    dinner,_,_=live._usc(usc_request('dinner',allergies=['shrimp','dairy']))
    assert names(dinner)==['Mexican Street Corn Bowl with Barbacoa Beef','Spanish Rice']
    # An allergy USC does not tag is matched by name only and labeled, never used to wipe the plan.
    hits,_,notes=live._usc(usc_request(allergies=['jackfruit']))
    assert 'Roasted Jackfruit with Mango Salsa' not in names(hits) and len(hits)==5
    assert any('only matched against dish names' in note for note in notes)


def test_usc_plan_with_allergy_returns_labeled_cards(usc):
    data=TestClient(app).post('/v1/live/plan',json={'mode':'usc_dining','date':'2026-11-15','profile':{'allergies':['eggs'],'disliked_ingredients':['fruits']},
        'context':{'dining_hall':'parkside','max_walk_m':80,'origin':{'lat':34.0258,'lng':-118.2854},'locked_meal_ids':[None]}}).json()
    cards=[card for slot in data['slots'] for card in slot['recommendations']]
    assert cards and all(card['meal_title'] not in {'Scrambled Eggs','Assorted Fruits'} for card in cards)
    assert data['restrictions']['allergens_filtered']==['eggs']
    pizza=next(card for card in cards if card['meal_title']=='Cheese Pizza')
    assert pizza['allergen_information_status']=='listed by USC: dairy, gluten, soy'
    assert pizza['source']['status']=='verified' and pizza['venue']['location_label']=='Pizza/Salad Bar station'
    assert pizza['walking_meters']>0 and pizza['walking_minutes']>=1
    assert 'travelmode=walking' in pizza['directions_url']
    assert pizza['directions']['available'] is True
    assert pizza['directions']['destination']['lat'] is not None and pizza['directions']['destination']['lng'] is not None
    grill=next(card for card in cards if card['meal_title'].startswith('Daily Grill'))
    assert grill['allergen_information_status']=='not analyzed by USC'


def test_selected_cards_get_estimates_even_outside_first_batch(usc,monkeypatch):
    def estimate(hits,sources,**kw):
        for hit in hits: hit.ai_estimates={'assumed_serving':'1 plate','ranges':{k:{'low':10,'high':20} for k in ['calories','protein_g','carbs_g','fat_g']},'cuisine':'American'}
        return hits,[]
    monkeypatch.setattr(frontend,'estimate_missing',estimate)
    data=frontend.daily_plan(frontend.PlanRequest(mode='usc_dining',date=date(2026,11,15),context={'dining_hall':'parkside'}))
    cards=[card for slot in data['slots'] for card in slot['recommendations']]
    assert cards and all(card['nutrition']['status']=='estimated' and card['nutrition']['display_status']=='AI-estimated nutrition' and card['nutrition']['calories']==15 for card in cards)
    assert all(card['cuisine']=='American' and card['cuisine_status']=='inferred' for card in cards)
    assert any('no calories or macros' in warning for warning in data['warnings'])


def place(name,site,lat=34.0224):
    return SimpleNamespace(lat=lat,lng=-118.2851,display_name=name,website_uri=site,provider_place_id=name,
        raw_types=['italian_restaurant','restaurant'],formatted_address='3551 Trousdale Pkwy, Los Angeles, CA')


def offcampus(monkeypatch,**settings):
    monkeypatch.setattr(live,'get_settings',lambda:SimpleNamespace(google_maps_api_key='test',**settings))
    monkeypatch.setattr(live,'PlacesDiscoveryAdapter',lambda:SimpleNamespace(discover=lambda *a,**kw:[place('Good Kitchen','https://good.test'),
        place('Blocked Bistro','https://blocked.test'),place('Script Only','https://script.test'),place('No Site',None)]))
    def fetch(url):
        if 'blocked' in url: raise ValueError('Menu retrieval disallowed by the site robots.txt')
        return web.Page(url,'Tofu Bowl vegan $11.00' if 'good' in url else 'Loading…',[])
    monkeypatch.setattr(live,'fetch_page',fetch)
    empty={'value':None,'quote':None}
    def extract(documents):
        if 'good' not in documents[0]['url']: return []
        return [live.ExtractedDish(source_id='0',name='Tofu Bowl',quote='Tofu Bowl vegan $11.00',serving=None,diet_claims=['vegan'],
            price={'value':11,'quote':'Tofu Bowl vegan $11.00'},calories=empty,protein_g=empty,carbs_g=empty,fat_g=empty)]
    monkeypatch.setattr(live,'_extract',extract)
    monkeypatch.setattr(frontend,'select_meals',lambda hits,*a,**kw:RecommendationResult(provider='openai',status='completed',meals=[asdict(h) for h in hits[:3]]))


def plan(**context):
    return frontend.daily_plan(frontend.PlanRequest(mode='off_campus',date=date(2026,11,15),
        context={'origin':{'lat':34.0224,'lng':-118.2851},**context}))


def test_one_unreadable_site_does_not_fail_the_plan_and_is_reported(monkeypatch):
    offcampus(monkeypatch)
    data=plan()
    status={venue['name']:venue['status'] for venue in data['sources_checked']}
    assert status=={'Good Kitchen':'ok','Blocked Bistro':'menu_unreachable','Script Only':'no_readable_dishes','No Site':'no_website'}
    card=next(card for slot in data['slots'] for card in slot['recommendations'])
    assert card['meal_title']=='Tofu Bowl' and card['cuisine']=='Italian' and card['dietary_tags']==['vegan','vegetarian']
    assert card['allergen_information_status']=='unverified' and card['source']['status']=='needs_verification'
    assert card['directions']['available'] is True
    dest=card['directions']['destination']
    assert dest['place_id']=='Good Kitchen' and dest['lat']==34.0224
    assert dest['lng']==-118.2851 and str(dest.get('address') or '').startswith('3551')
    assert 'travelmode=walking' in (card['directions_url'] or '') and 'key=' not in (card['directions_url'] or '')
    assert any('2 nearby restaurants had no menu we could read' in warning for warning in data['warnings'])
    assert 'breakfast menu' in data['slots'][0]['availability_note']


def test_extraction_failure_is_isolated_per_restaurant(monkeypatch):
    offcampus(monkeypatch)
    good=live._extract
    def extract(documents):
        if 'script' in documents[0]['url']: raise live.LiveDiscoveryError('OpenAI could not extract the live menus.')
        return good(documents)
    monkeypatch.setattr(live,'_extract',extract)
    data=plan()
    assert any(card['meal_title']=='Tofu Bowl' for slot in data['slots'] for card in slot['recommendations'])
    assert {v['name']:v['status'] for v in data['sources_checked']}['Script Only']=='extraction_failed'


def test_saved_menus_supplement_live_results_and_supply_breakfast(monkeypatch):
    offcampus(monkeypatch,live_snapshot_supplement=True)
    data=plan(per_meal_budget_cents=2500,include_unknown_prices=True)
    cards=[card for slot in data['slots'] for card in slot['recommendations']]
    saved=[card for card in cards if card['source']['kind']=='curated_snapshot']
    assert saved and all(card['source']['status']=='stale' for card in saved)
    assert data['slots'][0]['recommendations'], 'saved breakfast menus fill the breakfast slot near Tommy Trojan'
    assert any(card['nutrition']['field_status']['calories']=='published' for card in saved)
    assert any('saved menus' in warning for warning in data['warnings'])
    assert any(venue['source']=='saved_snapshot' for venue in data['sources_checked'])


def test_places_outage_falls_back_to_saved_menus_only_when_enabled(monkeypatch):
    offcampus(monkeypatch,live_snapshot_supplement=True)
    def down(): raise httpx.ConnectError('down')
    monkeypatch.setattr(live,'PlacesDiscoveryAdapter',lambda:SimpleNamespace(discover=lambda *a,**kw:down()))
    data=plan(per_meal_budget_cents=2500)
    assert any(slot['recommendations'] for slot in data['slots'])
    assert any('Google Places discovery failed' in warning for warning in data['warnings'])
    offcampus(monkeypatch)
    monkeypatch.setattr(live,'PlacesDiscoveryAdapter',lambda:SimpleNamespace(discover=lambda *a,**kw:down()))
    with pytest.raises(live.LiveDiscoveryError): plan()


def test_brunch_days_leave_dishes_for_lunch_when_the_pool_is_small(usc):
    data=frontend.daily_plan(frontend.PlanRequest(mode='usc_dining',date=date(2026,11,15),
        profile={'dietary_preferences':['vegetarian'],'allergies':['dairy']},context={'dining_hall':'parkside'}))
    breakfast,lunch,dinner=[slot['recommendations'] for slot in data['slots']]
    assert breakfast and lunch and dinner
    titles=[card['meal_title'] for slot in data['slots'] for card in slot['recommendations']]
    assert len(titles)==len(set(titles)) and 'Cheese Pizza' not in titles


def test_campus_all_halls_includes_seeded_usc_retail(usc):
    """restaurants_usc_complete.json retail (Panda, Bowls, …) must appear on the campus tab."""
    data=frontend.daily_plan(frontend.PlanRequest(
        mode='usc_dining',date=date(2026,11,15),
        context={'dining_hall':'All halls','origin':{'lat':34.0258,'lng':-118.2854},'max_walk_m':1609}))
    cards=[card for slot in data['slots'] for card in slot['recommendations']]
    assert cards
    assert any(card['source']['kind']=='curated_snapshot' for card in cards)
    assert any('saved campus menus' in note or 'USC Hospitality' in note for note in data['warnings'])
    # Specific-hall filter stays hall-focused (no retail flood).
    parkside=frontend.daily_plan(frontend.PlanRequest(
        mode='usc_dining',date=date(2026,11,15),context={'dining_hall':'parkside'}))
    assert all(card['source']['kind']=='usc_official_feed'
               for slot in parkside['slots'] for card in slot['recommendations'])


def test_off_campus_seed_supplement_loads_complete_dataset(monkeypatch):
    offcampus(monkeypatch,live_snapshot_supplement=True)
    data=plan(per_meal_budget_cents=2500,include_unknown_prices=True,max_walk_m=1609)
    assert data['diversity']['eligible_restaurants'] and data['diversity']['eligible_restaurants']>=1
    assert any(slot['recommendations'] for slot in data['slots'])
    # Seed file splits cleanly: off-campus snapshot has no usc_dining halls.
    from trojanbites_extract.plan.menus import load_off_campus_menu, load_usc_dining_menu
    off=load_off_campus_menu(); usc=load_usc_dining_menu()
    assert all(v.get('dataset_category')=='off_campus' for v in off['venues'])
    assert all(v.get('dataset_category')=='usc_dining' for v in usc['venues'])
    assert len(off['venues'])>=70 and len(usc['venues'])>=20
