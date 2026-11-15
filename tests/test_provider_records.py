import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import httpx
from trojanbites_extract import provider_records as records


def config(tmp_path,enabled=True):
    return SimpleNamespace(provider_records_enabled=enabled,provider_records_dir=tmp_path/'records',root=tmp_path,
        openai_api_key='test-secret',google_maps_api_key='maps-secret')


def test_records_response_and_redacts_secrets(tmp_path,monkeypatch):
    monkeypatch.setattr(records,'get_settings',lambda:config(tmp_path))
    response=httpx.Response(403,json={'error':{'message':'bad key test-secret','api_key':'anything'},'text':'maps-secret'},headers={'x-request-id':'req1'})
    records.record_response('openai','meal_recommendation',response,model='test')
    path=next((tmp_path/'records').glob('*.jsonl'))
    raw=path.read_text();data=json.loads(raw)
    assert 'test-secret' not in raw and 'maps-secret' not in raw
    assert data['http_status']==403 and data['provider_request_id']=='req1'
    assert data['response']['error']['api_key']=='[REDACTED]'
    assert path.stat().st_mode & 0o777 == 0o600


def test_disabled_does_not_write(tmp_path,monkeypatch):
    monkeypatch.setattr(records,'get_settings',lambda:config(tmp_path,False))
    records.record_response('google_maps','nearby_search',httpx.Response(200,json={}))
    assert not (tmp_path/'records').exists()


def test_concurrent_records_are_valid_json_lines(tmp_path,monkeypatch):
    monkeypatch.setattr(records,'get_settings',lambda:config(tmp_path))
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda n:records.record_response('openai','test',httpx.Response(200,json={'n':n})),range(12)))
    lines=next((tmp_path/'records').glob('*.jsonl')).read_text().splitlines()
    assert sorted(json.loads(line)['response']['n'] for line in lines)==list(range(12))
