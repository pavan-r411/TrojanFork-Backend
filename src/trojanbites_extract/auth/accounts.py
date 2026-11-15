"""PBKDF2 passwords, bearer sessions, and profile/plan records owned by one user.

Sessions store a SHA-256 of the bearer token. Profile updates never drop an
allergy list unless the client sends a new list. Swap preview does not insert
dishes and does not write the saved plan.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any

from trojanbites_extract.ids import new_id
from trojanbites_extract.settings import get_settings
from trojanbites_extract.store.db import session_scope
from trojanbites_extract.store.models import AuthSession, SavedDayPlan, User

_PBKDF2_ROUNDS = 200_000
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PROFILE_KEYS = {
    "goal",
    "preferred_cuisines",
    "dietary_preferences",
    "allergies",
    "disliked_ingredients",
    "targets",
    "remaining",
    "snacks",
    "activity_level",
    "display_name",
}
_MODES = {"usc_dining", "off_campus", "hybrid"}
_SLOTS = {"breakfast", "lunch", "dinner", "snack"}


class AuthError(Exception):
    def __init__(self, code: str, status: int):
        self.code = code
        self.status = status
        super().__init__(code)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${_PBKDF2_ROUNDS}${salt.hex()}${digest.hex()}"


_DUMMY_HASH: str | None = None


def _dummy_password_hash() -> str:
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password("not-a-real-password")
    return _DUMMY_HASH


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, rounds, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds)
        )
        return hmac.compare_digest(digest.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


def _normalize_email(email: str) -> str:
    cleaned = " ".join(str(email or "").split()).lower()
    if not _EMAIL.fullmatch(cleaned) or len(cleaned) > 320:
        raise AuthError("invalid_email", 422)
    return cleaned


def _check_password(password: str) -> str:
    if not isinstance(password, str) or not 8 <= len(password) <= 200:
        raise AuthError("password_too_short", 422)
    return password


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _public_user(user: User) -> dict[str, Any]:
    return {
        "user_id": user.user_id,
        "email": user.email,
        "display_name": user.display_name,
        "profile": dict(user.profile_json or {}),
    }


def _issue_session(session, user: User) -> tuple[str, datetime]:
    raw = secrets.token_urlsafe(32)
    expires = datetime.utcnow() + timedelta(hours=int(get_settings().session_ttl_hours))
    session.add(
        AuthSession(
            session_id=new_id("sess"),
            user_id=user.user_id,
            token_hash=_token_hash(raw),
            expires_at=expires,
        )
    )
    return raw, expires


def _auth_payload(user: User, token: str, expires: datetime) -> dict[str, Any]:
    return {
        "token": token,
        "token_type": "bearer",
        "expires_at": expires.isoformat() + "Z",
        "user": _public_user(user),
    }


def _user_for_token(session, token: str) -> User:
    row = (
        session.query(AuthSession)
        .filter(AuthSession.token_hash == _token_hash(token))
        .one_or_none()
    )
    if row is None or row.revoked_at is not None or row.expires_at <= datetime.utcnow():
        raise AuthError("authentication_required", 401)
    user = session.get(User, row.user_id)
    if user is None:
        raise AuthError("authentication_required", 401)
    return user


def register_account(email: str, password: str, display_name: str | None = None) -> dict[str, Any]:
    cleaned = _normalize_email(email)
    _check_password(password)
    name = (display_name or "").strip() or None
    if name is not None and len(name) > 80:
        raise AuthError("invalid_display_name", 422)
    with session_scope() as session:
        if session.query(User).filter(User.email == cleaned).one_or_none():
            raise AuthError("email_taken", 409)
        user = User(
            user_id=new_id("user"),
            email=cleaned,
            password_hash=hash_password(password),
            display_name=name,
            profile_json={},
        )
        session.add(user)
        session.flush()
        token, expires = _issue_session(session, user)
        return _auth_payload(user, token, expires)


def login_account(email: str, password: str) -> dict[str, Any]:
    cleaned = str(email or "").strip().lower()
    supplied = password if isinstance(password, str) else ""
    with session_scope() as session:
        user = session.query(User).filter(User.email == cleaned).one_or_none()
        # A dummy hash keeps the failure path in the same ballpark when the email is unknown.
        stored = user.password_hash if user is not None else _dummy_password_hash()
        if user is None or not verify_password(supplied, stored):
            raise AuthError("invalid_credentials", 401)
        token, expires = _issue_session(session, user)
        return _auth_payload(user, token, expires)


def logout_token(token: str) -> None:
    with session_scope() as session:
        _user_for_token(session, token)
        row = (
            session.query(AuthSession)
            .filter(AuthSession.token_hash == _token_hash(token))
            .one()
        )
        row.revoked_at = datetime.utcnow()


def current_user(token: str) -> dict[str, Any]:
    with session_scope() as session:
        return _public_user(_user_for_token(session, token))


def get_profile(user_id: str) -> dict[str, Any]:
    with session_scope() as session:
        user = session.get(User, user_id)
        if user is None:
            raise AuthError("authentication_required", 401)
        return _public_user(user)


def update_profile(user_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    """Merge profile fields. Omitted keys, including allergies, stay as stored.

    A JSON null does not clear allergies. An explicit list replaces them; that
    is the account owner editing their own profile, not a suggestion to drop one.
    """
    incoming = {key: value for key, value in patch.items() if key in _PROFILE_KEYS}
    if "allergies" in incoming and incoming["allergies"] is None:
        incoming.pop("allergies")
    if "display_name" in incoming and incoming["display_name"] is not None:
        incoming["display_name"] = str(incoming["display_name"]).strip() or None
        if incoming["display_name"] is not None and len(incoming["display_name"]) > 80:
            raise AuthError("invalid_display_name", 422)
    with session_scope() as session:
        user = session.get(User, user_id)
        if user is None:
            raise AuthError("authentication_required", 401)
        profile = dict(user.profile_json or {})
        for key, value in incoming.items():
            if key == "display_name":
                user.display_name = value
            profile[key] = value
        user.profile_json = profile
        user.updated_at = datetime.utcnow()
        return _public_user(user)


def _plan_out(row: SavedDayPlan) -> dict[str, Any]:
    return {
        "plan_id": row.plan_id,
        "date": row.plan_date,
        "mode": row.mode,
        "plan": deepcopy(row.plan_json or {}),
        "created_at": row.created_at.isoformat() + "Z" if row.created_at else None,
        "updated_at": row.updated_at.isoformat() + "Z" if row.updated_at else None,
    }


def list_plans(user_id: str, plan_date: str | None = None, mode: str | None = None) -> dict[str, Any]:
    with session_scope() as session:
        query = session.query(SavedDayPlan).filter(SavedDayPlan.user_id == user_id)
        if plan_date:
            query = query.filter(SavedDayPlan.plan_date == plan_date)
        if mode:
            query = query.filter(SavedDayPlan.mode == mode)
        rows = query.order_by(SavedDayPlan.plan_date.desc(), SavedDayPlan.mode).all()
        return {
            "plans": [
                {
                    "plan_id": row.plan_id,
                    "date": row.plan_date,
                    "mode": row.mode,
                    "updated_at": row.updated_at.isoformat() + "Z" if row.updated_at else None,
                }
                for row in rows
            ]
        }


def get_plan(user_id: str, plan_date: str, mode: str) -> dict[str, Any]:
    if mode not in _MODES:
        raise AuthError("invalid_mode", 422)
    with session_scope() as session:
        row = (
            session.query(SavedDayPlan)
            .filter(
                SavedDayPlan.user_id == user_id,
                SavedDayPlan.plan_date == plan_date,
                SavedDayPlan.mode == mode,
            )
            .one_or_none()
        )
        if row is None:
            raise AuthError("plan_not_found", 404)
        return _plan_out(row)


def save_plan(user_id: str, plan_date: str, mode: str, plan: dict[str, Any]) -> dict[str, Any]:
    if mode not in _MODES:
        raise AuthError("invalid_mode", 422)
    if not isinstance(plan, dict):
        raise AuthError("invalid_plan", 422)
    with session_scope() as session:
        owner = session.get(User, user_id)
        if owner is None:
            raise AuthError("authentication_required", 401)
        row = (
            session.query(SavedDayPlan)
            .filter(
                SavedDayPlan.user_id == user_id,
                SavedDayPlan.plan_date == plan_date,
                SavedDayPlan.mode == mode,
            )
            .one_or_none()
        )
        now = datetime.utcnow()
        if row is None:
            row = SavedDayPlan(
                plan_id=new_id("plan"),
                user_id=user_id,
                plan_date=plan_date,
                mode=mode,
                plan_json=deepcopy(plan),
                created_at=now,
                updated_at=now,
            )
            session.add(row)
        else:
            row.plan_json = deepcopy(plan)
            row.updated_at = now
        session.flush()
        return _plan_out(row)


def _owned_plan_dict(session, user_id: str, plan_date: str, mode: str) -> dict[str, Any]:
    row = (
        session.query(SavedDayPlan)
        .filter(
            SavedDayPlan.user_id == user_id,
            SavedDayPlan.plan_date == plan_date,
            SavedDayPlan.mode == mode,
        )
        .one_or_none()
    )
    if row is None:
        raise AuthError("plan_not_found", 404)
    return deepcopy(row.plan_json or {})


def swap_preview(
    user_id: str,
    *,
    plan_date: str,
    mode: str,
    slot: str,
    recommendation_id: str,
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Select an existing card in a slot. Does not persist and does not add dishes."""
    if mode not in _MODES:
        raise AuthError("invalid_mode", 422)
    if slot not in _SLOTS:
        raise AuthError("invalid_slot", 422)
    if not recommendation_id or not isinstance(recommendation_id, str):
        raise AuthError("recommendation_not_in_slot", 422)
    with session_scope() as session:
        if session.get(User, user_id) is None:
            raise AuthError("authentication_required", 401)
        body = deepcopy(plan) if plan is not None else _owned_plan_dict(session, user_id, plan_date, mode)
        if not isinstance(body, dict):
            raise AuthError("invalid_plan", 422)
        slots = body.get("slots")
        if not isinstance(slots, list):
            raise AuthError("invalid_slot", 422)
        match = next((item for item in slots if isinstance(item, dict) and item.get("slot") == slot), None)
        if match is None:
            raise AuthError("invalid_slot", 422)
        recommendations = match.get("recommendations") or []
        found = next(
            (
                card
                for card in recommendations
                if isinstance(card, dict) and card.get("id") == recommendation_id
            ),
            None,
        )
        if found is None:
            raise AuthError("recommendation_not_in_slot", 422)
        match["selected_recommendation_id"] = recommendation_id
        title = found.get("meal_title") or recommendation_id
        return {
            "persisted": False,
            "date": plan_date,
            "mode": mode,
            "slot": slot,
            "selected_recommendation_id": recommendation_id,
            "plan": body,
            "note": (
                f"Preview only: {title} selected for {slot}. "
                "The saved plan was not changed, and availability was not rechecked."
            ),
        }
