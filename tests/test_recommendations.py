import json
from types import SimpleNamespace

import httpx
import pytest

from trojanbites_extract.query.filters import MealHit
from trojanbites_extract.recommend import service


def meal():
    return MealHit(item_id='dish', restaurant_id='restaurant', restaurant_name='Kitchen', item_name='Tofu bowl',
        price_amount=11, currency='USD', published_protein_g=30, published_calories_kcal=500,
        match_class='strict', uncertain_reasons=[], variant_id='bowl')


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    cfg = SimpleNamespace(recommendation_provider='openai', openai_api_key='test-secret',
        openai_model='test-model', openai_timeout_s=2, recommendation_candidate_limit=30)
    monkeypatch.setattr(service, 'get_settings', lambda: cfg)
    return cfg


def response(choices):
    return httpx.Response(200, json={'status':'completed', 'output':[{'type':'message', 'content':[
        {'type':'output_text','text':json.dumps({'choices':choices})}]}]})


def test_selection_preserves_database_facts():
    def handler(request):
        body=json.loads(request.content)
        assert body['store'] is False
        assert body['text']['format']['strict'] is True
        data=json.loads(body['input'])
        assert data['preferences']['goal']=='training_support'
        assert data['preferences']['remaining']['protein_g']==75
        assert data['eligible_foods'][0]['variant_id']=='bowl'
        return response([{'candidate_id':'candidate_0','reason':'Fits your preference for tofu.'}])
    result=service.select_meals([meal()],service.UserPreferences(goal='training_support',remaining=service.NutritionContext(protein_g=75)), 'lunch', transport=httpx.MockTransport(handler))
    assert result.provider=='openai'
    assert result.meals[0]['published_calories_kcal']==500
    assert result.meals[0]['price_amount']==11
    assert result.meals[0]['published_fat_g'] is None


@pytest.mark.parametrize('choices', [
    [{'candidate_id':'invented','reason':'bad'}],
    [{'candidate_id':'candidate_0','reason':'one'},{'candidate_id':'candidate_0','reason':'two'}],
    [{'candidate_id':'candidate_0','reason':'one','calories':123}],
])
def test_invalid_selection_falls_back(choices):
    result=service.select_meals([meal()],service.UserPreferences(),None,transport=httpx.MockTransport(lambda _:response(choices)))
    assert result.provider=='deterministic'
    assert result.meals[0]['item_id']=='dish'


@pytest.mark.parametrize('kind',['error','refusal','incomplete','malformed'])
def test_provider_failures(kind):
    def handler(_):
        if kind=='error': return httpx.Response(429,json={'error':'test-secret'})
        if kind=='refusal': return httpx.Response(200,json={'status':'completed','output':[{'type':'message','content':[{'type':'refusal'}]}]})
        if kind=='incomplete': return httpx.Response(200,json={'status':'incomplete'})
        return httpx.Response(200,text='not-json')
    result=service.select_meals([meal()],service.UserPreferences(),None,transport=httpx.MockTransport(handler))
    assert result.provider=='deterministic'
    assert 'test-secret' not in result.model_dump_json()


def test_no_key_and_no_matches(settings):
    settings.openai_api_key=None
    assert service.select_meals([meal()],service.UserPreferences(),None).status=='missing_api_key'
    assert service.select_meals([],service.UserPreferences(),None).status=='no_matches'


def test_restrictions_fail_closed():
    result=service.select_meals([meal()],service.UserPreferences(allergies=['peanut']),None)
    assert result.status=='restriction_evidence_missing'
    assert not result.meals


def test_api_passes_goal_and_returns_original_records(monkeypatch):
    from importlib import import_module
    from fastapi.testclient import TestClient
    from trojanbites_extract.store.db import init_db
    api = import_module('trojanbites_extract.api.app')
    init_db()
    seen={}
    def filtered(session, query):
        seen['query']=query
        return [meal()]
    def ranked(hits, preferences, period):
        seen['goal']=preferences.goal
        seen['period']=period
        return service.select_meals(hits, preferences, period,transport=httpx.MockTransport(
            lambda _:response([{'candidate_id':'candidate_0','reason':'Fits your food preference.'}])))
    monkeypatch.setattr(api,'filter_meals',filtered)
    monkeypatch.setattr(api,'select_meals',ranked)
    result=TestClient(api.app).post('/v1/suggest',json={'campus_id':'usc_upc', 'budget_max':12,
        'diet':['vegetarian'],'collect_missing':False,'meal_period':'lunch','preferences':{'goal':'build muscle'}})
    assert result.status_code==200
    body=result.json()
    assert body['personalization']['provider']=='openai'
    assert body['suggested_meals'][0]['price_amount']==11
    assert seen['goal']=='build muscle' and seen['period']=='lunch'
    assert seen['query'].budget_max==12
    assert seen['query'].diet_claims_required==['vegetarian']


def test_api_restrictions_cannot_bypass_with_personalize_false(monkeypatch):
    from importlib import import_module
    from fastapi.testclient import TestClient
    api=import_module('trojanbites_extract.api.app')
    monkeypatch.setattr(api,'filter_meals',lambda *_:[meal()])
    result=TestClient(api.app).post('/v1/suggest',json={'campus_id':'usc_upc','collect_missing':False,
        'personalize':False,'preferences':{'allergies':['peanut']}})
    assert result.status_code==200
    assert result.json()['suggested_meals']==[]
    assert result.json()['personalization']['status']=='restriction_evidence_missing'
