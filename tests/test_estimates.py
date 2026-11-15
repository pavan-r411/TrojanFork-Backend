import json
from types import SimpleNamespace
import httpx
from trojanbites_extract.recommend import estimates, frontend
from trojanbites_extract.query.filters import MealHit
from trojanbites_extract.recommend.service import RecommendationResult
from dataclasses import asdict
from datetime import date


def meal():
    return MealHit(item_id='dish',restaurant_id='r',restaurant_name='Kitchen',item_name='Tofu Bowl',
        price_amount=12,published_calories_kcal=None,published_protein_g=30,currency='USD',match_class='strict',uncertain_reasons=[])


def response(rows):
    return httpx.Response(200,json={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps({'estimates':rows})}]}]})


def row(**kw):
    return dict(item_id='dish',assumed_serving='One medium bowl; oil quantity unknown',price={'low':10,'high':16},
        calories={'low':450,'high':650},protein_g={'low':20,'high':40},carbs_g=None,fat_g=None) | kw


def test_estimates_do_not_overwrite_published_values(monkeypatch):
    monkeypatch.setattr(estimates,'get_settings',lambda:SimpleNamespace(openai_api_key='secret',openai_model='test'))
    item=meal()
    hits,_=estimates.estimate_missing([item],[],transport=httpx.MockTransport(lambda _:response([row()])))
    assert hits[0].price_amount==12
    assert hits[0].published_protein_g==30
    assert hits[0].published_calories_kcal is None
    assert 'price' not in hits[0].ai_estimates['ranges']
    assert 'protein_g' not in hits[0].ai_estimates['ranges']
    assert estimates.midpoint(hits[0].ai_estimates['ranges']['calories'])==550


def test_invalid_ids_ranges_or_errors_leave_unknown(monkeypatch):
    monkeypatch.setattr(estimates,'get_settings',lambda:SimpleNamespace(openai_api_key='secret',openai_model='test'))
    for rows in [[row(item_id='invented')],[row(calories={'low':700,'high':400})],[row(),row()]]:
        item=meal()
        hits,warnings=estimates.estimate_missing([item],[],transport=httpx.MockTransport(lambda _:response(rows)))
        assert hits[0].ai_estimates is None
        assert 'unavailable' in warnings[0]


def test_frontend_marks_mixed_estimates_and_published_separately(monkeypatch):
    item=meal();item.ai_estimates={'assumed_serving':'One bowl','ranges':{'calories':{'low':450,'high':650}}}
    monkeypatch.setattr(frontend,'_usc',lambda body:([item] if body.meal_period=='dinner' else [],[],[]))
    monkeypatch.setattr(frontend,'select_meals',lambda hits,*a:RecommendationResult(provider='openai',status='completed',meals=[asdict(h) for h in hits]))
    data=frontend.daily_plan(frontend.PlanRequest(mode='usc_dining',date=date(2026,11,14)))
    n=data['slots'][2]['recommendations'][0]['nutrition']
    assert n['calories']==550 and n['published']['calories'] is None
    assert n['field_status']['calories']=='estimated'
    assert n['protein_g']==30 and n['field_status']['protein_g']=='published'
    assert n['status']=='estimated'
