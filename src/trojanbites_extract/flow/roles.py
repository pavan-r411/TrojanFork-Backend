"""Tell mains from sides in a dining-hall feed, and build whole plates from them.

A dining-hall visit is one meal swipe, and nobody eats a lone side of squash. So hall recommendations are
plates: one main plus up to two sides from the same hall, chosen so the total lands near the meal's calorie
and protein target. Every component has already passed the allergy, diet and dislike filters.
"""
from __future__ import annotations

import hashlib
import itertools
import re

from trojanbites_extract.flow.model import Dish

TOPPER_WORDS = re.compile(r'\b(bacon|sausage|ham|canadian bacon)\b', re.I)
DELI_WORDS = re.compile(r'\b(salami|pepperoni|prosciutto|chorizo|pastrami|bologna|mortadella)\b', re.I)
PROTEIN_WORDS = re.compile(r'\b(chicken|beef|pork|turkey|steak|tilapia|salmon|tuna|shrimp|fish|cod|halibut|mahi|tofu|tempeh|seitan|'
                           r'jackfruit|lentils?|beans?|chickpeas?|eggs?|omelet\w*|meatballs?|lamb|brisket|ribs?|'
                           r'carnitas|falafel|paneer|duck|veal|bison|scrambled|pot roast|meatloaf|frittata|quiche|hot dogs?|corn dogs?|brats?|bratwurst|schnitzel|cutlet|fillet|kebab|gyro)\b', re.I)
DISH_WORDS = re.compile(r'\b(burgers?|pizza|pasta|tacos?|enchiladas?|casserole|sandwich(?:es)?|wraps?|curry|bowl|soup|bisque|chowder|'
                        r'stew|chili|lasagna|quesadillas?|burritos?|noodles?|ramen|pho|crepes?|waffles?|pancakes?|oatmeal|mulita|'
                        r'parmesan|bolognese|shepherds?|stir.?fry|fried rice|dumplings?|bao|kebabs?|skewers?|empanadas?|'
                        r'mac(?:aroni)?(?: and | & )cheese|flatbread|calzone|biryani|dal|french toast|granola|cereal)\b', re.I)
SWEET_MAIN = re.compile(r'\b(pancakes?|waffles?|crepes?|french toast|oatmeal|granola|cereal|porridge|parfait)\b', re.I)
COMPLETE_MAIN = re.compile(r'\b(burgers?|pizza|pasta|tacos?|enchiladas?|casserole|sandwich(?:es)?|wraps?|curry|bowl|soup|bisque|chowder|'
                           r'stew|chili|lasagna|quesadillas?|burritos?|noodles?|ramen|pho|mulita|shepherds?|stir.?fry|fried rice|'
                           r'dumplings?|mac(?:aroni)?(?: and | & )cheese|flatbread|calzone|biryani)\b', re.I)
BREAKFASTY = re.compile(r'\b(eggs?|omelet\w*|scrambled|frittata|quiche|pancakes?|waffles?|french toast|oatmeal|bagel|biscuit|hash)\b', re.I)

_CLASSES = (
    ('veg', re.compile(r'brussels|saut[eé]ed|roasted|steamed|onions?|broccoli|carrots?|spinach|kale|green beans|asparagus|zucchini|squash|cauliflower|medley', re.I)),
    ('fruit', re.compile(r'fruit|melon|berries|apple|banana|orange|grapes|pineapple|mango|papaya', re.I)),
    ('yogurt', re.compile(r'yogurt|parfait|cottage cheese', re.I)),
    ('soup', re.compile(r'soup|broth|bisque|chowder', re.I)),
    ('salad', re.compile(r'salad|slaw|greens$|coleslaw', re.I)),
    ('dip', re.compile(r'hummus|guacamole|salsa|tzatziki|baba', re.I)),
    ('bakery', re.compile(r'muffin|pastr|danish|croissant|scone|donut|doughnut|cake|coffee cake', re.I)),
    ('bread', re.compile(r'bread|roll|biscuit|cornbread|toast|bagel|naan|pita|tortilla|bun', re.I)),
    ('starch', re.compile(r'rice|grain|quinoa|couscous|pilaf|polenta|barley|farro|noodles?|pasta|potato|fries|plantain|corn|mashed|yam|tots?|hash', re.I)),
    ('veg', re.compile(r'squash|broccoli|carrot|spinach|kale|green beans|asparagus|zucchini|cabbage|peppers?|vegetables?|brussels|cauliflower|beets?|mushrooms?|eggplant|onions?|tomato|chard|bok choy|medley|edamame|corn on|roasted|steamed|sauteed|sautéed', re.I)),
)


def role(name: str) -> str:
    if DELI_WORDS.search(name) and not DISH_WORDS.search(name):
        return 'skip'
    if TOPPER_WORDS.search(name) and not DISH_WORDS.search(name) and not re.search(r'\b(burger|sandwich|pizza)\b', name, re.I):
        return 'topper'
    return 'main' if PROTEIN_WORDS.search(name) or DISH_WORDS.search(name) else 'side'


def side_class(name: str) -> str:
    if role(name) == 'topper':
        return 'topper'
    return next((c for c, pat in _CLASSES if pat.search(name)), 'veg')


def allowed_classes(main: str) -> set[str]:
    if SWEET_MAIN.search(main):
        return {'fruit', 'yogurt', 'topper'}
    if BREAKFASTY.search(main):
        return {'fruit', 'yogurt', 'topper', 'bread', 'bakery', 'starch'}
    if COMPLETE_MAIN.search(main):
        return {'veg', 'salad', 'fruit', 'soup'} if re.search(r'\b(burger|sandwich|wrap|taco|pizza|flatbread|quesadilla|burrito)\b', main, re.I) \
            else {'veg', 'salad', 'fruit', 'bread', 'soup'}
    return {'starch', 'veg', 'salad', 'bread', 'fruit', 'dip'}


DESSERT_STATION = re.compile(r'sweet|treat|dessert|bakery|pastr|ice cream|bake', re.I)


def is_dessert_station(station: str | None) -> bool:
    return bool(station and DESSERT_STATION.search(station))


def _plate_id(parts: list[Dish]) -> str:
    return 'plate-' + hashlib.sha256('|'.join(p.id for p in parts).encode()).hexdigest()[:16]


def _sum(parts: list[Dish], attr: str) -> float | None:
    values = [getattr(p, attr) for p in parts]
    return None if any(v is None for v in values) else float(sum(values))


def make_plate(main: Dish, sides: list[Dish], meal: str) -> Dish:
    parts = [main, *sides]
    weakest = min(parts, key=lambda p: p.nutrition_confidence)
    allergen_status = 'not_analyzed' if any(p.allergen_status == 'not_analyzed' for p in parts) else 'published'
    return Dish(
        id=_plate_id(parts), venue_id=main.venue_id, name=main.name, category='plate', meal_times=frozenset({meal}),
        description=('with ' + ' and '.join(s.name for s in sides)) if sides else '', price_usd=0.0, price_kind='swipe',
        calories=_sum(parts, 'calories'), protein_g=_sum(parts, 'protein_g'), carbs_g=_sum(parts, 'carbs_g'), fat_g=_sum(parts, 'fat_g'),
        nutrition_status=weakest.nutrition_status, nutrition_confidence=min(p.nutrition_confidence for p in parts),
        allergens=frozenset().union(*(p.allergens for p in parts)), allergen_other=frozenset(),
        allergen_raw=tuple(sorted(frozenset().union(*(p.allergens for p in parts)))), allergen_status=allergen_status,
        is_vegetarian=all(p.is_vegetarian for p in parts), is_vegan=all(p.is_vegan for p in parts),
        ingredients_text=', '.join(p.name for p in parts), source_kind='usc_feed', source_label=main.source_label,
        source_date=main.source_date, station=main.station, availability_note=main.availability_note,
        extra={'feed_url': main.extra.get('feed_url'), 'halal': all(p.extra.get('halal') or p.is_vegetarian or p.is_vegan for p in parts),
               'components': [{'id': p.id, 'name': p.name, 'station': p.station, 'role': 'main' if p is main else 'side',
                               'calories': p.calories, 'protein_g': p.protein_g, 'status': p.nutrition_status} for p in parts]})


def compose(kept: list[Dish], meal: str, kcal_target: float, protein_target: float, goal: str = 'balanced') -> list[Dish]:
    """Plates for every hall that has at least one eligible main."""
    from trojanbites_extract.flow.engine import GAIN, LOSE  # local import avoids a cycle

    by_venue: dict[str, list[Dish]] = {}
    for d in kept:
        if d.source_kind == 'usc_feed' and d.category != 'plate':
            by_venue.setdefault(d.venue_id, []).append(d)
    plates: list[Dish] = []
    over_weight = 1.6 if goal in LOSE else 1.0
    under_weight = 1.6 if goal in GAIN else 0.8

    def fit(cal: float | None, protein: float | None) -> float:
        cal_part = 0.3 if cal is None else max(0.0, 1 - ((cal / kcal_target - 1) * over_weight if cal > kcal_target else (1 - cal / kcal_target) * under_weight))
        prot_part = 0.3 if protein is None else min(1.0, protein / protein_target)
        return cal_part + 0.6 * prot_part

    for dishes in by_venue.values():
        mains = [d for d in dishes if role(d.name) == 'main' and not is_dessert_station(d.station)]
        side_pool = [d for d in dishes if role(d.name) in ('side', 'topper') and not is_dessert_station(d.station)]
        used: dict[str, int] = {}
        for main in sorted(mains, key=lambda m: (-(m.protein_g or 0), m.name))[:24]:
            ok = allowed_classes(main.name)
            cands = [d for d in side_pool if side_class(d.name) in ok]
            if is_meatless_main(main):
                cands = [d for d in cands if side_class(d.name) != 'topper']
            else:
                cands = [d for d in cands if side_class(d.name) != 'dip']
            cands = sorted(cands, key=lambda s: (-(s.protein_g or 0), (s.calories or 999), s.name))[:14]
            best, best_fit = [], -1.0
            for n in (0, 1, 2):
                for combo in itertools.combinations(cands, n):
                    classes = [side_class(c.name) for c in combo]
                    if len(set(classes)) != len(classes):
                        continue
                    cal = _sum([main, *combo], 'calories')
                    protein = _sum([main, *combo], 'protein_g')
                    value = fit(cal, protein) - 0.04 * n - 0.05 * sum(used.get(c.id, 0) for c in combo)
                    if value > best_fit:
                        best, best_fit = list(combo), value
            for c in best:
                used[c.id] = used.get(c.id, 0) + 1
            plate = make_plate(main, best, meal)
            if plate.calories is not None and plate.calories < 0.45 * kcal_target and len(best) < 2:
                continue  # a lone small item is a snack, not a swipe's worth of food
            plates.append(plate)
    return plates


def is_meatless_main(d: Dish) -> bool:
    return d.is_vegetarian or bool(re.search(r'\b(tofu|tempeh|seitan|beans?|lentils?|chickpeas?|falafel|veggie|vegetable|boca)\b', d.name, re.I))
