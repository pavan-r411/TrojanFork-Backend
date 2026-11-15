from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy.orm import Session, joinedload

from trojanbites_extract.store.models import MenuItem, MenuVariant, Nutrition, Restaurant

# Product default: walkable nearby
DEFAULT_MAX_DISTANCE_MILES = 0.3


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Straight-line distance in miles. Prefer walking-route distance later if available."""
    r = 3958.7613
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@dataclass
class MealQuery:
    campus_id: str | None = None
    budget_max: float | None = None
    diet_claims_required: list[str] = field(default_factory=list)
    cuisine_any: list[str] | None = None
    min_published_protein_g: float | None = None
    min_published_calories_kcal: float | None = None
    max_published_calories_kcal: float | None = None
    meal_period: str | None = None
    boundary_statuses: list[str] = field(
        default_factory=lambda: ["inside", "boundary"]
    )
    allow_estimated_nutrition: bool = False
    strict: bool = True
    user_lat: float | None = None
    user_lng: float | None = None
    max_distance_miles: float | None = None


@dataclass
class MealHit:
    item_id: str
    restaurant_id: str
    restaurant_name: str
    item_name: str
    price_amount: float | None
    currency: str | None
    published_protein_g: float | None
    published_calories_kcal: float | None
    match_class: Literal["strict", "uncertain_alternative"]
    uncertain_reasons: list[str]
    distance_miles: float | None = None
    restaurant_lat: float | None = None
    restaurant_lng: float | None = None
    campus_id: str | None = None
    variant_id: str | None = None
    published_carbohydrates_g: float | None = None
    published_fat_g: float | None = None
    serving_label: str | None = None
    nutrition_evidence_status: str = 'unknown'
    ai_estimates: dict | None = None
    cuisines: list[str] = field(default_factory=list)
    diet_claims: list[str] = field(default_factory=list)
    price_note: str = "menu_price_excludes_tax_and_fees"
    distance_metric: str = "haversine_miles_straight_line"


@dataclass
class NearbyRestaurant:
    restaurant_id: str
    name: str
    branch_name: str | None
    distance_miles: float
    lat: float
    lng: float
    cuisines: list[str]
    boundary_status: str
    menu_item_count: int
    campus_id: str | None = None


def _has_diet_claim(item: MenuItem, required: list[str]) -> bool:
    claims = {
        str(c.get("claim", "")).lower()
        for c in (item.dietary_claims_json or [])
        if isinstance(c, dict)
    }
    return all(r.lower() in claims for r in required)


def _distance_or_none(
    restaurant: Restaurant, q: MealQuery
) -> tuple[float | None, bool]:
    if q.user_lat is None or q.user_lng is None:
        return None, True
    if restaurant.lat is None or restaurant.lng is None:
        return None, False if q.strict else True
    dist = haversine_miles(q.user_lat, q.user_lng, restaurant.lat, restaurant.lng)
    max_d = (
        q.max_distance_miles
        if q.max_distance_miles is not None
        else DEFAULT_MAX_DISTANCE_MILES
    )
    return dist, dist <= max_d


def nearby_restaurants(
    session: Session,
    *,
    user_lat: float,
    user_lng: float,
    max_distance_miles: float = DEFAULT_MAX_DISTANCE_MILES,
    campus_id: str | None = None,
    boundary_statuses: list[str] | None = None,
) -> list[NearbyRestaurant]:
    statuses = boundary_statuses or ["inside", "boundary"]
    q = session.query(Restaurant)
    if campus_id:
        q = q.filter(Restaurant.campus_id == campus_id)
    rows = q.all()
    out: list[NearbyRestaurant] = []
    for r in rows:
        if r.discontinued_at is not None:
            continue
        if r.boundary_status not in statuses:
            continue
        if r.lat is None or r.lng is None:
            continue
        dist = haversine_miles(user_lat, user_lng, r.lat, r.lng)
        if dist > max_distance_miles:
            continue
        menu_count = (
            session.query(MenuItem)
            .filter(MenuItem.restaurant_id == r.restaurant_id, MenuItem.available.is_(True))
            .count()
        )
        out.append(
            NearbyRestaurant(
                restaurant_id=r.restaurant_id,
                name=r.name,
                branch_name=r.branch_name,
                distance_miles=round(dist, 3),
                lat=r.lat,
                lng=r.lng,
                cuisines=list(r.cuisines_json or []),
                boundary_status=r.boundary_status,
                menu_item_count=menu_count,
                campus_id=r.campus_id,
            )
        )
    out.sort(key=lambda x: x.distance_miles)
    return out


def filter_meals(session: Session, q: MealQuery) -> list[MealHit]:
    """Deterministic filters. Campus isolation is required when campus_id is set."""
    query = (
        session.query(MenuItem)
        .options(
            joinedload(MenuItem.restaurant),
            joinedload(MenuItem.variants).joinedload(MenuVariant.nutrition),
        )
        .filter(MenuItem.available.is_(True))
    )
    items = query.all()

    hits: list[MealHit] = []
    for item in items:
        restaurant: Restaurant = item.restaurant
        if q.campus_id and restaurant.campus_id != q.campus_id:
            continue
        if restaurant.boundary_status not in q.boundary_statuses:
            continue
        if restaurant.discontinued_at is not None:
            continue

        dist, include = _distance_or_none(restaurant, q)
        if not include:
            continue

        if q.cuisine_any:
            cuisines = {c.lower() for c in (restaurant.cuisines_json or [])}
            if not cuisines.intersection({c.lower() for c in q.cuisine_any}):
                continue

        uncertain: list[str] = []
        if q.diet_claims_required:
            if not _has_diet_claim(item, q.diet_claims_required):
                if q.strict:
                    continue
                uncertain.append("diet_claim_missing")

        if q.meal_period:
            periods = [
                p.lower()
                for p in (item.availability_json or {}).get("meal_periods") or []
            ]
            if periods and q.meal_period.lower() not in periods:
                if q.strict:
                    continue
                uncertain.append("meal_period_unconfirmed")

        for variant in item.variants:
            price = variant.price_amount
            if q.budget_max is not None:
                if price is None:
                    if q.strict:
                        continue
                    uncertain.append("price_unknown")
                elif price > q.budget_max:
                    continue

            nut: Nutrition | None = variant.nutrition
            protein = nut.protein_g if nut else None
            calories = nut.calories_kcal if nut else None
            status = nut.evidence_status if nut else "unknown"

            if q.min_published_protein_g is not None:
                if status != "restaurant_published" or protein is None:
                    continue
                if protein < q.min_published_protein_g:
                    continue

            if q.min_published_calories_kcal is not None:
                if status != "restaurant_published" or calories is None:
                    continue
                if calories < q.min_published_calories_kcal:
                    continue
            if q.max_published_calories_kcal is not None:
                if status != "restaurant_published" or calories is None:
                    continue
                if calories > q.max_published_calories_kcal:
                    continue

            if q.strict and uncertain:
                continue

            hits.append(
                MealHit(
                    item_id=item.item_id,
                    variant_id=variant.variant_id,
                    serving_label=variant.serving_label,
                    nutrition_evidence_status=status,
                    published_carbohydrates_g=nut.carbohydrates_g if nut and status == 'restaurant_published' else None,
                    published_fat_g=nut.fat_g if nut and status == 'restaurant_published' else None,
                    restaurant_id=restaurant.restaurant_id,
                    restaurant_name=restaurant.name,
                    item_name=item.name,
                    price_amount=price,
                    currency=variant.currency,
                    published_protein_g=protein if status == "restaurant_published" else None,
                    published_calories_kcal=calories
                    if status == "restaurant_published"
                    else None,
                    match_class="uncertain_alternative" if uncertain else "strict",
                    uncertain_reasons=uncertain,
                    distance_miles=round(dist, 3) if dist is not None else None,
                    restaurant_lat=restaurant.lat,
                    restaurant_lng=restaurant.lng,
                    campus_id=restaurant.campus_id,
                )
            )

    if q.user_lat is not None and q.user_lng is not None:
        hits.sort(key=lambda h: (h.distance_miles is None, h.distance_miles or 1e9))
    return hits
