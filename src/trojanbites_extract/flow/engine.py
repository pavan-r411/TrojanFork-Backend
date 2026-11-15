"""Hard filters first, then transparent scoring. No model call decides what is allowed on the plate."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace
from datetime import date as Date, datetime, timezone

from trojanbites_extract.flow import feed, roles
from trojanbites_extract.flow.data import dataset
from trojanbites_extract.flow.model import (ANIMAL_NON_MEAT, DRINK_NAME, MEAT, NON_MEAL_CATEGORIES, Dish, Venue,
                                            canonical_allergen_tags)
from trojanbites_extract.query.filters import haversine_miles
from trojanbites_extract.recommend.restrictions import allergy_text_terms, canonical_allergies, mentions, stems

MEALS = ('breakfast', 'lunch', 'dinner', 'snack')
EAT_TIME = {'breakfast': '08:30', 'lunch': '12:30', 'dinner': '18:30', 'snack': '15:30'}
DEFAULT_KCAL = {'breakfast': 500.0, 'lunch': 650.0, 'dinner': 700.0, 'snack': 200.0}
LOSE = {'lose', 'gradual_weight_loss', 'weight_loss'}
GAIN = {'gain', 'gradual_weight_gain', 'weight_gain'}
STRENGTH = {'muscle', 'build_muscle', 'training', 'training_support'}
WALK_DETOUR = 1.25            # straight-line to street-route allowance
WALK_MIN_PER_MILE = 20.0      # 3 mph
ANY_DISTANCE_SCALE = 1.0      # with no walking limit, closeness still counts, spread over the first mile
# Walking bands. Together they cover every restaurant in the dataset (the farthest is about 1.1 miles from campus), so
# nobody is left out for being far: a student chooses which bands to include, and all three are on by default.
BANDS = ((0.0, 0.3), (0.3, 0.5), (0.5, 1.5))
BAND_LABEL = {(0.0, 0.3): 'Up to 0.3 mi', (0.3, 0.5): '0.3 to 0.5 mi', (0.5, 1.5): '0.5 to 1.5 mi'}
SNACKISH = {'snack entree', 'smoothie', 'side', 'sides', 'pastry', 'cookie', 'dessert', 'desserts', 'toast', 'protein box',
            'egg bites', 'appetizer', 'appetizers', 'bread', 'onigiri', 'musubi', 'cafe item', 'small plate'}
WEEKDAYS = ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')


@dataclass
class Query:
    mode: str
    meal: str
    day: Date
    diet: str = 'any'
    allergies: list[str] = field(default_factory=list)
    exclusions: list[str] = field(default_factory=list)
    goal: str = 'balanced'
    cuisines: list[str] = field(default_factory=list)
    meal_kcal: float | None = None
    meal_protein_g: float | None = None
    min_protein_g: float | None = None
    max_kcal: float | None = None
    per_meal_usd: float | None = None
    daily_remaining_usd: float | None = None
    meals_left: int = 1
    swipes_remaining: int | None = None
    halls: list[str] = field(default_factory=list)
    include_retail: bool = False
    lat: float | None = None
    lng: float | None = None
    max_miles: float | None = 0.3     # legacy single limit; None means no limit
    bands: list[tuple[float, float]] | None = None   # distance bands (from, to] in miles; when set they replace max_miles
    rank_by: str = 'fit'
    exclude_ids: set[str] = field(default_factory=set)
    avoid_venue_ids: set[str] = field(default_factory=set)
    pool_size: int = 600
    at_time: str | None = None


def _minutes(clock: str) -> int:
    hours, minutes = clock.split(':')[:2]
    return int(hours) * 60 + int(minutes)


def _clock_label(clock: str) -> str:
    h, m = (int(x) for x in clock.split(':')[:2])
    suffix = 'AM' if h < 12 else 'PM'
    return f'{(h % 12) or 12}{"" if m == 0 else f":{m:02d}"} {suffix}'


def hours_status(venue: Venue, day: Date, at: str) -> tuple[bool | None, str | None]:
    """(open?, label). None means the dataset has no hours for that weekday."""
    windows = (venue.weekly_hours or {}).get(WEEKDAYS[day.weekday()])
    if not windows:
        return (None, None) if windows is None else (False, 'Closed today')
    label = ', '.join(f"{_clock_label(w['open'])}–{_clock_label(w['close'])}" for w in windows)
    now = _minutes(at)
    for w in windows:
        start, end = _minutes(w['open']), _minutes(w['close'])
        if (start <= now < end) or (end <= start and (now >= start or now < end)):
            return True, label
    return False, label


def walk(venue: Venue, q: Query) -> tuple[float | None, float | None]:
    """(straight-line miles, estimated walking minutes)."""
    if q.lat is None or q.lng is None or venue.lat is None or venue.lng is None:
        return None, None
    miles = haversine_miles(q.lat, q.lng, venue.lat, venue.lng)
    return miles, float(max(1, round(miles * WALK_DETOUR * WALK_MIN_PER_MILE)))


# ---------------------------------------------------------------- hard filters

# Extra fail-closed keyword checks per allergen, on top of the published tags and the shared synonym scan: dishes whose
# source lists no allergens (or an incomplete list) are still caught when their name or description gives them away.
_LETTERS = lambda text: re.sub(r'[^a-z]', '', text.lower())
FLOW_TERMS = {
    'eggs': r'omelet\w*|frittata|quiche|meringue|custard|hollandaise|aioli|mayo(?:nnaise)?|french toast|\beggs?\b',
    'sesame': r'sesame|tahini|hummus|halva|za.?atar',
    'peanuts': r'peanuts?|satay|groundnut',
    'treenuts': r'almonds?|walnuts?|pecans?|cashews?|pistachios?|hazelnuts?|macadamia|pine nuts?|marzipan|praline|nutella|baklava|pesto',
    'soy': r'\bsoy\w*|tofu|edamame|tempeh|miso|teriyaki|tamari|shoyu',
    'dairy': r'milk|cheese|butter|cream|yogurt|yoghurt|queso|ricotta|mozzarella|parmesan|cheddar|feta|paneer|ghee|whey|casein|alfredo|tzatziki|custard|ice cream|latte',
    'fish': r'salmon|tuna|tilapia|\bcod\b|halibut|mahi|anchov\w*|sardines?|snapper|trout|\bfish\b|kanpachi|yellowtail|unagi|eel|caesar',
    'shellfish': r'shrimp|crab|lobster|clams?|oysters?|mussels?|scallops?|prawns?|crawfish|crayfish|calamari|squid|octopus',
    'gluten': r'\bwheat\b|\bflour\b|seitan|couscous|farro|barley|\bbread\w*|\bbuns?\b|pasta|noodles?|ramen|udon|pizza|bagels?|croissants?|muffins?|biscuits?|pancakes?|waffles?|crepes?|dumplings?|breaded|battered|tempura|panko|orzo|lasagna|gnocchi|pita|naan|flatbread|rolls?\b|pretzel|cake|cookie',
}
FLOW_TERMS['wheat'] = FLOW_TERMS['gluten']
_PLANT_PHRASES = re.compile(r'coconut (?:milk|cream|yogurt)|peanut butter|almond (?:milk|butter)|oat milk|soy (?:milk|yogurt)|cashew (?:cheese|cream)|butternut|cocoa butter|cream of tartar|vegan (?:cheese|butter)|gluten.free', re.I)


class Restrictions:
    """Allergy, diet and dislike rules compiled once per request."""

    def __init__(self, q: Query):
        self.tags, self.unmapped = canonical_allergies(q.allergies)
        self.text_terms = allergy_text_terms(q.allergies, include_synonyms=True)
        self.unmapped_stems = stems(self.unmapped)
        self.dislike_stems = stems(q.exclusions)
        self.diet = (q.diet or 'any').lower()
        self.has_allergy = bool(self.tags or self.unmapped)
        wanted = {_LETTERS(t) for t in self.tags} | {_LETTERS(a) for a in q.allergies}
        self.flow_patterns = [re.compile(FLOW_TERMS[k], re.I) for k in sorted(wanted) if k in FLOW_TERMS]

    def allergy_reason(self, d: Dish) -> str | None:
        if self.has_allergy and d.allergen_status == 'not_analyzed':
            return 'not_analyzed'
        if self.tags & d.allergens:
            return 'allergy'
        blob = d.text_blob()
        if self.text_terms and mentions(blob, self.text_terms):
            return 'allergy'
        if self.flow_patterns:
            cleaned = _PLANT_PHRASES.sub(' ', blob)
            if any(p.search(cleaned) for p in self.flow_patterns):
                return 'allergy'
        if self.unmapped_stems:
            raw = ' '.join(d.allergen_raw).lower()
            if mentions(blob, self.unmapped_stems) or any(s in raw for s in self.unmapped_stems):
                return 'allergy'
        return None

    def diet_ok(self, d: Dish) -> bool:
        if self.diet in {'', 'any', 'any diet', 'non-veg', 'omnivore'}:
            return True
        blob = f'{d.name} {d.ingredients_text}'
        if self.diet == 'halal':
            # Strict: only dishes the source marks halal, or meatless dishes. Unlabelled meat is never assumed halal.
            return bool(d.extra.get('halal')) or ((d.is_vegetarian or d.is_vegan) and not MEAT.search(blob))
        if self.diet in {'pescatarian', 'pescetarian'}:
            return not MEAT.search(PESCA_WORDS.sub(' ', blob))
        if MEAT.search(blob):
            return False
        if self.diet == 'vegetarian':
            return d.is_vegetarian
        if self.diet == 'vegan':
            return d.is_vegan and not (d.allergens & {'dairy', 'eggs'}) and not ANIMAL_NON_MEAT.search(blob)
        return True

    def dislike(self, d: Dish) -> bool:
        return bool(self.dislike_stems) and mentions(d.text_blob(), self.dislike_stems)


PESCA_WORDS = re.compile(r'\b(anchov\w*|tuna|salmon|shrimp|prawns?|crab|lobster|fish|tilapia|cod|halibut|mahi|calamari|squid|octopus|oysters?|clams?|mussels?|scallops?)\b', re.I)


def is_meal_like(d: Dish, meal: str) -> bool:
    if meal == 'snack':
        if 'snack' in d.meal_times or 'dessert' in d.meal_times:
            return not (DRINK_NAME.search(d.name) and 'smoothie' not in d.name.lower() and d.category != 'smoothie')
        return (d.category in SNACKISH and (d.calories or 999) <= 450
                and not (DRINK_NAME.search(d.name) and 'smoothie' not in d.name.lower()))
    if d.category in NON_MEAL_CATEGORIES or DRINK_NAME.search(d.name):
        return False
    return True


def in_range(q: Query, miles: float) -> bool:
    """Is a restaurant this far away inside what the student chose? Bands share their edges, so none can fall between two."""
    if q.bands:
        return any(lo - 1e-9 <= miles <= hi + 1e-9 for lo, hi in q.bands)
    return q.max_miles is None or miles <= q.max_miles + 1e-9


def reach(q: Query) -> float:
    """The farthest distance the student's choice allows, for scaling the closeness score."""
    if q.bands:
        return max(hi for _, hi in q.bands)
    return q.max_miles or ANY_DISTANCE_SCALE


def cash_cap(q: Query) -> float | None:
    caps = [c for c in (q.per_meal_usd, q.daily_remaining_usd) if c is not None]
    return min(caps) if caps else None


# ---------------------------------------------------------------- candidate pool

def _candidates(q: Query) -> tuple[list[Dish], dict, list[str]]:
    venues, dishes, _ = dataset()
    warnings: list[str] = []
    report: dict = {}
    if q.mode == 'usc_dining':
        pool, report = feed.hall_pool(q.meal, q.day, q.halls or None)
        if q.include_retail:
            pool += [d for d in dishes if venues[d.venue_id].kind == 'retail' and d.venue_id in venues
                     and (q.meal in d.meal_times or (q.meal == 'snack' and 'dessert' in d.meal_times))]
    else:
        pool = [d for d in dishes if venues[d.venue_id].category == 'off_campus'
                and (q.meal in d.meal_times or (q.meal == 'snack' and 'dessert' in d.meal_times) or q.meal == 'snack')]
    return pool, report, warnings


def eligible(q: Query, pool: list[Dish] | None = None) -> tuple[list[Dish], dict]:
    """Apply every hard filter. Returns (dishes that pass, count hidden per reason)."""
    venues, _, _ = dataset()
    if pool is None:
        pool, _, _ = _candidates(q)
    rules = Restrictions(q)
    cap = cash_cap(q)
    at = q.at_time or EAT_TIME[q.meal]
    hidden = {'allergy': 0, 'not_analyzed': 0, 'diet': 0, 'dislike': 0, 'budget': 0, 'distance': 0, 'closed': 0,
              'protein': 0, 'calories': 0, 'not_a_meal': 0, 'venue_unavailable': 0}
    kept: list[Dish] = []
    for d in pool:
        v = venues.get(d.venue_id)
        if v is None or not v.eligible:
            hidden['venue_unavailable'] += 1
            continue
        if d.id in q.exclude_ids:
            continue
        if not is_meal_like(d, q.meal):
            hidden['not_a_meal'] += 1
            continue
        reason = rules.allergy_reason(d)
        if reason:
            hidden[reason] += 1
            continue
        if not rules.diet_ok(d):
            hidden['diet'] += 1
            continue
        if rules.dislike(d):
            hidden['dislike'] += 1
            continue
        if d.price_kind == 'cash' and cap is not None and (d.price_usd is None or d.price_usd > cap + 1e-9):
            hidden['budget'] += 1
            continue
        miles, _ = walk(v, q)
        if v.kind != 'hall' and miles is not None and not in_range(q, miles):
            hidden['distance'] += 1
            continue
        if hours_status(v, q.day, at)[0] is False:
            hidden['closed'] += 1
            continue
        now = _minutes(at)
        a_from, a_until = d.extra.get('avail_from'), d.extra.get('avail_until')
        if (a_from is not None and now < a_from) or (a_until is not None and now >= a_until):
            hidden['closed'] += 1
            continue
        if q.min_protein_g and (d.protein_g is None or d.protein_g < q.min_protein_g):
            hidden['protein'] += 1
            continue
        if q.max_kcal and (d.calories is None or d.calories > q.max_kcal):
            hidden['calories'] += 1
            continue
        kept.append(d)
    return kept, hidden


# ---------------------------------------------------------------- scoring

def _weights(q: Query) -> dict[str, float]:
    goal = (q.goal or 'balanced').lower()
    if goal in STRENGTH:
        w = {'cal': .25, 'protein': .38, 'price': .08, 'dist': .10, 'cuisine': .08, 'conf': .11}
    elif goal in LOSE:
        w = {'cal': .38, 'protein': .22, 'price': .10, 'dist': .12, 'cuisine': .08, 'conf': .10}
    elif goal in GAIN:
        w = {'cal': .35, 'protein': .25, 'price': .10, 'dist': .10, 'cuisine': .08, 'conf': .12}
    else:
        w = {'cal': .36, 'protein': .16, 'price': .12, 'dist': .14, 'cuisine': .10, 'conf': .12}
    if q.cuisines:
        w['cuisine'] = .30  # the student named cuisines on purpose: let that show in the order, never in the filters
    total = sum(w.values())
    return {k: v / total for k, v in w.items()}


def targets(q: Query) -> tuple[float, float]:
    kcal = q.meal_kcal or DEFAULT_KCAL[q.meal]
    return kcal, (q.meal_protein_g or round(kcal * 0.25 / 4))


def score(d: Dish, v: Venue, q: Query, miles: float | None) -> tuple[float, dict]:
    goal = (q.goal or 'balanced').lower()
    kcal_target, protein_target = targets(q)
    if d.calories is None:
        cal_fit = 0.3
    else:
        dev = d.calories / kcal_target - 1
        if dev > 0:
            cal_fit = max(0.0, 1 - dev * (1.6 if goal in LOSE else 1.0))
        else:
            cal_fit = max(0.0, 1 - (-dev) * (1.6 if goal in GAIN else 0.8))
    protein_fit = 0.3 if d.protein_g is None else min(1.0, d.protein_g / protein_target)
    if d.protein_g and d.calories and goal in LOSE | STRENGTH and d.protein_g / d.calories * 100 >= 6:
        protein_fit = min(1.0, protein_fit + 0.1)
    cap = cash_cap(q) or 20.0
    if q.daily_remaining_usd is not None and q.meals_left > 0:
        cap = min(cap, max(8.0, q.daily_remaining_usd / q.meals_left * 1.35))
    price_fit = 1.0 if d.price_kind == 'swipe' or d.price_usd is None else max(0.0, 1 - 0.6 * d.price_usd / cap)
    scale = 0.5 if v.kind == 'hall' else max(reach(q), 0.3)
    dist_fit = 0.5 if miles is None else max(0.0, 1 - min(1.0, miles / scale))
    wanted = {c.casefold() for c in q.cuisines}
    cuisine_fit = 1.0 if wanted and ({c.casefold() for c in v.cuisines} & wanted or any(w in d.name.casefold() for w in wanted)) else 0.0
    conf = d.nutrition_confidence if d.calories is not None else 0.0
    w = _weights(q)
    parts = {'cal': cal_fit, 'protein': protein_fit, 'price': price_fit, 'dist': dist_fit, 'cuisine': cuisine_fit, 'conf': conf}
    total = sum(w[k] * parts[k] for k in w)
    if v.id in q.avoid_venue_ids:
        total -= 0.06
    return round(max(0.0, min(1.0, total)), 4), parts


NUTRITION_LABEL = {
    'verified_published': 'Published by the restaurant',
    'chain_pattern_estimate': "Estimated from the chain's standard recipe",
    'estimated': 'Estimated',
    'name_estimate': 'Rough estimate from the dish name',
}


def _money(value: float) -> str:
    return f'${value:.2f}'.replace('.00', '')


def reasons(d: Dish, v: Venue, q: Query, miles: float | None, minutes: float | None) -> list[str]:
    kcal_target, protein_target = targets(q)
    meal = q.meal
    out: list[str] = []
    if d.protein_g is not None and d.protein_g >= protein_target * 0.9:
        out.append(f'{d.protein_g:.0f} g protein covers {min(100, round(d.protein_g / protein_target * 100))}% of your {meal} target')
    elif d.calories is not None and abs(d.calories / kcal_target - 1) <= 0.15:
        out.append(f'About {d.calories:.0f} kcal, right on your {meal} budget')
    elif d.calories is not None and d.calories < kcal_target * 0.85:
        out.append(f'A lighter {d.calories:.0f} kcal, leaving room for the rest of your day')
    elif d.calories is not None:
        out.append(f'{d.calories:.0f} kcal is on the hearty side for a {meal}')
    diet = (q.diet or 'any').lower()
    if diet == 'vegan' and d.is_vegan:
        out.append('Vegan')
    elif diet in {'vegetarian', 'vegan'} and d.is_vegetarian:
        out.append('Vegetarian')
    if d.price_kind == 'swipe':
        out.append('Uses 1 meal swipe, no cash' if v.kind == 'hall' else 'Meal-swipe priced')
    elif d.price_usd is not None:
        cap = cash_cap(q)
        out.append(f'{_money(d.price_usd)}, under your {_money(cap)} limit' if cap is not None else f'{_money(d.price_usd)}')
    if q.cuisines and {c.casefold() for c in v.cuisines} & {c.casefold() for c in q.cuisines}:
        out.append('Matches your cuisine pick')
    if minutes is not None:
        out.append(f'{minutes:.0f} min walk')
    return out[:3]


def allergen_block(d: Dish) -> dict:
    contains = sorted(d.allergens | d.allergen_other)
    if d.allergen_status == 'not_analyzed':
        note = 'USC has not analyzed this dish for allergens. Ask dining staff before eating.'
    elif d.allergen_status == 'published':
        note = 'Allergens as published. Cross-contact is still possible, so confirm with staff.'
    else:
        note = 'Allergens from TrojanPlate saved menu data. Confirm with the venue.'
    return {'contains': contains, 'status': d.allergen_status, 'note': note}


def option(d: Dish, v: Venue, q: Query, score_value: float, miles: float | None, minutes: float | None) -> dict:
    open_now, hours_label = hours_status(v, q.day, q.at_time or EAT_TIME[q.meal])
    cents = None if d.price_usd is None or d.price_kind == 'swipe' else round(d.price_usd * 100)
    return {
        'id': d.id, 'name': d.name, 'category': d.category, 'description': d.description, 'station': d.station,
        'venue': {'id': v.id, 'name': v.name, 'kind': v.kind, 'cuisines': list(v.cuisines), 'address': v.address,
                  'lat': v.lat, 'lng': v.lng, 'price_level': v.price_level, 'website': v.website},
        'price': {'kind': d.price_kind, 'cash_cents': cents,
                  'label': ('1 swipe' if v.kind == 'hall' else '≈ one meal swipe') if d.price_kind == 'swipe' else (
                      _money(d.price_usd) if d.price_usd is not None else 'Price unavailable')},
        'nutrition': {'calories': d.calories, 'protein_g': d.protein_g, 'carbs_g': d.carbs_g, 'fat_g': d.fat_g,
                      'status': d.nutrition_status, 'confidence': d.nutrition_confidence,
                      'label': NUTRITION_LABEL.get(d.nutrition_status, 'Estimated')},
        'allergens': allergen_block(d),
        'diet': {'vegetarian': d.is_vegetarian, 'vegan': d.is_vegan, 'halal': bool(d.extra.get('halal'))},
        'walk': {'miles': None if miles is None else round(miles, 2), 'minutes': None if minutes is None else int(minutes), 'method': 'straight_line_estimate'},
        'hours': {'open': open_now, 'label': hours_label},
        'source': {'kind': d.source_kind, 'label': d.source_label, 'date': d.source_date, 'url': d.extra.get('feed_url') or v.source_url or v.website},
        'goal_tags': list(d.goal_tags), 'image_url': d.image_url, 'image': d.extra.get('image'), 'availability_note': d.availability_note,
        'subtitle': d.description if d.category == 'plate' else None, 'components': d.extra.get('components'),
        'score': score_value, 'reasons': reasons(d, v, q, miles, minutes),
    }


def paginate(options: list[dict], size: int = 3, spread: bool = True) -> list[list[int]]:
    """Group the ordered pool into pages of `size`, never repeating a dish name on a page.

    With `spread`, a page takes one dish per venue first, for variety. Without it the order is kept as it is, which is what
    "closest hall" needs: the nearest hall's plates come first, then the next hall's."""
    remaining = list(range(len(options)))
    pages: list[list[int]] = []
    norm = lambda s: re.sub(r'[^a-z]+', ' ', s.lower()).strip()
    while remaining:
        page: list[int] = []
        venues_seen: set[str] = set()
        names: set[str] = set()
        for i in list(remaining):
            if len(page) == size:
                break
            o = options[i]
            if (spread and o['venue']['id'] in venues_seen) or norm(o['name']) in names:
                continue
            page.append(i); venues_seen.add(o['venue']['id']); names.add(norm(o['name'])); remaining.remove(i)
        for i in list(remaining):
            if len(page) == size:
                break
            if norm(options[i]['name']) in names:
                continue
            page.append(i); names.add(norm(options[i]['name'])); remaining.remove(i)
        if not page:                       # only duplicate names left; take them rather than loop forever
            page = remaining[:size]
            remaining = remaining[size:]
        pages.append(page)
    return pages


SORTS = ('fit', 'nearest', 'cheapest', 'protein', 'lighter')
_FAR = 9e9


def sort_key(rank_by: str):
    """Ordering over (score, miles, minutes, dish, venue) rows. Every sort ends in score, then id, so ties are stable."""
    if rank_by == 'nearest':
        return lambda t: (round(t[1], 2) if t[1] is not None else _FAR, -t[0], t[3].id)
    if rank_by == 'cheapest':
        # Swipe-priced hall food all costs one swipe, so ties fall back to best fit. Unknown cash prices go last.
        return lambda t: ((t[3].price_usd if t[3].price_usd is not None else _FAR) if t[3].price_kind == 'cash' else 0.0, -t[0], t[3].id)
    if rank_by == 'protein':
        return lambda t: (-(round(t[3].protein_g / 2) if t[3].protein_g is not None else -1), -t[0], t[3].id)
    if rank_by == 'lighter':
        return lambda t: (round(t[3].calories / 50) if t[3].calories is not None else _FAR, -t[0], t[3].id)
    return lambda t: (-t[0], t[3].id)


def rank(q: Query, kept: list[Dish]) -> list[dict]:
    """Score every dish that passed the hard filters, then order the whole pool by the chosen sort."""
    venues, _, _ = dataset()
    scored = []
    for d in kept:
        v = venues[d.venue_id]
        miles, minutes = walk(v, q)
        s, _parts = score(d, v, q, miles)
        scored.append((s, miles, minutes, d, v))
    scored.sort(key=sort_key(q.rank_by if q.rank_by in SORTS else 'fit'))
    top = scored[:max(3, q.pool_size)]
    return [option(d, v, q, s, m, mins) for s, m, mins, d, v in top]


RELAX_STEPS = (0.5, 0.75, 1.0)


def relax_hints(q: Query, pool: list[Dish], hidden: dict, current: int) -> list[dict]:
    """What a student could loosen to see more choices. Allergies and diet are never offered."""
    hints = []
    if hidden.get('distance') and q.mode == 'off_campus' and q.bands:
        chosen = {tuple(b) for b in q.bands}
        for band in BANDS:
            if band in chosen:
                continue
            n = len(eligible(replace(q, bands=[*q.bands, band]), pool)[0])
            if n > current:
                hints.append({'key': 'distance_band', 'value': list(band), 'label': f'Add restaurants {BAND_LABEL[band].lower()} away', 'gain': n - current})
    elif hidden.get('distance') and q.mode == 'off_campus' and q.max_miles is not None:
        for miles in RELAX_STEPS:
            if miles > q.max_miles:
                n = len(eligible(replace(q, max_miles=miles), pool)[0])
                if n > current:
                    hints.append({'key': 'max_miles', 'value': miles, 'label': f'Walk up to {miles:g} mi', 'gain': n - current})
                    break
        n_all = len(eligible(replace(q, max_miles=None), pool)[0])
        if n_all > current:
            hints.append({'key': 'max_miles', 'value': None, 'label': 'Remove the walking limit', 'gain': n_all - current})
    if hidden.get('budget') and q.per_meal_usd is not None:
        for extra in (3, 6):
            n = len(eligible(replace(q, per_meal_usd=q.per_meal_usd + extra), pool)[0])
            if n > current:
                hints.append({'key': 'per_meal_usd', 'value': q.per_meal_usd + extra, 'label': f'Raise the meal limit to {_money(q.per_meal_usd + extra)}', 'gain': n - current})
                break
    if hidden.get('protein') and q.min_protein_g:
        n = len(eligible(replace(q, min_protein_g=None), pool)[0])
        if n > current:
            hints.append({'key': 'min_protein_g', 'value': None, 'label': 'Drop the protein minimum', 'gain': n - current})
    if hidden.get('dislike') and q.exclusions:
        n = len(eligible(replace(q, exclusions=[]), pool)[0])
        if n > current:
            hints.append({'key': 'exclusions', 'value': [], 'label': 'Ignore disliked foods for this meal', 'gain': n - current})
    if q.mode == 'usc_dining' and not q.include_retail:
        extra_q = replace(q, include_retail=True)
        n = len(eligible(extra_q)[0])
        if n > current:
            hints.append({'key': 'include_retail', 'value': True, 'label': 'Include campus cafés and restaurants', 'gain': n - current})
    return sorted(hints, key=lambda h: -h['gain'])


def recommend(q: Query) -> dict:
    if q.meal not in MEALS:
        raise ValueError('Unknown meal')
    pool, report, warnings = _candidates(q)
    kept, hidden = eligible(q, pool)
    if q.mode == 'usc_dining':
        kcal_target, protein_target = targets(q)
        plates = roles.compose(kept, q.meal, kcal_target, protein_target, (q.goal or 'balanced').lower())
        kept = plates + [d for d in kept if d.source_kind != 'usc_feed']
    options = rank(q, kept)
    hints = relax_hints(q, pool, hidden, len(kept)) if len(options) < 3 else []
    if q.mode == 'usc_dining':
        if q.swipes_remaining is not None and q.swipes_remaining <= 0:
            warnings.append('No meal swipes left today. A hall visit would be paid another way, so check the door price.')
        if any(r['status'] == 'saved' for r in report.values()):
            warnings.append("Some halls are showing TrojanPlate's saved sample menu because USC's live menu could not be read.")
    if any(o['nutrition']['status'] in {'name_estimate', 'estimated', 'chain_pattern_estimate'} for o in options):
        warnings.append('Calories and macros marked as estimates are approximate.')
    return {
        'meal': q.meal, 'mode': q.mode, 'date': str(q.day), 'generated_at': datetime.now(timezone.utc).isoformat(),
        'menu': {'halls': report},
        'targets': {'meal_kcal': targets(q)[0], 'meal_protein_g': targets(q)[1]},
        'options': options, 'pages': paginate(options, spread=not (q.mode == 'usc_dining' and q.rank_by == 'nearest')),
        'stats': {'considered': len(pool), 'eligible': len(kept), 'venues': len({d.venue_id for d in kept}),
                  'hidden': {k: v for k, v in hidden.items() if v}},
        'relax': hints, 'warnings': warnings,
    }


def band_overview(lat: float, lng: float, day: Date | None = None) -> dict:
    """Every off-campus restaurant, grouped by walking band from a starting point, so no restaurant is out of reach."""
    venues, dishes, _ = dataset()
    counts: dict[str, int] = {}
    for d in dishes:
        counts[d.venue_id] = counts.get(d.venue_id, 0) + 1
    q = Query(mode='off_campus', meal='lunch', day=day or Date.today(), lat=lat, lng=lng)
    bands = [{'min': lo, 'max': hi, 'label': BAND_LABEL[(lo, hi)], 'restaurants': []} for lo, hi in BANDS]
    unavailable, beyond = [], []
    for v in venues.values():
        if v.category != 'off_campus':
            continue
        miles, minutes = walk(v, q)
        if not v.eligible:
            unavailable.append({'id': v.id, 'name': v.name, 'reason': 'Reported closed' if 'closed' in (v.status or '') else 'Not available right now'})
            continue
        row = {'id': v.id, 'name': v.name, 'cuisines': list(v.cuisines), 'miles': None if miles is None else round(miles, 2),
               'minutes': None if minutes is None else int(minutes), 'dishes': counts.get(v.id, 0), 'address': v.address}
        home = next((b for b in bands if miles is not None and b['min'] - 1e-9 <= miles <= b['max'] + 1e-9 and (b['min'] == 0 or miles > b['min'])), None)
        (home['restaurants'] if home else beyond).append(row)
    for b in bands:
        b['restaurants'].sort(key=lambda r: (r['miles'], r['name']))
        b['count'] = len(b['restaurants'])
        b['dishes'] = sum(r['dishes'] for r in b['restaurants'])
    return {'bands': bands, 'total': sum(b['count'] for b in bands), 'beyond': beyond, 'unavailable': unavailable}
