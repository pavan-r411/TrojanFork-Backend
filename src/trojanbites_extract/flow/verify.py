"""Independent audit of recommendation output.

The engine filters with its own rules; this module re-checks the *result* with a separate, deliberately simple
keyword model so a bug in one cannot hide a bug in the other. It is used by the tests and by scripts/flow_accuracy.py.
"""
from __future__ import annotations

import re

_ALLERGY_WORDS = {
    'peanuts': r'peanuts?', 'tree nuts': r'almonds?|walnuts?|pecans?|cashews?|pistachios?|hazelnuts?|macadamia',
    'eggs': r'eggs?|omelet\w*|frittata|quiche|mayo(?:nnaise)?|aioli', 'soy': r'soy\w*|tofu|edamame|tempeh|miso',
    'fish': r'salmon|tuna|tilapia|cod|halibut|mahi|anchov\w*|sardines?|fish', 'shellfish': r'shrimp|crab|lobster|clams?|oysters?|mussels?|scallops?|prawns?',
    'sesame': r'sesame|tahini|hummus', 'dairy': r'milk|cheese|butter|cream|yogurt|ricotta|mozzarella|parmesan|cheddar|feta|queso|paneer',
    'gluten': r'wheat|flour tortillas?|seitan|couscous|farro|barley',
}
_DAIRY_FALSE = re.compile(r'coconut (?:milk|cream|yogurt)|peanut butter|almond (?:milk|butter)|oat milk|soy (?:milk|yogurt)|cashew (?:cheese|cream)|butternut|cocoa butter|cream of tartar|vegan (?:cheese|butter)', re.I)
_MEAT = re.compile(r'\b(chicken|beef|pork|bacon|ham|sausage|turkey|steak|lamb|brisket|meatballs?|salami|pepperoni|hot ?dogs?|pot roast|carnitas|ribs?|'
                   r'tuna|salmon|tilapia|cod|halibut|mahi|shrimp|crab|lobster|fish|anchov\w*)\b', re.I)
_PLANT_MEAT = re.compile(r'veggie|vegan|vegetable|plant|boca|impossible|beyond|jackfruit|tofu|tempeh|seitan|mushroom', re.I)
_ANIMAL = re.compile(r'\b(milk|cheese|butter|cream|yogurt|egg|eggs|honey|ricotta|mozzarella|parmesan|cheddar|feta|queso|paneer|omelet\w*|custard)\b', re.I)
_PLANT_DAIRY = re.compile(r'coconut|almond|oat|soy|vegan|cashew|plant|peanut butter', re.I)


def option_text(option: dict) -> str:
    comps = ' '.join(c.get('name', '') for c in (option.get('components') or []))
    return f"{option.get('name', '')} {option.get('subtitle') or ''} {comps} {option.get('description') or ''}".lower()


def _contains_meat(text: str) -> bool:
    for part in re.split(r'\bwith\b|\band\b|,|&', text):
        if _MEAT.search(part) and not _PLANT_MEAT.search(part):
            return True
    return False


def violations(q, option: dict) -> list[str]:
    """Human-readable problems with one returned option for one query. Empty list means it is acceptable."""
    problems: list[str] = []
    text = option_text(option)
    contains = {c.lower() for c in option['allergens']['contains']}
    for allergy in q.allergies:
        key = allergy.lower().strip()
        tag = {'peanut': 'peanuts', 'nuts': 'tree nuts', 'tree nut': 'tree nuts', 'egg': 'eggs', 'shellfish': 'shellfish', 'milk': 'dairy'}.get(key, key)
        if tag.replace(' ', '') in {re.sub(r'[^a-z]', '', c) for c in contains}:
            problems.append(f'published allergen {tag} present')
        pattern = _ALLERGY_WORDS.get(tag)
        if pattern:
            scan = _DAIRY_FALSE.sub(' ', text) if tag == 'dairy' else text
            if tag == 'soy':
                scan = re.sub(r'soy ?milk|soy yogurt', '', scan)
            if re.search(rf'\b({pattern})\b', scan):
                problems.append(f'name mentions {tag}')
        if option['allergens'].get('status') == 'not_analyzed':
            problems.append('allergen data missing but user has allergies')
    diet = (q.diet or 'any').lower()
    if diet in {'vegetarian', 'vegan'}:
        if not option['diet'].get(diet) and not option['diet'].get('vegan'):
            problems.append(f'not flagged {diet}')
        if _contains_meat(text):
            problems.append('meat in a vegetarian/vegan option')
    if diet == 'vegan':
        stripped = _PLANT_DAIRY.sub(' ', text)
        if _ANIMAL.search(stripped) and not option['diet'].get('vegan'):
            problems.append('animal product in a vegan option')
    if diet == 'halal' and not option['diet'].get('halal') and not option['diet'].get('vegetarian'):
        problems.append('not halal or vegetarian')
    price = option['price']
    if price.get('kind') == 'cash':
        dollars = (price.get('cash_cents') or 0) / 100
        if q.per_meal_usd is not None and dollars > q.per_meal_usd + 0.005:
            problems.append(f'${dollars:.2f} over per-meal budget')
        if q.daily_remaining_usd is not None and dollars > q.daily_remaining_usd + 0.005:
            problems.append(f'${dollars:.2f} over remaining daily budget')
    if q.mode == 'off_campus' and option['venue']['kind'] != 'hall':
        miles = option['walk']['miles']
        if miles is not None and miles > q.max_miles + 1e-6:
            problems.append(f'{miles} mi beyond {q.max_miles} mi')
    if q.mode == 'usc_dining' and option['price']['kind'] != 'swipe':
        problems.append('hall option priced in cash')
    if q.min_protein_g and (option['nutrition']['protein_g'] or 0) < q.min_protein_g:
        problems.append('below minimum protein')
    if q.max_kcal and (option['nutrition']['calories'] or 1e9) > q.max_kcal:
        problems.append('above calorie ceiling')
    return problems


def result_violations(q, result: dict) -> list[str]:
    problems: list[str] = []
    seen: set[str] = set()
    for page in result['pages']:
        if len(page) > 3:
            problems.append('page with more than 3 options')
        for index in page:
            if index in seen:
                problems.append('option repeated across pages')
            seen.add(index)
            if not 0 <= index < len(result['options']):
                problems.append('page points at a missing option')
    for option in result['options']:
        problems += [f"{option['name']}: {p}" for p in violations(q, option)]
    return problems
