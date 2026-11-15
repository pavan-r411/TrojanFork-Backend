from dataclasses import asdict
from datetime import date
from fastapi.testclient import TestClient
from trojanbites_extract.api.app import app
from trojanbites_extract.recommend import frontend
from trojanbites_extract.recommend.service import RecommendationResult
from trojanbites_extract.query.filters import MealHit


def hit():
    return MealHit(item_id='food',restaurant_id='venue',restaurant_name='Live Venue',item_name='Live tofu bowl',price_amount=11,
        currency='USD',published_calories_kcal=None,published_protein_g=None,match_class='strict',uncertain_reasons=[],distance_miles=.2)


def test_offcampus_discovered_once_and_matches_ui_contract(monkeypatch):
    calls=[]
    def discover(body):
        calls.append(body)
        return [hit()],[{'item_id':'food','menu_url':'https://venue.test/menu','diet_claims':['vegan']}],[]
    monkeypatch.setattr(frontend,'_offcampus',discover)
    monkeypatch.setattr(frontend,'select_meals',lambda hits,*a:RecommendationResult(provider='openai',status='completed',meals=[asdict(x) for x in hits]))
    response=TestClient(app).post('/v1/live/plan',json={'mode':'off_campus','date':'2026-11-14','context':{'origin':{'lat':34.02,'lng':-118.28}}})
    assert response.status_code==200
    data=response.json()
    assert len(calls)==1
    assert len(data['slots'])==3
    assert data['slots'][1]['recommendations'][0]['nutrition']['calories'] is None
    assert data['slots'][1]['recommendations'][0]['nutrition']['display_status'] == 'Nutrition unavailable'
    assert data['slots'][1]['recommendations'][0]['price_cents']==1100
    assert data['slots'][0]['selected_recommendation_id'] is None
    assert data['data_mode']=='live'


def test_usc_never_calls_restaurants_and_respects_profile(monkeypatch):
    calls=[]
    monkeypatch.setattr(frontend,'_offcampus',lambda *_: (_ for _ in ()).throw(AssertionError()))
    def usc(body):
        calls.append(body);return [],[],[]
    monkeypatch.setattr(frontend,'_usc',usc)
    monkeypatch.setattr(frontend,'select_meals',lambda *a:RecommendationResult(provider='deterministic',status='no_matches',meals=[]))
    data=frontend.daily_plan(frontend.PlanRequest(mode='usc_dining',date=date(2026,11,14),profile={'goal':'build muscle','snacks':True}))
    assert len(calls)==4
    assert calls[0].preferences.goal=='build muscle'
    assert len(data['slots'])==4
    assert not data['slots'][0]['recommendations']


def test_frontend_is_served_and_dotfiles_blocked():
    client=TestClient(app)
    response=client.get('/ui/')
    assert response.status_code==200
    assert 'app.js' in response.text
    assert client.get('/ui/config.js').status_code==200
    assert client.get('/ui/.git/config').status_code==404


def test_daily_variety_reserves_distinct_dishes_and_requires_breakfast_evidence(monkeypatch):
    from dataclasses import replace
    meals=[replace(hit(),item_id=str(i),item_name=f'Dish {i}') for i in range(8)]
    sources=[{'item_id':str(i),'menu_url':'https://venue.test/menu','meal_periods':['breakfast'] if i<2 else []} for i in range(8)]
    monkeypatch.setattr(frontend,'_offcampus',lambda body:(meals,sources,[]))
    # Worst-case model always ranks every candidate in original order.
    monkeypatch.setattr(frontend,'select_meals',lambda hits,*a:RecommendationResult(provider='openai',status='completed',meals=[asdict(x) for x in hits[:3]]))
    data=frontend.daily_plan(frontend.PlanRequest(mode='off_campus',date=date(2026,11,14),context={'origin':{'lat':34.02,'lng':-118.28}}))
    choices=[item for slot in data['slots'] for item in slot['recommendations']]
    assert len({item['id'] for item in choices})==len(choices)
    assert all(slot['recommendations'] for slot in data['slots'])
    assert all(item['id'] in {'0','1'} for item in data['slots'][0]['recommendations'])


def test_inferred_breakfast_is_not_capped_at_one_by_later_slot_reserves(monkeypatch):
    """Breakfast-named unlabeled dishes used to count as lunch/dinner inventory and
    the reserve formula then capped breakfast at 1 even with 3+ breakfast options."""
    from dataclasses import replace
    names=['Acai Bowl','Egg Sandwich','Pancakes','Caesar Salad','Burrito Bowl','Pasta']
    meals=[replace(hit(),item_id=str(i),restaurant_id=f'r{i}',restaurant_name=f'Restaurant {i}',item_name=names[i]) for i in range(6)]
    sources=[{'item_id':str(i),'menu_url':'https://venue.test/menu','meal_periods':[]} for i in range(6)]
    monkeypatch.setattr(frontend,'_offcampus',lambda body:(meals,sources,[]))
    monkeypatch.setattr(frontend,'select_meals',lambda hits,*a:RecommendationResult(provider='openai',status='completed',meals=[asdict(x) for x in hits[:3]]))
    data=frontend.daily_plan(frontend.PlanRequest(mode='off_campus',date=date(2026,11,14),context={'origin':{'lat':34.02,'lng':-118.28}}))
    breakfast=data['slots'][0]['recommendations']
    assert len(breakfast)==3, breakfast
    assert {r['meal_title'] for r in breakfast}=={'Acai Bowl','Egg Sandwich','Pancakes'}
    assert all(slot['recommendations'] for slot in data['slots'][1:])


def test_single_candidate_is_not_repeated_or_presented_as_breakfast(monkeypatch):
    monkeypatch.setattr(frontend,'_offcampus',lambda body:([hit()],[{'item_id':'food','menu_url':'https://venue.test/menu'}],[]))
    monkeypatch.setattr(frontend,'select_meals',lambda hits,*a:RecommendationResult(provider='openai',status='completed',meals=[asdict(x) for x in hits]))
    data=frontend.daily_plan(frontend.PlanRequest(mode='off_campus',date=date(2026,11,14),context={'origin':{'lat':34.02,'lng':-118.28}}))
    assert not data['slots'][0]['recommendations']
    assert sum(len(slot['recommendations']) for slot in data['slots'])==1
    assert 'distinct' in data['slots'][2]['availability_note']


def test_on_campus_cards_cover_all_available_kitchens(monkeypatch):
    from dataclasses import replace
    meals=[replace(hit(),item_id=f'{hall}-{i}',restaurant_id=hall,restaurant_name=hall,item_name=f'{hall} dish {i}')
           for hall in ['EVK','Parkside','USC Village'] for i in range(40)]
    monkeypatch.setattr(frontend,'_usc',lambda body:(meals if body.meal_period=='dinner' else [],[],[]))
    monkeypatch.setattr(frontend,'select_meals',lambda hits,*a:RecommendationResult(provider='openai',status='completed',meals=[asdict(x) for x in hits[:3]]))
    data=frontend.daily_plan(frontend.PlanRequest(mode='usc_dining',date=date(2026,11,14)))
    dinner=data['slots'][2]['recommendations']
    assert len(dinner)==3
    assert {item['venue']['name'] for item in dinner}=={'EVK','Parkside','USC Village'}


def test_single_kitchen_retains_three_alternatives(monkeypatch):
    from dataclasses import replace
    meals=[replace(hit(),item_id=str(i),item_name=f'Dish {i}') for i in range(3)]
    monkeypatch.setattr(frontend,'select_meals',lambda hits,*a:RecommendationResult(provider='openai',status='completed',meals=[asdict(x) for x in hits[:3]]))
    result=frontend.rank_across_kitchens(meals,None,'dinner')
    assert len(result.meals)==3


def test_off_campus_recommendations_cover_eligible_restaurants(monkeypatch):
    from dataclasses import replace
    meals=[replace(hit(),item_id=f'{venue}-{i}',restaurant_id=venue,restaurant_name=venue,item_name=f'{venue} meal {i}')
        for venue in ['Restaurant A','Restaurant B','Restaurant C'] for i in range(12)]
    monkeypatch.setattr(frontend,'_offcampus',lambda body:(meals,[],[]))
    monkeypatch.setattr(frontend,'select_meals',lambda hits,*a:RecommendationResult(provider='openai',status='completed',meals=[asdict(x) for x in hits[:3]]))
    data=frontend.daily_plan(frontend.PlanRequest(mode='off_campus',date=date(2026,11,14),context={'origin':{'lat':34.02,'lng':-118.28}}))
    for slot in data['slots'][1:]:
        assert {r['venue']['name'] for r in slot['recommendations']}=={'Restaurant A','Restaurant B','Restaurant C'}
    assert data['diversity']['eligible_restaurants']==3


def test_cuisine_preferences_reach_live_ranking(monkeypatch):
    captured=[]
    monkeypatch.setattr(frontend,'_usc',lambda body:([],[],[]))
    def rank(hits,preferences,period):
        captured.append(preferences.preferred_cuisines)
        return RecommendationResult(provider='deterministic',status='no_matches',meals=[])
    monkeypatch.setattr(frontend,'select_meals',rank)
    frontend.daily_plan(frontend.PlanRequest(mode='usc_dining',date=date(2026,11,14),context={'preferred_cuisines':[' Indian ','Mexican','Indian']}))
    assert captured==[['Indian','Mexican']]*3


def test_usc_requests_carry_each_meal_period(monkeypatch):
    periods=[]
    monkeypatch.setattr(frontend,'_offcampus',lambda *_: (_ for _ in ()).throw(AssertionError('campus plan must not call off-campus discovery')))
    def usc(body):
        periods.append(body.meal_period)
        return [],[],[]
    monkeypatch.setattr(frontend,'_usc',usc)
    monkeypatch.setattr(frontend,'select_meals',lambda *a:RecommendationResult(provider='deterministic',status='no_matches',meals=[]))
    frontend.daily_plan(frontend.PlanRequest(mode='usc_dining',date=date(2026,11,14)))
    assert periods==['breakfast','lunch','dinner']


def test_daily_plan_prefers_unused_restaurants_across_slots(monkeypatch):
    from dataclasses import replace
    meals=[]
    sources=[]
    for period,venues in [('breakfast',['B1','B2','B3']),('lunch',['L1','L2','L3']),('dinner',['D1','D2','D3'])]:
        for venue in venues:
            item_id=f'{period}-{venue}'
            meals.append(replace(hit(),item_id=item_id,restaurant_id=venue,restaurant_name=venue,item_name=f'{venue} {period} plate'))
            sources.append({'item_id':item_id,'menu_url':'https://venue.test/menu','meal_periods':[period]})
    monkeypatch.setattr(frontend,'_offcampus',lambda body:(meals,sources,[]))
    monkeypatch.setattr(frontend,'select_meals',lambda hits,*a:RecommendationResult(provider='openai',status='completed',meals=[asdict(x) for x in hits[:3]]))
    data=frontend.daily_plan(frontend.PlanRequest(mode='off_campus',date=date(2026,11,14),context={'origin':{'lat':34.02,'lng':-118.28}}))
    by_slot={slot['slot']:slot for slot in data['slots']}
    breakfast_venues={r['venue']['id'] for r in by_slot['breakfast']['recommendations']}
    lunch_venues={r['venue']['id'] for r in by_slot['lunch']['recommendations']}
    dinner_venues={r['venue']['id'] for r in by_slot['dinner']['recommendations']}
    assert breakfast_venues=={'B1','B2','B3'}
    assert lunch_venues=={'L1','L2','L3'}
    assert dinner_venues=={'D1','D2','D3'}
    assert breakfast_venues.isdisjoint(lunch_venues)
    assert lunch_venues.isdisjoint(dinner_venues)
    assert by_slot['lunch']['empty_state']['diagnostics']['requested_service_time']=='12:30'
    assert by_slot['dinner']['empty_state']['diagnostics']['requested_service_time']=='18:30'
    assert by_slot['breakfast']['empty_state']['diagnostics']['final_selected_ids']


def test_within_slot_keeps_distinct_restaurants_when_inventory_allows(monkeypatch):
    from dataclasses import replace
    meals=[replace(hit(),item_id=f'{venue}-{i}',restaurant_id=venue,restaurant_name=venue,item_name=f'{venue} dinner {i}')
           for venue in ['Kitchen A','Kitchen B','Kitchen C'] for i in range(4)]
    sources=[{'item_id':m.item_id,'menu_url':'https://venue.test/menu','meal_periods':['dinner']} for m in meals]
    monkeypatch.setattr(frontend,'_offcampus',lambda body:(meals,sources,[]))
    monkeypatch.setattr(frontend,'select_meals',lambda hits,*a:RecommendationResult(provider='openai',status='completed',meals=[asdict(x) for x in hits[:3]]))
    data=frontend.daily_plan(frontend.PlanRequest(mode='off_campus',date=date(2026,11,14),context={'origin':{'lat':34.02,'lng':-118.28}}))
    dinner=next(slot for slot in data['slots'] if slot['slot']=='dinner')['recommendations']
    assert len(dinner)==3
    assert len({r['venue']['id'] for r in dinner})==3
    assert len({r['id'] for r in dinner})==3


def test_insufficient_kitchens_explain_restaurant_repeat(monkeypatch):
    from dataclasses import replace
    meals=[replace(hit(),item_id=str(i),restaurant_id='only',restaurant_name='Only Spot',item_name=f'Only dish {i}') for i in range(3)]
    sources=[{'item_id':str(i),'menu_url':'https://venue.test/menu','meal_periods':['lunch']} for i in range(3)]
    monkeypatch.setattr(frontend,'_offcampus',lambda body:(meals,sources,[]))
    monkeypatch.setattr(frontend,'select_meals',lambda hits,*a:RecommendationResult(provider='openai',status='completed',meals=[asdict(x) for x in hits[:3]]))
    data=frontend.daily_plan(frontend.PlanRequest(mode='off_campus',date=date(2026,11,14),context={'origin':{'lat':34.02,'lng':-118.28}}))
    lunch=next(slot for slot in data['slots'] if slot['slot']=='lunch')
    assert len(lunch['recommendations'])==3
    assert {r['venue']['id'] for r in lunch['recommendations']}=={'only'}
    assert any('Only Spot' in note for note in [lunch['availability_note'], *data['warnings']])
