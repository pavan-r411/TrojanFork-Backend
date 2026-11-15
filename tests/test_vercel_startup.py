from fastapi.testclient import TestClient
from trojanbites_extract.api import app as api
from trojanbites_extract.settings import _project_root


def test_vercel_health_does_not_initialize_legacy_database(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    def forbidden():
        raise AssertionError("Vercel startup must not open the legacy database")
    monkeypatch.setattr(api, "init_db", forbidden)
    monkeypatch.setattr(api, "tag_existing_pilot_as_usc", forbidden)
    with TestClient(api.app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["ready"] is True


def test_project_assets_found_from_installed_package(monkeypatch, tmp_path):
    import trojanbites_extract.settings as settings
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings, "__file__", str(tmp_path / "_vendor" / "trojanbites_extract" / "settings.py"))
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "extraction.yaml").write_text("product_name: TrojanPlate")
    assert _project_root() == tmp_path
