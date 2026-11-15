"""Today's official USC residential-dining menus, merged with the saved menu as a labelled fallback.

The feed (hospitality.usc.edu wp-json) publishes dishes, diet tags and allergens but no nutrition, so
nutrition comes from the saved menu when a dish matches closely and from a labelled name-based estimate
otherwise. A successful fetch is also written to disk so a later outage on the same day still serves
today's menu instead of dropping to the saved sample.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date as Date
from pathlib import Path

import httpx

from trojanbites_extract.flow import nutrition_guess, roles
from trojanbites_extract.flow.data import dataset
from trojanbites_extract.flow.model import Dish, canonical_allergen_tags
from trojanbites_extract.recommend import live
from trojanbites_extract.recommend.restrictions import feed_allergens
from trojanbites_extract.settings import ROOT

log = logging.getLogger(__name__)
CACHE_DIR = ROOT / 'data' / 'feed_cache'
HALL_KEYS = tuple(live.USC_HALLS)          # evk, parkside, university-village
FEED_PAGE = live.USC_MENU_PAGE
MATCH_THRESHOLD = 0.72


def _cache_path(key: str, day: Date) -> Path:
    return CACHE_DIR / f'{key}-{day.isoformat()}.json'


def fetch_hall(key: str, day: Date) -> tuple[str, dict | None, str]:
    """Return (feed url, feed json or None, status) where status is live | cached | unavailable."""
    try:
        url, data = live._usc_feed(key, day)
        if data.get('date') != day.strftime('%Y%m%d'):
            raise ValueError('USC returned a different menu date')
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            _cache_path(key, day).write_text(json.dumps({'saved_at': time.time(), 'url': url, 'data': data}), encoding='utf-8')
        except OSError:
            pass
        return url, data, 'live'
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        log.info('USC feed %s unavailable for %s: %s', key, day, type(exc).__name__)
    try:
        saved = json.loads(_cache_path(key, day).read_text(encoding='utf-8'))
        if saved['data'].get('date') == day.strftime('%Y%m%d'):
            return saved.get('url', ''), saved['data'], 'cached'
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return '', None, 'unavailable'


def fetch_all(day: Date, keys=HALL_KEYS) -> dict[str, tuple[str, dict | None, str]]:
    keys = list(keys)
    with ThreadPoolExecutor(max_workers=max(1, len(keys))) as pool:
        return dict(zip(keys, pool.map(lambda k: fetch_hall(k, day), keys)))


def _hall_venue(key: str):
    venues, _, _ = dataset()
    return next((v for v in venues.values() if v.hall_key == key), None)


def _saved_hall_dishes(key: str) -> list[Dish]:
    _, dishes, _ = dataset()
    venue = _hall_venue(key)
    return [d for d in dishes if venue and d.venue_id == venue.id]


def feed_dishes(key: str, url: str, data: dict, period: str, day: Date, status: str) -> list[Dish]:
    """Normalise one hall's feed for one meal period into Dish records."""
    venue = _hall_venue(key)
    if venue is None:
        return []
    meals = data.get('meals') or []
    wanted = live._usc_meal_periods(period, meals)
    saved = _saved_hall_dishes(key)
    out: dict[str, Dish] = {}
    for meal in meals:
        served_as = (meal.get('name') or '').lower()
        if served_as not in wanted:
            continue
        for station in meal.get('stations') or []:
            station_name = ' '.join(str(station.get('station') or '').split())
            if 'must register' in f"{station_name} {station.get('subtitle') or ''}".lower():
                continue
            for item in station.get('menu') or []:
                name = ' '.join(str(item.get('item') or '').split())
                if not name or live._is_notice(name) or live._is_component(name):
                    continue
                name, avail_note, avail_from, avail_until = split_availability(name)
                if not name or name.isupper() or re.search(r'^daily grill specials|\(including|^made to order station', name, re.I):
                    continue  # station headers and 'specials' banners are not dishes
                claims = {str(x).lower() for x in item.get('preferences') or []}
                tags = feed_allergens(item)
                analyzed = 'not-analyzed' not in tags
                canon = frozenset(t for t in tags if t != 'not-analyzed')
                values, _serving = live._feed_nutrition(item)
                published = any(v is not None for v in values.values())
                nutrition_status, confidence = ('verified_published', 0.9) if published else ('name_estimate', 0.25)
                if not published:
                    best = max(saved, key=lambda d: nutrition_guess.similar(name, d.name), default=None)
                    if best is not None and nutrition_guess.similar(name, best.name) >= MATCH_THRESHOLD:
                        values = {'calories': best.calories, 'protein_g': best.protein_g, 'carbs_g': best.carbs_g, 'fat_g': best.fat_g}
                        nutrition_status, confidence = 'estimated', 0.5
                    else:
                        values = nutrition_guess.guess(name, station_name, roles.role(name)) or {}
                dish_id = 'feed-' + hashlib.sha256(f'{key}|{day}|{served_as}|{name}'.encode()).hexdigest()[:16]
                if dish_id in out:
                    continue
                out[dish_id] = Dish(
                    id=dish_id, venue_id=venue.id, name=name, category=_category(name, station_name), meal_times=frozenset({period}),
                    description=f'{station_name}' if station_name else '', price_usd=0.0, price_kind='swipe',
                    calories=values.get('calories'), protein_g=values.get('protein_g'), carbs_g=values.get('carbs_g'),
                    fat_g=values.get('fat_g'), nutrition_status=nutrition_status, nutrition_confidence=confidence,
                    allergens=canon, allergen_other=frozenset(), allergen_raw=tuple(sorted(canon)),
                    allergen_status='published' if analyzed else 'not_analyzed',
                    is_vegetarian='vegetarian' in claims or 'vegan' in claims, is_vegan='vegan' in claims,
                    ingredients_text='', source_kind='usc_feed',
                    source_label=("Today's USC menu" if status == 'live' else "Today's USC menu (saved earlier today)"),
                    source_date=str(day), station=station_name or None,
                    availability_note=avail_note or (f'Served as {served_as.title()}' if served_as != period else None),
                    extra={'feed_url': url, 'served_as': served_as, 'halal': 'halal-ingredients' in claims,
                           'avail_from': avail_from, 'avail_until': avail_until})
    # Mains first so the ranking never leads with sides.
    return sorted(out.values(), key=lambda d: (-live._entree_score(d.name), d.name))


_AVAIL = re.compile(r'\s*\(?\s*(?P<note>available\s+(?P<kind>at|from|after|until|before)\s+(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ap>am|pm|a\.m\.|p\.m\.))\s*\)?', re.I)


def split_availability(name: str) -> tuple[str, str | None, int | None, int | None]:
    """'Oatmeal (available until 2pm)' -> ('Oatmeal', 'Available until 2pm', None, 840)."""
    found = _AVAIL.search(name)
    if not found:
        return name, None, None, None
    hour = int(found['h']) % 12 + (12 if found['ap'].lower().startswith('p') else 0)
    minute = hour * 60 + int(found['m'] or 0)
    kind = found['kind'].lower()
    clean = _AVAIL.sub('', name).strip()
    note = found['note'][0].upper() + found['note'][1:]
    return clean, note, (minute if kind in ('at', 'from', 'after') else None), (minute if kind in ('until', 'before') else None)


_CATEGORY_HINTS = (
    (re.compile(r'salad', re.I), 'salad'), (re.compile(r'soup|chowder|bisque|chili', re.I), 'soup'),
    (re.compile(r'pizza', re.I), 'pizza'), (re.compile(r'burger', re.I), 'burger'),
    (re.compile(r'sandwich|wrap|panini', re.I), 'sandwich'), (re.compile(r'taco|burrito|quesadilla|enchilada', re.I), 'taco'),
    (re.compile(r'pasta|spaghetti|penne|noodle|lasagna|mac', re.I), 'pasta'), (re.compile(r'bowl', re.I), 'bowl'),
    (re.compile(r'omelet|egg|scramble|frittata', re.I), 'breakfast entree'),
    (re.compile(r'oatmeal|pancake|waffle|french toast|cereal|yogurt', re.I), 'breakfast entree'),
)


def _category(name: str, station: str = '') -> str:
    if roles.is_dessert_station(station):
        return 'dessert'
    return next((label for pattern, label in _CATEGORY_HINTS if pattern.search(name)), 'entree')


def hall_pool(period: str, day: Date, halls: list[str] | None = None) -> tuple[list[Dish], dict[str, dict]]:
    """Dishes for the requested halls and meal period plus a per-hall status report.

    Per hall: live or cached official feed when it has dishes for the period, otherwise the saved menu.
    """
    keys = [k for k in HALL_KEYS if not halls or k in halls]
    feeds = fetch_all(day, keys)
    pool: list[Dish] = []
    report: dict[str, dict] = {}
    for key in keys:
        url, data, status = feeds[key]
        venue = _hall_venue(key)
        dishes = feed_dishes(key, url, data, period, day, status) if data else []
        if dishes:
            pool.extend(dishes)
            report[key] = {'name': venue.name if venue else key, 'status': status, 'source': 'usc_feed', 'dishes': len(dishes),
                           'menu_date': str(day), 'url': FEED_PAGE}
            continue
        saved = [d for d in _saved_hall_dishes(key) if period in d.meal_times or (period == 'snack' and 'dessert' in d.meal_times)]
        pool.extend(saved)
        reason = 'USC lists no dishes for this meal today' if data else 'USC menu feed unreachable'
        report[key] = {'name': venue.name if venue else key, 'status': 'saved', 'source': 'saved_menu', 'dishes': len(saved),
                       'menu_date': None, 'reason': reason, 'url': FEED_PAGE}
    return pool, report
