from dataclasses import asdict
from types import SimpleNamespace
import json

import pytest

from trojanbites_extract.recommend import live, web
from trojanbites_extract.recommend.service import RecommendationResult


def request(mode='off_campus', meal_period='lunch', **kwargs):
    return live.LiveRequest(mode=mode,date='2026-11-14',lat=34.0224,lng=-118.2851,meal_period=meal_period,**kwargs)


@pytest.fixture(autouse=True)
def rank(monkeypatch):
    monkeypatch.setattr(live,'select_meals',lambda hits,*a,**kw:RecommendationResult(provider='openai',status='completed',meals=[asdict(x) for x in hits]))


def test_usc_exact_date_period_and_no_catalog(monkeypatch):
    page={'date':'20261114','meals':[{'name':'Lunch','stations':[{'menu':[{'item':'Tofu Bowl','preferences':['vegan']}]}]},
        {'name':'Dinner','stations':[{'menu':[{'item':'Dinner only'}]}]}]}
    calls=[]
    def fetch(url):
        calls.append(url);return web.Page(url,json.dumps(page),[])
    monkeypatch.setattr(live,'fetch_page',fetch)
    result=live.live_suggest(request('usc_dining',dining_hall='EVK',diet=['vegan']))
    assert len(calls)==1 and '/evk?y=2026&m=11&d=14' in calls[0]
    assert result['suggested_meals'][0]['item_name']=='Tofu Bowl'
    assert result['suggested_meals'][0]['published_calories_kcal'] is None
    page['date']='20261113'
    live.clear_feed_cache()
    assert not live.live_suggest(request('usc_dining',dining_hall='evk'))['suggested_meals']


def test_usc_empty_breakfast_falls_back_to_brunch():
    meals = [
        {'name': 'Breakfast', 'stations': [{'menu': []}]},
        {'name': 'Brunch', 'stations': [{'menu': [{'item': 'Eggs'}]}]},
        {'name': 'Lunch', 'stations': [{'menu': []}]},
        {'name': 'Dinner', 'stations': [{'menu': [{'item': 'Pasta'}]}]},
    ]
    assert live._usc_meal_periods('breakfast', meals) == ['brunch']
    assert live._usc_meal_periods('lunch', meals) == ['brunch']
    assert live._usc_meal_periods('dinner', meals) == ['dinner']
    meals[0]['stations'][0]['menu'] = [{'item': 'Oatmeal'}]
    assert live._usc_meal_periods('breakfast', meals) == ['breakfast']


def test_usc_brunch_fallback_returns_dishes(monkeypatch):
    page = {
        'date': '20261114',
        'meals': [
            {'name': 'Breakfast', 'stations': [{'menu': []}]},
            {'name': 'Brunch', 'stations': [{'menu': [{'item': 'Avocado Toast', 'preferences': []}]}]},
            {'name': 'Lunch', 'stations': [{'menu': []}]},
            {'name': 'Dinner', 'stations': [{'menu': [{'item': 'Dinner Bowl', 'preferences': []}]}]},
        ],
    }
    monkeypatch.setattr(live, 'fetch_page', lambda url: web.Page(url, json.dumps(page), []))
    breakfast = live.live_suggest(request('usc_dining', dining_hall='evk', meal_period='breakfast'))
    assert breakfast['suggested_meals'][0]['item_name'] == 'Avocado Toast'
    assert any('Brunch' in w for w in breakfast.get('warnings', []))


def test_invalid_hall_and_missing_location():
    with pytest.raises(live.LiveDiscoveryError): live.live_suggest(request('usc_dining',dining_hall='fake'))
    b=request();b.lat=None
    with pytest.raises(live.LiveDiscoveryError,match='latitude'):live.live_suggest(b)


def extracted(**kwargs):
    empty={'value':None,'quote':None}
    return live.ExtractedDish(source_id='0',name='Tofu Bowl',quote='Tofu Bowl vegan $11.00',serving=None,
        diet_claims=['vegan'],price={'value':11,'quote':'Tofu Bowl vegan $11.00'},calories=empty,
        protein_g=empty,carbs_g=empty,fat_g=empty,**kwargs)


def setup_offcampus(monkeypatch):
    monkeypatch.setattr(live,'get_settings',lambda:SimpleNamespace(google_maps_api_key='test'))
    places=[SimpleNamespace(lat=34.0224,lng=-118.2851,display_name='Kitchen',website_uri='https://menu.test',provider_place_id='test'),
            SimpleNamespace(lat=35,lng=-118,display_name='Far away',website_uri='https://far.test',provider_place_id='far')]
    monkeypatch.setattr(live,'PlacesDiscoveryAdapter',lambda:SimpleNamespace(discover=lambda *a,**kw:places))
    calls=[]
    def fetch(url):
        calls.append(url);return web.Page(url,'Tofu Bowl vegan $11.00',[])
    monkeypatch.setattr(live,'fetch_page',fetch)
    monkeypatch.setattr(live,'_extract',lambda docs:[extracted()])
    return calls


def test_offcampus_radius_prices_and_source(monkeypatch):
    calls=setup_offcampus(monkeypatch)
    result=live.live_suggest(request(budget_max=12,diet=['vegan']))
    assert calls==['https://menu.test']
    assert result['suggested_meals'][0]['price_amount']==11
    assert result['suggested_meals'][0]['published_protein_g'] is None
    assert result['sources'][0]['menu_url']=='https://menu.test'
    assert not live.live_suggest(request(budget_max=10))['suggested_meals']


def test_invented_extraction_not_returned(monkeypatch):
    setup_offcampus(monkeypatch)
    item=extracted();item.name='Invented curry'
    monkeypatch.setattr(live,'_extract',lambda docs:[item])
    assert not live.live_suggest(request())['suggested_meals']


def test_number_requires_item_specific_source_and_label():
    f=live.EvidenceNumber(value=30,quote='Tofu Bowl protein 30g')
    assert live._number(f,f.quote,'Tofu Bowl','protein_g')==30
    assert live._number(f,'unrelated menu','Tofu Bowl','protein_g') is None
    f.quote='Tofu Bowl 30 reviews'
    assert live._number(f,f.quote,'Tofu Bowl','protein_g') is None
    f=live.EvidenceNumber(value=11,quote='Tofu Bowl $110')
    assert live._number(f,f.quote,'Tofu Bowl','price') is None


def test_allergies_hide_only_dishes_with_evidence(monkeypatch):
    setup_offcampus(monkeypatch)
    body=request();body.preferences.allergies=['peanut']
    data=live.live_suggest(body)
    assert data['suggested_meals'][0]['item_name']=='Tofu Bowl'
    assert any('unverified' in warning for warning in data['warnings'])
    body=request();body.preferences.allergies=['soy']  # "tofu" in the dish text is evidence of soy
    assert not live.live_suggest(body)['suggested_meals']
    body=request();body.preferences.excluded_ingredients=['bowls']
    assert not live.live_suggest(body)['suggested_meals']


def test_private_urls_rejected(monkeypatch):
    monkeypatch.setattr(web,'_is_private_host',lambda host:host in {'localhost','127.0.0.1'})
    assert not web.public_url('http://127.0.0.1/menu')
    assert not web.public_url('http://user:password@restaurant.test/menu')
    assert not web.public_url('file:///etc/passwd')
    assert web.public_url('https://restaurant.test/menu')


def test_location_name_resolution(monkeypatch):
    setup_offcampus(monkeypatch)
    monkeypatch.setattr(live,'_resolve_location',lambda name:(34.0224,-118.2851,'USC Village','Los Angeles'))
    body=request(location_name='USC Village, Los Angeles');body.lat=None;body.lng=None
    result=live.live_suggest(body)
    assert result['resolved_location']['name']=='USC Village'
    assert result['suggested_meals']


def test_decimal_price_preserved():
    f=live.EvidenceNumber(value=11.5,quote='Tofu Bowl $11.50')
    assert live._number(f,f.quote,'Tofu Bowl','price')==11.5


@pytest.mark.parametrize('hall',['','   ','Any dining hall','All halls',' all   halls '])
def test_blank_or_any_hall_means_all_halls(monkeypatch,hall):
    calls=[]
    def fetch(url):
        calls.append(url)
        return web.Page(url,json.dumps({'date':'20261114','meals':[]}),[])
    monkeypatch.setattr(live,'fetch_page',fetch)
    live.live_suggest(request('usc_dining',dining_hall=hall))
    assert len(calls)==3
    assert any('/evk?' in url for url in calls)
    assert any('/parkside?' in url for url in calls)
    assert any('/university-village?' in url for url in calls)



def test_price_quote_whitespace_normalization():
    fact=live.EvidenceNumber(value=12.95,quote='Caesar Salad $12.95')
    assert live._number(fact,'Caesar Salad\n  $12.95','Caesar Salad','price')==12.95
    assert live._number(fact,'Different dish\n  $12.95','Caesar Salad','price') is None



def test_shared_category_prices_are_scoped_and_source_grounded():
    text="Choose a Fresh Pasta $14.95\nSpaghetti\nPenne\nGluten Free Penne Option Available\nAlfredo\nCream Sauce\nAdditions: Chicken +$4.00\nSalads $12.95\nCaesar Salad.\nRomaine Lettuce\nKale Salad.\nAdditions: Shrimp +$5.00\nHours\nOpen Daily"
    assert live._section_price(text,'Spaghetti')[0]==14.95
    assert live._section_price(text,'Kale Salad')[0]==12.95
    assert live._section_price(text,'Caesar Salad.')[0]==12.95
    assert live._section_price(text,'Alfredo')[0] is None
    assert live._section_price(text,'Chicken')[0] is None
    assert live._section_price(text,'Imaginary bowl')[0] is None


def test_unpriced_meals_require_explicit_opt_in(monkeypatch):
    setup_offcampus(monkeypatch)
    row=extracted();row.price=live.EvidenceNumber(value=None,quote=None)
    monkeypatch.setattr(live,'_extract',lambda docs:[row])
    assert not live.live_suggest(request(budget_max=15))['suggested_meals']
    data=live.live_suggest(request(budget_max=15,include_unknown_prices=True))
    assert len(data['suggested_meals'])==1
    assert data['suggested_meals'][0]['price_amount'] is None
