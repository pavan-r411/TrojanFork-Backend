"""HTTP surface for the guided flow."""
from __future__ import annotations

from datetime import date as Date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query as ApiQuery
from pydantic import BaseModel, ConfigDict, Field

from trojanbites_extract.flow import engine, explain as explain_mod, feed, parse as parse_mod
from trojanbites_extract.flow.data import dataset

router = APIRouter(prefix='/v1/flow', tags=['flow'])
LA = ZoneInfo('America/Los_Angeles')


def today_la() -> Date:
    return datetime.now(LA).date()


class ProfileIn(BaseModel):
    model_config = ConfigDict(extra='ignore')
    diet: str = Field('any', max_length=20)
    allergies: list[str] = Field(default_factory=list, max_length=20)
    exclusions: list[str] = Field(default_factory=list, max_length=20)
    goal: str = Field('balanced', max_length=40)
    preferred_cuisines: list[str] = Field(default_factory=list, max_length=12)


class TargetsIn(BaseModel):
    model_config = ConfigDict(extra='ignore')
    meal_kcal: float | None = Field(None, ge=50, le=3000)
    meal_protein_g: float | None = Field(None, ge=0, le=250)
    min_protein_g: float | None = Field(None, ge=0, le=250)
    max_kcal: float | None = Field(None, ge=50, le=3000)


class BudgetIn(BaseModel):
    model_config = ConfigDict(extra='ignore')
    per_meal_usd: float | None = Field(None, ge=0, le=500)
    daily_remaining_usd: float | None = Field(None, ge=0, le=2000)
    meals_left: int = Field(1, ge=1, le=4)


class CampusIn(BaseModel):
    model_config = ConfigDict(extra='ignore')
    swipes_remaining: int | None = Field(None, ge=0, le=100)
    halls: list[Literal['evk', 'parkside', 'university-village']] = Field(default_factory=list)
    include_retail: bool = False


class OriginIn(BaseModel):
    model_config = ConfigDict(extra='ignore')
    lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    lng: float = Field(ge=-180, le=180, allow_inf_nan=False)
    label: str | None = Field(None, max_length=120)


class BandIn(BaseModel):
    model_config = ConfigDict(extra='ignore')
    min: float = Field(ge=0, le=25, allow_inf_nan=False)
    max: float = Field(ge=0.05, le=25, allow_inf_nan=False)


class OptionsIn(BaseModel):
    model_config = ConfigDict(extra='ignore')
    mode: Literal['usc_dining', 'off_campus']
    meal: Literal['breakfast', 'lunch', 'dinner', 'snack']
    date: Date | None = None
    at_time: str | None = Field(None, pattern=r'^\d{2}:\d{2}$')
    profile: ProfileIn = Field(default_factory=ProfileIn)
    targets: TargetsIn = Field(default_factory=TargetsIn)
    budget: BudgetIn = Field(default_factory=BudgetIn)
    campus: CampusIn = Field(default_factory=CampusIn)
    origin: OriginIn | None = None
    max_miles: float | None = Field(0.3, ge=0.05, le=25.0)   # null means any distance
    bands: list[BandIn] | None = Field(None, max_length=6)    # walking bands in miles; when given they replace max_miles
    rank_by: Literal['fit', 'nearest', 'cheapest', 'protein', 'lighter'] = 'fit'
    exclude_ids: list[str] = Field(default_factory=list, max_length=200)
    avoid_venue_ids: list[str] = Field(default_factory=list, max_length=50)
    pool_size: int = Field(600, ge=3, le=800)


def build_query(body: OptionsIn) -> engine.Query:
    return engine.Query(
        mode=body.mode, meal=body.meal, day=body.date or today_la(), diet=body.profile.diet, allergies=body.profile.allergies,
        exclusions=body.profile.exclusions, goal=body.profile.goal, cuisines=body.profile.preferred_cuisines,
        meal_kcal=body.targets.meal_kcal, meal_protein_g=body.targets.meal_protein_g, min_protein_g=body.targets.min_protein_g,
        max_kcal=body.targets.max_kcal, per_meal_usd=body.budget.per_meal_usd, daily_remaining_usd=body.budget.daily_remaining_usd,
        meals_left=body.budget.meals_left, swipes_remaining=body.campus.swipes_remaining, halls=list(body.campus.halls),
        include_retail=body.campus.include_retail, lat=body.origin.lat if body.origin else None,
        lng=body.origin.lng if body.origin else None, max_miles=body.max_miles, rank_by=body.rank_by,
        bands=[(b.min, b.max) for b in body.bands if b.max > b.min] if body.bands else None,
        exclude_ids=set(body.exclude_ids), avoid_venue_ids=set(body.avoid_venue_ids), pool_size=body.pool_size, at_time=body.at_time)


@router.post('/options')
def options(body: OptionsIn) -> dict:
    if body.mode == 'off_campus' and body.origin is None:
        raise HTTPException(status_code=422, detail='Choose a starting point before searching off campus.')
    try:
        return engine.recommend(build_query(body))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get('/bands')
def bands(lat: float = ApiQuery(..., ge=-90, le=90), lng: float = ApiQuery(..., ge=-180, le=180)) -> dict:
    return engine.band_overview(lat, lng, today_la())


class ParseIn(BaseModel):
    text: str = Field(min_length=1, max_length=400)


@router.post('/parse')
def parse(body: ParseIn) -> dict:
    return parse_mod.parse_request(body.text)


class ExplainIn(BaseModel):
    model_config = ConfigDict(extra='ignore')
    goal: str = Field('balanced', max_length=40)
    meal: Literal['breakfast', 'lunch', 'dinner', 'snack'] = 'lunch'
    options: list[dict] = Field(min_length=1, max_length=3)


@router.post('/explain')
def explain(body: ExplainIn) -> dict:
    try:
        notes = explain_mod.explain(body.options, body.goal, body.meal)
    except (KeyError, TypeError):
        notes = {}
    return {'notes': notes, 'source': 'model' if notes else 'engine'}


@router.get('/menu-status')
def menu_status(date: Date | None = None) -> dict:
    day = date or today_la()
    feeds = feed.fetch_all(day)
    venues, dishes, meta = dataset()
    halls = {}
    for key, (url, data, status) in feeds.items():
        counts = {}
        for meal in ('breakfast', 'lunch', 'dinner'):
            counts[meal] = len(feed.feed_dishes(key, url, data, meal, day, status)) if data else 0
        venue = next((v for v in venues.values() if v.hall_key == key), None)
        halls[key] = {'name': venue.name if venue else key, 'status': status, 'dishes': counts, 'url': feed.FEED_PAGE}
    return {'date': str(day), 'halls': halls, 'saved_menu': {'venues': len(venues), 'dishes': len(dishes), 'version': meta.get('version'),
            'generated_at': meta.get('generated_at')}}
