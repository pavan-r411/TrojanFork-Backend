"""HTTP routes for accounts, profiles, and owned day plans."""
from __future__ import annotations

from datetime import date as Date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from trojanbites_extract.auth.accounts import (
    AuthError,
    current_user,
    get_plan,
    get_profile,
    list_plans,
    login_account,
    logout_token,
    register_account,
    save_plan,
    swap_preview,
    update_profile,
)
from trojanbites_extract.store.db import session_scope
from trojanbites_extract.auth.accounts import _user_for_token

router = APIRouter()


class RegisterBody(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=200)
    display_name: str | None = Field(None, max_length=80)


class LoginBody(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=200)


class ProfileBody(BaseModel):
    goal: str | None = Field(None, max_length=200)
    preferred_cuisines: list[str] | None = Field(None, max_length=20)
    dietary_preferences: list[str] | None = Field(None, max_length=10)
    allergies: list[str] | None = Field(None, max_length=20)
    disliked_ingredients: list[str] | None = Field(None, max_length=20)
    targets: dict[str, Any] | None = None
    remaining: dict[str, Any] | None = None
    snacks: bool | None = None
    activity_level: str | None = Field(None, max_length=40)
    display_name: str | None = Field(None, max_length=80)


class SavePlanBody(BaseModel):
    date: Date
    mode: Literal["usc_dining", "off_campus", "hybrid"]
    plan: dict[str, Any]


class SwapPreviewBody(BaseModel):
    date: Date
    mode: Literal["usc_dining", "off_campus", "hybrid"]
    slot: Literal["breakfast", "lunch", "dinner", "snack"]
    recommendation_id: str = Field(min_length=1, max_length=200)
    plan: dict[str, Any] | None = None


def _call(fn):
    try:
        return fn()
    except AuthError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.code) from exc


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="authentication_required")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="authentication_required")
    return token


def _user_id(authorization: str | None) -> str:
    token = _bearer(authorization)

    def load():
        with session_scope() as session:
            return _user_for_token(session, token).user_id

    return _call(load)


@router.post("/v1/auth/register", status_code=201)
def register(body: RegisterBody) -> dict[str, Any]:
    return _call(lambda: register_account(body.email, body.password, body.display_name))


@router.post("/v1/auth/login")
def login(body: LoginBody) -> dict[str, Any]:
    return _call(lambda: login_account(body.email, body.password))


@router.post("/v1/auth/logout", status_code=204)
def logout(authorization: Annotated[str | None, Header()] = None) -> Response:
    token = _bearer(authorization)
    _call(lambda: logout_token(token))
    return Response(status_code=204)


@router.get("/v1/auth/me")
def me(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    token = _bearer(authorization)
    return _call(lambda: current_user(token))


@router.get("/v1/profile")
def read_profile(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    user_id = _user_id(authorization)
    return _call(lambda: get_profile(user_id))


@router.put("/v1/profile")
def write_profile(
    body: ProfileBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    user_id = _user_id(authorization)
    return _call(lambda: update_profile(user_id, body.model_dump(exclude_unset=True)))


@router.get("/v1/plans")
def read_plans(
    authorization: Annotated[str | None, Header()] = None,
    date: Date | None = None,
    mode: Literal["usc_dining", "off_campus", "hybrid"] | None = None,
) -> dict[str, Any]:
    user_id = _user_id(authorization)
    plan_date = date.isoformat() if date else None
    if date is not None and mode is not None:
        return _call(lambda: get_plan(user_id, plan_date or "", mode))
    return _call(lambda: list_plans(user_id, plan_date, mode))


@router.put("/v1/plans")
def write_plan(
    body: SavePlanBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    user_id = _user_id(authorization)
    return _call(lambda: save_plan(user_id, body.date.isoformat(), body.mode, body.plan))


@router.post("/v1/plans/swap-preview")
def preview_swap(
    body: SwapPreviewBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    user_id = _user_id(authorization)
    return _call(
        lambda: swap_preview(
            user_id,
            plan_date=body.date.isoformat(),
            mode=body.mode,
            slot=body.slot,
            recommendation_id=body.recommendation_id,
            plan=body.plan,
        )
    )
