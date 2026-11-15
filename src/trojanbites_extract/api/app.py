from __future__ import annotations

import os
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any, Literal

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel, Field

from trojanbites_extract.campus.registry import list_campuses, load_campus, load_universities_registry
from trojanbites_extract.campus.resolve import resolve_campus
from trojanbites_extract.jobs.ingestion import (
    create_ingestion_job,
    get_job,
    tag_existing_pilot_as_usc,
)
from trojanbites_extract.plan.engine import plan_day, swap_meal
from trojanbites_extract.plan.menus import load_off_campus_menu, load_usc_dining_menu
from trojanbites_extract.plan.search import search_menus
from trojanbites_extract.plan.targets import estimate_daily_targets
from trojanbites_extract.query.filters import (
    DEFAULT_MAX_DISTANCE_MILES,
    MealQuery,
    filter_meals,
    nearby_restaurants,
)
from trojanbites_extract.recommend.live import LiveRequest, LiveDiscoveryError, live_suggest
from trojanbites_extract.recommend.service import UserPreferences, select_meals
from trojanbites_extract.settings import get_settings, load_extraction_config
from trojanbites_extract.auth.routes import router as accounts_router
from trojanbites_extract.store.db import init_db, session_scope
from trojanbites_extract.store.models import MenuItem, Restaurant


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Ensure .env overrides empty shell exports (common with GOOGLE_MAPS_API_KEY=)
    try:
        from dotenv import load_dotenv

        from trojanbites_extract.settings import ROOT, get_settings

        load_dotenv(ROOT / ".env", override=True)
        get_settings.cache_clear()
    except Exception:
        pass
    # Live recommendations do not need the legacy catalog database.
    # Vercel application files are read-only; initialize legacy storage lazily.
    if os.getenv("VERCEL") != "1":
        init_db()
        tag_existing_pilot_as_usc()
    yield


app = FastAPI(
    title="TrojanPlate API",
    description=(
        "TrojanPlate daily meal planning API. "
        "Live recommendations fetch official menus on demand using Google Places and OpenAI at /v1/live/plan. "
        "Snapshot planning remains available at /v1/plan/day and /v1/plan/swap. "
        "Missing nutrition stays null unless explicitly labeled AI estimates are enabled. "
        "Contract: docs/API_CONTRACT.md"

    ),
    version="0.6.0",
    lifespan=lifespan,
)

app.add_middleware(GZipMiddleware, minimum_size=1024)   # a full menu of options is large but compresses about 10 to 1
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(accounts_router)


class HealthOut(BaseModel):
    status: str
    product: str
    database_url: str
    campuses: list[str]
    ready: bool


@app.get("/health", response_model=HealthOut)
@app.get("/ready", response_model=HealthOut)
def health() -> HealthOut:
    cfg = load_extraction_config()
    campuses = [c.campus_id for c in list_campuses()]
    return HealthOut(
        status="ok",
        product=cfg.get("product_name", "TrojanPlate"),
        database_url=get_settings().database_url,
        campuses=campuses,
        ready=True,
    )


@app.get("/v1/campuses")
def campuses() -> dict[str, Any]:
    reg = load_universities_registry()
    items = []
    for c in list_campuses():
        items.append(
            {
                "campus_id": c.campus_id,
                "university_id": c.university_id,
                "display_name": c.display_name,
                "short_name": c.short_name,
                "center": {"lat": c.center_lat, "lng": c.center_lng},
                "boundary": {
                    "type": c.boundary_type,
                    "official": c.boundary_official,
                    "boundary_id": c.boundary_id,
                    "boundary_version": c.boundary_version,
                    "radius_miles": c.boundary_radius_miles,
                    "notes": c.boundary_notes,
                    "source_url": c.boundary_source_url,
                },
                "discovery": {
                    "default_walk_miles": c.default_walk_miles,
                    "max_walk_miles": c.max_walk_miles,
                },
            }
        )
    return {
        "product_scope": reg.get("product_scope", "usc_only"),
        "default_campus_id": reg.get("default_campus_id"),
        "judging_campus_id": reg.get("judging_campus_id", "usc_upc"),
        "count": len(items),
        "campuses": items,
    }


@app.get("/v1/usc/overview")
def usc_overview() -> dict[str, Any]:
    """USC pitch + snapshot stats for judges and campus partners."""
    usc = load_campus("usc_upc")
    dining = load_usc_dining_menu()
    off = load_off_campus_menu()
    return {
        "product": "TrojanPlate",
        "tagline": "Your goals. Your campus. Your plate.",
        "scope": "usc_upc",
        "university": "University of Southern California",
        "campus": {
            "campus_id": usc.campus_id,
            "display_name": usc.display_name,
            "center": {"lat": usc.center_lat, "lng": usc.center_lng},
            "default_walk_miles": usc.default_walk_miles,
            "boundary": {
                "type": usc.boundary_type,
                "official": usc.boundary_official,
                "boundary_id": usc.boundary_id,
                "source_url": usc.boundary_source_url,
                "notes": usc.boundary_notes,
            },
        },
        "friction": (
            "Trojans need a full-day diet plan from dining halls or nearby restaurants "
            "that respects goals, diet, budget, and walkability — without invented nutrition."
        ),
        "ai_guarantees": [
            "Day plans use verified menu snapshots — never fabricated dishes.",
            "Unknown calories/protein stay unavailable; nutrition estimation is off.",
            "Allergies and hard budgets always beat ranking preferences.",
            "Residential dining is meal-swipe / AYCE — no fake per-dish prices.",
        ],
        "catalog": {
            "usc_dining_dishes": len(dining.get("dishes") or []),
            "usc_dining_venues": len(dining.get("venues") or []),
            "off_campus_dishes": len(off.get("dishes") or []),
            "off_campus_venues": len(off.get("venues") or []),
            "hospitality_seeds": len(usc.seeds),
        },
        "demo": {
            "docs": "/docs",
            "plan": "POST /v1/plan/day",
            "swap": "POST /v1/plan/swap",
            "contract": "docs/API_CONTRACT.md",
            "script": "scripts/demo_usc.sh",
            "judging": "docs/JUDGING.md",
            "adoption": "docs/ADOPTION.md",
        },
        "adoption_partners": [
            "USC Student Government",
            "USC Hospitality",
            "DPS boundary reference (public patrol materials)",
        ],
    }


class PlanProfile(BaseModel):
    nutrition_goal: str = "balanced"
    dietary_preference: str | None = None
    allergies: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    preferred_foods: list[str] = Field(default_factory=list)
    prefer_high_protein: bool = False
    age_range: str | None = None
    activity_level: str | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    goal_weight_kg: float | None = None


class PlanSituation(BaseModel):
    mode: Literal["usc_dining", "off_campus", "hybrid"]
    meal_periods: list[str] = Field(default_factory=lambda: ["breakfast", "lunch", "dinner"])
    lat: float | None = 34.0224
    lng: float | None = -118.2851
    max_miles: float = Field(DEFAULT_MAX_DISTANCE_MILES, ge=0.05, le=5.0)
    preferred_cuisines: list[str] = Field(default_factory=list)
    budget_per_meal: float | None = None
    budget_daily: float | None = None
    meal_swipes_remaining: int | None = None
    dining_dollars_remaining: float | None = None
    include_snacks: bool = False
    menu_date: str | None = None
    ranking_priority: str = "balanced"
    min_protein: float | None = Field(None, ge=0, description="Minimum protein grams per dish")
    allow_estimated_nutrition: bool = True


class LockedMeal(BaseModel):
    meal_period: str
    dish_id: str
    status: Literal["selected", "eaten", "locked"] = "selected"


class PlanDayBody(BaseModel):
    profile: PlanProfile = Field(default_factory=PlanProfile)
    situation: PlanSituation
    locked: list[LockedMeal] = Field(default_factory=list)


class PlanSwapBody(BaseModel):
    profile: PlanProfile = Field(default_factory=PlanProfile)
    situation: PlanSituation
    locked: list[LockedMeal] = Field(default_factory=list)
    meal_period: str
    dish_id: str
    status: Literal["selected", "eaten", "locked"] = "selected"


@app.post("/v1/plan/day")
def api_plan_day(body: PlanDayBody) -> dict[str, Any]:
    return plan_day(
        body.profile.model_dump(),
        body.situation.model_dump(),
        [m.model_dump() for m in body.locked],
    )


@app.post("/v1/plan/swap")
def api_plan_swap(body: PlanSwapBody) -> dict[str, Any]:
    return swap_meal(
        body.profile.model_dump(),
        body.situation.model_dump(),
        [m.model_dump() for m in body.locked],
        meal_period=body.meal_period,  # type: ignore[arg-type]
        dish_id=body.dish_id,
        status=body.status,
    )


@app.post("/v1/profile/targets")
def api_profile_targets(body: PlanProfile) -> dict[str, Any]:
    """Estimated daily macro targets for Profile / nutrition rings (not dish macros)."""
    return estimate_daily_targets(body.model_dump())


@app.get("/v1/search")
def api_search(
    q: str = Query(..., min_length=1),
    mode: Literal["usc_dining", "off_campus", "all", "hybrid"] = "all",
    limit: int = Query(20, ge=1, le=100),
    menu_date: str | None = None,
) -> dict[str, Any]:
    return search_menus(q=q, mode=mode, limit=limit, menu_date=menu_date)


@app.get("/v1/menus/usc-dining")
def menus_usc_dining(menu_date: str | None = None) -> dict[str, Any]:
    data = load_usc_dining_menu(menu_date)
    return {
        "metadata": data.get("metadata"),
        "path": data.get("_path"),
        "venues": data.get("venues"),
        "dish_count": len(data.get("dishes") or []),
        "dishes": data.get("dishes"),
    }


@app.get("/v1/menus/off-campus")
def menus_off_campus() -> dict[str, Any]:
    data = load_off_campus_menu()
    return {
        "metadata": data.get("metadata"),
        "path": data.get("_path"),
        "venues": data.get("venues"),
        "dish_count": len(data.get("dishes") or []),
        "dishes": data.get("dishes"),
    }


@app.get("/v1/campuses/resolve")
def campuses_resolve(
    lat: float | None = None,
    lng: float | None = None,
    campus_id: str | None = None,
) -> dict[str, Any]:
    result = resolve_campus(lat=lat, lng=lng, campus_id=campus_id)
    return {
        "status": result.status,
        "active_campus_id": result.active_campus_id,
        "message": result.message,
        "user": {"lat": result.user_lat, "lng": result.user_lng},
        "candidates": [asdict(c) for c in result.candidates],
    }


class SelectCampusBody(BaseModel):
    campus_id: str
    lat: float | None = None
    lng: float | None = None


@app.post("/v1/campuses/select")
def campuses_select(body: SelectCampusBody) -> dict[str, Any]:
    result = resolve_campus(lat=body.lat, lng=body.lng, campus_id=body.campus_id)
    if result.status == "unresolved":
        raise HTTPException(status_code=404, detail=result.message)
    return {
        "status": result.status,
        "active_campus_id": result.active_campus_id,
        "message": result.message,
        "candidates": [asdict(c) for c in result.candidates],
    }


def _require_campus(campus_id: str | None, lat: float | None, lng: float | None) -> str:
    if campus_id:
        load_campus(campus_id)
        return campus_id
    result = resolve_campus(lat=lat, lng=lng)
    if result.active_campus_id:
        return result.active_campus_id
    raise HTTPException(
        status_code=409,
        detail={
            "error": "campus_unresolved",
            "message": result.message,
            "resolution_status": result.status,
            "candidates": [asdict(c) for c in result.candidates],
        },
    )


@app.get("/v1/restaurants")
def list_restaurants(
    campus_id: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
    boundary_only: bool = Query(True),
) -> dict[str, Any]:
    active = _require_campus(campus_id, lat, lng)
    statuses = {"inside", "boundary"} if boundary_only else None
    with session_scope() as session:
        rows = session.query(Restaurant).filter(Restaurant.campus_id == active).all()
        out = []
        for r in rows:
            if r.discontinued_at is not None:
                continue
            if statuses and r.boundary_status not in statuses:
                continue
            out.append(
                {
                    "restaurant_id": r.restaurant_id,
                    "campus_id": r.campus_id,
                    "name": r.name,
                    "branch_name": r.branch_name,
                    "lat": r.lat,
                    "lng": r.lng,
                    "boundary_status": r.boundary_status,
                    "cuisines": r.cuisines_json,
                    "website": r.website,
                    "menu_links": r.menu_links_json,
                    "business_status": r.business_status,
                }
            )
    return {"campus_id": active, "count": len(out), "restaurants": out}


@app.get("/v1/restaurants/nearby")
def restaurants_nearby(
    lat: float = Query(...),
    lng: float = Query(...),
    campus_id: str | None = None,
    max_miles: float = Query(DEFAULT_MAX_DISTANCE_MILES, ge=0.05, le=5.0),
) -> dict[str, Any]:
    active = _require_campus(campus_id, lat, lng)
    with session_scope() as session:
        rows = nearby_restaurants(
            session,
            user_lat=lat,
            user_lng=lng,
            max_distance_miles=max_miles,
            campus_id=active,
        )
    return {
        "campus_id": active,
        "user": {"lat": lat, "lng": lng},
        "max_miles": max_miles,
        "distance_metric": "haversine_miles_straight_line",
        "count": len(rows),
        "restaurants": [asdict(r) for r in rows],
    }


@app.get("/v1/restaurants/{restaurant_id}")
def restaurant_detail(restaurant_id: str) -> dict[str, Any]:
    with session_scope() as session:
        r = session.get(Restaurant, restaurant_id)
        if r is None:
            raise HTTPException(status_code=404, detail="restaurant_not_found")
        items = (
            session.query(MenuItem)
            .filter(MenuItem.restaurant_id == restaurant_id, MenuItem.available.is_(True))
            .all()
        )
        menu = []
        for item in items:
            variants = []
            for v in item.variants:
                nut = v.nutrition
                variants.append(
                    {
                        "variant_id": v.variant_id,
                        "size_label": v.size_label,
                        "serving_label": v.serving_label,
                        "price": {
                            "amount": v.price_amount,
                            "currency": v.currency,
                            "note": "menu_price_excludes_tax_and_fees",
                        },
                        "nutrition": None
                        if nut is None
                        else {
                            "evidence_status": nut.evidence_status,
                            "serving_basis": nut.serving_basis,
                            "published": {
                                "calories_kcal": nut.calories_kcal,
                                "protein_g": nut.protein_g,
                                "carbohydrates_g": nut.carbohydrates_g,
                                "fat_g": nut.fat_g,
                                "fiber_g": nut.fiber_g,
                                "sugar_g": nut.sugar_g,
                                "sodium_mg": nut.sodium_mg,
                            },
                            "estimated": nut.estimated_json,
                        },
                    }
                )
            menu.append(
                {
                    "item_id": item.item_id,
                    "name": item.name,
                    "description": item.description,
                    "category": item.category,
                    "dietary_claims": item.dietary_claims_json,
                    "variants": variants,
                }
            )
        return {
            "restaurant": {
                "restaurant_id": r.restaurant_id,
                "campus_id": r.campus_id,
                "university_id": r.university_id,
                "name": r.name,
                "branch_name": r.branch_name,
                "address": r.address_json,
                "lat": r.lat,
                "lng": r.lng,
                "boundary_status": r.boundary_status,
                "cuisines": r.cuisines_json,
                "website": r.website,
                "service": r.service_json,
            },
            "menu_items": menu,
        }


@app.get("/v1/meals")
@app.get("/v1/search/dishes")
def meals_query(
    campus_id: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
    max_miles: float | None = None,
    budget_max: float | None = Query(None, ge=0),
    diet: list[str] = Query(default_factory=list),
    cuisine: list[str] = Query(default_factory=list),
    min_protein: float | None = Query(None, ge=0),
    min_calories: float | None = Query(None, ge=0),
    max_calories: float | None = Query(None, ge=0),
    meal_period: str | None = None,
    allow_uncertain: bool = False,
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    if (lat is None) ^ (lng is None):
        raise HTTPException(status_code=400, detail="Provide both lat and lng, or neither")
    active = _require_campus(campus_id, lat, lng)
    q = MealQuery(
        campus_id=active,
        budget_max=budget_max,
        diet_claims_required=diet,
        cuisine_any=cuisine or None,
        min_published_protein_g=min_protein,
        min_published_calories_kcal=min_calories,
        max_published_calories_kcal=max_calories,
        meal_period=meal_period,
        strict=not allow_uncertain,
        user_lat=lat,
        user_lng=lng,
        max_distance_miles=max_miles,
    )
    with session_scope() as session:
        hits = filter_meals(session, q)
    trimmed = hits[:limit]
    return {
        "campus_id": active,
        "query": {
            "lat": lat,
            "lng": lng,
            "max_miles": max_miles
            if max_miles is not None
            else (DEFAULT_MAX_DISTANCE_MILES if lat is not None else None),
            "budget_max": budget_max,
            "diet": diet,
            "cuisine": cuisine,
            "min_protein": min_protein,
            "meal_period": meal_period,
            "strict": not allow_uncertain,
            "price_basis": "menu_price_excludes_tax_and_fees",
            "distance_metric": "haversine_miles_straight_line",
        },
        "count": len(trimmed),
        "total_matches": len(hits),
        "meals": [asdict(h) for h in trimmed],
        "note": "Unknown nutrition cannot satisfy verified nutrition requirements.",
    }


class SuggestBody(BaseModel):
    lat: float | None = None
    lng: float | None = None
    campus_id: str | None = None
    max_miles: float = Field(DEFAULT_MAX_DISTANCE_MILES, ge=0.05, le=5.0)
    budget_max: float | None = None
    diet: list[str] = Field(default_factory=list)
    cuisine: list[str] = Field(default_factory=list)
    min_protein: float | None = None
    meal_period: str | None = None
    limit: int = Field(20, ge=1, le=100)
    collect_missing: bool = True
    personalize: bool = True
    preferences: UserPreferences = Field(default_factory=UserPreferences)


@app.post("/v1/suggest")
@app.post("/v1/recommendations")
def suggest(body: SuggestBody) -> dict[str, Any]:
    active = _require_campus(body.campus_id, body.lat, body.lng)
    job_info = None
    if body.collect_missing:
        job_info = create_ingestion_job(active, run_async=True)

    near: list[Any] = []
    meals: list[Any] = []
    with session_scope() as session:
        if body.lat is not None and body.lng is not None:
            near = nearby_restaurants(
                session,
                user_lat=body.lat,
                user_lng=body.lng,
                max_distance_miles=body.max_miles,
                campus_id=active,
            )
        q = MealQuery(
            campus_id=active,
            budget_max=body.budget_max,
            diet_claims_required=body.diet,
            cuisine_any=body.cuisine or None,
            min_published_protein_g=body.min_protein,
            meal_period=body.meal_period,
            strict=True,
            user_lat=body.lat,
            user_lng=body.lng,
            max_distance_miles=body.max_miles if body.lat is not None else None,
        )
        meals = filter_meals(session, q)
    personalization = select_meals(meals, body.preferences, body.meal_period) if body.personalize else None
    # Restrictions remain enforced even when personalization is explicitly disabled.
    if not body.personalize and (body.preferences.allergies or body.preferences.excluded_ingredients):
        personalization = select_meals([], body.preferences, body.meal_period)
    suggested = personalization.meals[:body.limit] if personalization else [asdict(m) for m in meals[:body.limit]]

    return {
        "mode": "location_enabled" if body.lat is not None else "campus_selected",
        "campus_id": active,
        "user": {"lat": body.lat, "lng": body.lng},
        "max_miles": body.max_miles,
        "distance_metric": "haversine_miles_straight_line",
        "price_basis": "menu_price_excludes_tax_and_fees",
        "nearby_restaurants": [asdict(r) for r in near],
        "suggested_meals": suggested,
        "personalization": personalization.model_dump(exclude={'meals'}) if personalization else {'provider': 'deterministic', 'status': 'not_requested', 'warnings': []},
        "counts": {"restaurants": len(near), "meals": len(suggested)},
        "ingestion_job": job_info,
        "explanations": [
            {
                "type": personalization.provider if personalization else "deterministic",
                "text": (
                    f"Showing stored {active} matches only. AI ranks eligible records when available. "
                    "Constraints are not silently relaxed. "
                    "Missing calories/protein stay unknown."
                ),
            }
        ],
    }


class IngestBody(BaseModel):
    campus_id: str
    run_async: bool = True


@app.post("/v1/ingestion/jobs")
def start_ingestion(
    body: IngestBody,
    x_ingest_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """Paid/slow collection. Optional token gate via INGEST_API_TOKEN env."""
    expected = get_settings().root  # placate linter; real check below
    _ = expected
    import os

    token = os.getenv("INGEST_API_TOKEN")
    if token and x_ingest_token != token:
        raise HTTPException(status_code=401, detail="ingestion_unauthorized")
    try:
        load_campus(body.campus_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return create_ingestion_job(body.campus_id, run_async=body.run_async)


@app.get("/v1/ingestion/jobs/{job_id}")
def ingestion_status(job_id: str) -> dict[str, Any]:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job_not_found")
    return job


def create_app() -> FastAPI:
    return app


@app.post('/v1/live/suggest')
def live_recommendations(body: 'LiveRequest') -> dict[str, Any]:
    try:
        return live_suggest(body)
    except LiveDiscoveryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


from trojanbites_extract.recommend.frontend import PlanRequest, daily_plan

@app.post('/v1/live/plan')
def frontend_daily_plan(body: PlanRequest) -> dict[str, Any]:
    try:
        return daily_plan(body)
    except LiveDiscoveryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

from trojanbites_extract.flow.routes import router as flow_router
app.include_router(flow_router)

# The frontend and API share an origin; no backend URL is embedded in browser code.
from fastapi.staticfiles import StaticFiles
from pathlib import Path
_frontend = Path(__file__).resolve().parents[4] / 'TrojanFork-Frontend'
class FrontendFiles(StaticFiles):
    async def get_response(self, path, scope):
        if any(part.startswith('.') for part in Path(path).parts):
            raise HTTPException(status_code=404)
        response=await super().get_response(path, scope)
        response.headers['Cache-Control']='no-store'
        return response

if _frontend.is_dir():
    app.mount('/ui', FrontendFiles(directory=str(_frontend), html=True), name='trojanplate-ui')
    from fastapi.responses import RedirectResponse
    @app.get('/')
    def frontend_home():
        return RedirectResponse('/ui/')
