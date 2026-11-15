"""Account, profile, and owned-plan routes."""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from trojanbites_extract.api.app import app
from trojanbites_extract.auth.accounts import verify_password
from trojanbites_extract.store.db import session_scope
from trojanbites_extract.store.models import AuthSession, User


@pytest.fixture
def client(tmp_path, monkeypatch):
    from trojanbites_extract.store import db

    previous = db.SessionLocal
    db.init_db(f"sqlite:///{tmp_path}/auth.db")
    monkeypatch.setattr("trojanbites_extract.api.app.init_db", lambda *a, **k: None)
    monkeypatch.setattr("trojanbites_extract.jobs.ingestion.init_db", lambda *a, **k: None)
    with TestClient(app) as test_client:
        yield test_client
    db.SessionLocal = previous


def _auth(client, email, password="correct-horse", display_name=None):
    body = {"email": email, "password": password}
    if display_name:
        body["display_name"] = display_name
    response = client.post("/v1/auth/register", json=body)
    assert response.status_code == 201, response.text
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_register_login_logout_and_me(client):
    registered = client.post(
        "/v1/auth/register",
        json={"email": "Sam@usc.edu", "password": "correct-horse", "display_name": "Sam"},
    )
    assert registered.status_code == 201
    payload = registered.json()
    assert payload["token_type"] == "bearer"
    assert payload["user"]["email"] == "sam@usc.edu"
    assert "password" not in payload["user"]
    headers = {"Authorization": f"Bearer {payload['token']}"}
    assert client.get("/v1/auth/me", headers=headers).json()["display_name"] == "Sam"
    logged_in = client.post("/v1/auth/login", json={"email": "sam@usc.edu", "password": "correct-horse"})
    assert logged_in.status_code == 200
    assert client.post("/v1/auth/login", json={"email": "sam@usc.edu", "password": "wrong-password"}).status_code == 401
    assert client.post("/v1/auth/logout", headers=headers).status_code == 204
    assert client.get("/v1/auth/me", headers=headers).status_code == 401
    with session_scope() as session:
        user = session.query(User).one()
        assert user.password_hash != "correct-horse"
        assert user.password_hash.startswith("pbkdf2_sha256$")
        assert verify_password("correct-horse", user.password_hash)
        assert not verify_password("wrong-password", user.password_hash)


def test_duplicate_email_and_short_password(client):
    _auth(client, "sam@usc.edu")
    again = client.post("/v1/auth/register", json={"email": "sam@usc.edu", "password": "correct-horse"})
    assert again.status_code == 409
    assert again.json()["detail"] == "email_taken"
    short = client.post("/v1/auth/register", json={"email": "new@usc.edu", "password": "short"})
    assert short.status_code == 422


def test_expired_session_is_rejected(client):
    headers = _auth(client, "sam@usc.edu")
    with session_scope() as session:
        session.query(AuthSession).one().expires_at = datetime.utcnow() - timedelta(minutes=1)
    assert client.get("/v1/auth/me", headers=headers).status_code == 401


def test_profile_merge_keeps_allergies_and_is_private(client):
    owner = _auth(client, "owner@usc.edu")
    other = _auth(client, "other@usc.edu")
    saved = client.put(
        "/v1/profile",
        headers=owner,
        json={"allergies": ["peanut"], "goal": "balanced", "display_name": "Owner"},
    )
    assert saved.status_code == 200
    updated = client.put("/v1/profile", headers=owner, json={"goal": "build muscle"})
    profile = updated.json()
    assert profile["profile"]["allergies"] == ["peanut"]
    assert profile["profile"]["goal"] == "build muscle"
    assert profile["display_name"] == "Owner"
    assert "password_hash" not in profile
    assert client.get("/v1/profile", headers=other).json()["profile"] == {}


def test_plans_are_owned_and_swap_preview_does_not_persist_or_invent(client):
    owner = _auth(client, "owner@usc.edu")
    other = _auth(client, "other@usc.edu")
    plan = {
        "restrictions": {"allergens_filtered": ["peanut"]},
        "slots": [
            {
                "slot": "lunch",
                "selected_recommendation_id": None,
                "recommendations": [
                    {"id": "real-tofu", "meal_title": "Tofu Bowl"},
                    {"id": "real-rice", "meal_title": "Spanish Rice"},
                ],
            }
        ],
    }
    saved = client.put(
        "/v1/plans",
        headers=owner,
        json={"date": "2026-11-15", "mode": "off_campus", "plan": plan},
    )
    assert saved.status_code == 200
    assert saved.json()["plan_id"]
    listed = client.get("/v1/plans", headers=owner).json()["plans"]
    assert len(listed) == 1 and listed[0]["date"] == "2026-11-15"
    loaded = client.get("/v1/plans", headers=owner, params={"date": "2026-11-15", "mode": "off_campus"})
    assert loaded.status_code == 200
    assert loaded.json()["plan"]["restrictions"]["allergens_filtered"] == ["peanut"]
    assert client.get(
        "/v1/plans", headers=other, params={"date": "2026-11-15", "mode": "off_campus"}
    ).status_code == 404

    preview = client.post(
        "/v1/plans/swap-preview",
        headers=owner,
        json={
            "date": "2026-11-15",
            "mode": "off_campus",
            "slot": "lunch",
            "recommendation_id": "real-rice",
        },
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["persisted"] is False
    assert body["selected_recommendation_id"] == "real-rice"
    assert body["plan"]["slots"][0]["selected_recommendation_id"] == "real-rice"
    assert [card["id"] for card in body["plan"]["slots"][0]["recommendations"]] == ["real-tofu", "real-rice"]
    assert body["plan"]["restrictions"]["allergens_filtered"] == ["peanut"]
    assert "remove" not in body["note"].lower()
    stored = client.get(
        "/v1/plans", headers=owner, params={"date": "2026-11-15", "mode": "off_campus"}
    ).json()
    assert stored["plan"]["slots"][0]["selected_recommendation_id"] is None

    invented = client.post(
        "/v1/plans/swap-preview",
        headers=owner,
        json={
            "date": "2026-11-15",
            "mode": "off_campus",
            "slot": "lunch",
            "recommendation_id": "invented-omelette",
        },
    )
    assert invented.status_code == 422
    assert invented.json()["detail"] == "recommendation_not_in_slot"
    after = client.get(
        "/v1/plans", headers=owner, params={"date": "2026-11-15", "mode": "off_campus"}
    ).json()
    assert [card["meal_title"] for card in after["plan"]["slots"][0]["recommendations"]] == [
        "Tofu Bowl",
        "Spanish Rice",
    ]
