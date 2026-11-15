"""Loads restaurants_usc_complete.json into normalised Venue/Dish records (cached by file mtime)."""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path

from trojanbites_extract.flow.model import Dish, Venue, canonical_allergen_tags
from trojanbites_extract.settings import ROOT

DATASET_PATH = ROOT / 'restaurants_usc_complete.json'
IMAGES_PATH = ROOT / 'dish_images.json'   # curated dish photos, built by scripts/build_dish_images.py
HALL_KEYS = (('everybody', 'evk'), ('parkside', 'parkside'), ('village', 'university-village'))

_lock = threading.Lock()
_cache: dict = {'mtime': None, 'venues': {}, 'dishes': [], 'meta': {}}


def _hall_key(name: str) -> str | None:
    lowered = name.lower()
    for needle, key in HALL_KEYS:
        if needle in lowered and ('dining hall' in lowered or 'evk' in lowered or 'kitchen' in lowered):
            return key
    return None


def _num(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _dish(raw: dict, venue: Venue, photos: dict | None = None) -> Dish | None:
    name = str(raw.get('dish_name') or '').strip()
    if not name or not raw.get('dish_id'):
        return None
    nutrition = raw.get('nutrition_per_serving') or {}
    price = raw.get('price') or {}
    diet = raw.get('dietary_compatibility') or {}
    tags, other = canonical_allergen_tags(raw.get('allergens_contains'))
    status = raw.get('nutrition_status') or 'estimated'
    goal_tags = tuple(t for t in (raw.get('goal_tags') or []) if isinstance(t, str) and len(t) > 2)
    swipe = price.get('pricing_model') == 'meal_swipe_fixed_cost'
    photo = (photos or {}).get(str(raw['dish_id']))
    own_image = raw.get('image_url') if isinstance(raw.get('image_url'), str) else None
    return Dish(
        id=str(raw['dish_id']), venue_id=venue.id, name=name, category=str(raw.get('category') or '').strip().lower(),
        meal_times=frozenset(str(m).lower() for m in raw.get('meal_times') or []),
        description=str(raw.get('description') or ''), price_usd=_num(price.get('amount_usd')),
        price_kind='swipe' if swipe else 'cash',
        calories=_num(nutrition.get('calories_kcal')), protein_g=_num(nutrition.get('protein_g')),
        carbs_g=_num(nutrition.get('carbohydrates_g')), fat_g=_num(nutrition.get('total_fat_g')),
        nutrition_status=status, nutrition_confidence=float(raw.get('nutrition_confidence_0_to_1') or 0.4),
        allergens=tags, allergen_other=other, allergen_raw=tuple(str(a) for a in raw.get('allergens_contains') or []),
        allergen_status='published' if status == 'verified_published' else 'curated',
        is_vegetarian=bool(diet.get('is_vegetarian')), is_vegan=bool(diet.get('is_vegan')),
        ingredients_text=str(raw.get('ingredients_text') or ''), goal_tags=goal_tags,
        image_url=(photo or {}).get('file') or own_image,
        extra={'image': {'source': photo.get('source'), 'match': photo.get('match'), 'page': photo.get('page')}} if photo else {},
        source_kind='dataset', source_label='Saved menu', source_date=str(raw.get('last_verified_at') or '') or None,
        availability_note=(raw['availability'] if isinstance(raw.get('availability'), str) and not re.fullmatch(r'[a-z_]+', raw['availability']) else None))


def _load() -> tuple[dict[str, Venue], list[Dish], dict]:
    data = json.loads(DATASET_PATH.read_text(encoding='utf-8'))
    try:
        photos = json.loads(IMAGES_PATH.read_text(encoding='utf-8')).get('images') or {}
    except (OSError, ValueError):
        photos = {}
    venues: dict[str, Venue] = {}
    dishes: list[Dish] = []
    for category in ('usc_dining', 'off_campus'):
        for raw in data.get(category) or []:
            loc = raw.get('location') or {}
            sub = raw.get('usc_subcategory')
            kind = 'restaurant' if category == 'off_campus' else ('hall' if sub == 'residential_dining_hall' else 'retail')
            hours = (raw.get('opening_hours') or {}).get('weekly') or {}
            venue = Venue(
                id=str(raw['restaurant_id']), name=str(raw['restaurant_name']), kind=kind, category=category,
                cuisines=tuple(str(c) for c in raw.get('cuisines') or []),
                lat=loc.get('latitude'), lng=loc.get('longitude'), address=loc.get('formatted_address'),
                price_level=(raw.get('price_level') or {}).get('symbol'), weekly_hours=hours,
                eligible=bool(raw.get('recommendation_eligible')), status=str(raw.get('operating_status') or ''),
                hall_key=_hall_key(str(raw['restaurant_name'])) if kind == 'hall' else None,
                website=(raw.get('contact') or {}).get('website'), source_url=raw.get('source_url'),
                phone=(raw.get('contact') or {}).get('phone'))
            venues[venue.id] = venue
            for dish_raw in raw.get('dishes') or []:
                dish = _dish(dish_raw, venue, photos)
                if dish:
                    dishes.append(dish)
    return venues, dishes, dict(data.get('metadata') or {})


def dataset() -> tuple[dict[str, Venue], list[Dish], dict]:
    mtime = (DATASET_PATH.stat().st_mtime, IMAGES_PATH.stat().st_mtime if IMAGES_PATH.exists() else 0)
    with _lock:
        if _cache['mtime'] != mtime:
            venues, dishes, meta = _load()
            _cache.update(mtime=mtime, venues=venues, dishes=dishes, meta=meta)
        return _cache['venues'], _cache['dishes'], _cache['meta']
