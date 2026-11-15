"""Never spend API credits on automatic estimates during local tests."""
from types import SimpleNamespace
import pytest
from trojanbites_extract.recommend import estimates
from trojanbites_extract import provider_records
from trojanbites_extract.recommend import live


@pytest.fixture(autouse=True)
def estimates_offline_by_default(monkeypatch):
    live.clear_feed_cache()  # the short USC feed cache must never leak between tests
    monkeypatch.setattr(provider_records, 'get_settings', lambda: SimpleNamespace(provider_records_enabled=False))
    # Estimator HTTP tests explicitly replace this with their mocked configuration.
    monkeypatch.setattr(estimates, 'get_settings', lambda: SimpleNamespace(openai_api_key=None))
