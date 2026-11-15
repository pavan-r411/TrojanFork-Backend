"""Allergy, dislike and menu-noise helpers shared by the live USC and off-campus paths.

Dishes are only hidden when published evidence says so (USC allergen tags, or the
allergen named in the dish text). Everything else is labeled, never silently cleared.
"""
from __future__ import annotations

import re

# USC labels the FDA top nine allergens plus pork (legend on the residential menus page).
ALLERGEN_TERMS: dict[str, list[str]] = {
    'dairy': ['dairy', 'milk', 'lactose', 'cheese', 'butter', 'cream', 'yogurt', 'whey', 'casein'],
    'eggs': ['egg', 'eggs'],
    'fish': ['fish', 'salmon', 'tuna', 'tilapia', 'cod'],
    'shellfish': ['shellfish', 'shrimp', 'crab', 'lobster', 'prawn', 'prawns', 'crustacean', 'crustaceans',
                  'clam', 'clams', 'mussel', 'mussels', 'oyster', 'oysters', 'scallop', 'scallops'],
    'soy': ['soy', 'soya', 'soybean', 'soybeans', 'tofu', 'edamame'],
    'gluten': ['gluten', 'wheat', 'barley', 'rye'],
    'sesame': ['sesame', 'tahini'],
    'peanuts': ['peanut', 'peanuts', 'peanut butter', 'groundnut', 'groundnuts', 'nut', 'nuts'],
    'tree-nuts': ['tree nut', 'tree nuts', 'treenut', 'treenuts', 'nut', 'nuts', 'almond', 'almonds', 'walnut',
                  'walnuts', 'cashew', 'cashews', 'pecan', 'pecans', 'pistachio', 'pistachios', 'hazelnut',
                  'hazelnuts', 'macadamia'],
    'pork': ['pork', 'bacon', 'ham'],
}
ALLERGEN_LABELS = 'dairy, eggs, fish, shellfish, soy, wheat/gluten, sesame, peanuts, tree nuts and pork'
_FILLER = {'and', 'or', 'allergy', 'allergies', 'allergic', 'to', 'free', 'no', 'intolerance', 'intolerant',
           'products', 'product', 'all', 'any', 'the'}
_PHRASES = sorted({(term, key) for key, terms in ALLERGEN_TERMS.items() for term in terms}, key=lambda x: -len(x[0]))


def _clean(value) -> str:
    return ' '.join(re.sub(r'[^a-z ]', ' ', str(value).lower()).split())


def canonical_allergies(values) -> tuple[set[str], list[str]]:
    """Map free-text allergies to published allergen tags; return (tags, entries we cannot map)."""
    found, unknown = set(), []
    for value in values or []:
        text = _clean(value)
        if not text:
            continue
        matched, rest = set(), text
        for term, _ in _PHRASES:
            pattern = rf'\b{re.escape(term)}\b'
            if re.search(pattern, rest):
                matched |= {key for other, key in _PHRASES if other == term}
                rest = re.sub(pattern, ' ', rest)
        if not matched or any(word not in _FILLER for word in rest.split()):
            unknown.append(str(value).strip())
        else:
            found |= matched
    return found, unknown


def stems(values) -> list[str]:
    """Lower-cased stems for text matching ("mushrooms" also matches "Sliced Mushroom")."""
    out = []
    for value in values or []:
        text = _clean(value)
        if len(text) > 3 and text.endswith('s') and not text.endswith('ss'):
            text = text[:-1]
        if len(text) >= 3 and text not in out:
            out.append(text)
    return out


def allergy_text_terms(values, *, include_synonyms: bool) -> list[str]:
    """Words whose presence in a dish name/description is evidence of a listed allergen."""
    tags, unknown = canonical_allergies(values)
    terms = stems(unknown)
    if include_synonyms:
        for tag in tags:
            for term in ALLERGEN_TERMS[tag]:
                if term not in terms:
                    terms.append(term)
    return terms


def mentions(text: str, terms) -> bool:
    """Whole-word match (optional plural), so "ham" never matches "hamburger"."""
    text = _clean(text)
    return any(re.search(rf'\b{re.escape(term)}(?:s|es)?\b', text) for term in terms)


def feed_allergens(item: dict) -> set[str]:
    """Canonical allergen tags USC published for one feed item ('not-analyzed' when USC says so)."""
    tags = {re.sub(r'[^a-z]', '', str(tag).lower())
            for tag in list(item.get('allergens') or []) + list(item.get('dietary_preferences') or [])}
    out = set()
    for tag in tags:
        if 'notanalyzed' in tag:
            out.add('not-analyzed')
        if 'dairy' in tag or 'milk' in tag:
            out.add('dairy')
        if 'egg' in tag:
            out.add('eggs')
        if 'shellfish' in tag:
            out.add('shellfish')
        elif 'fish' in tag:
            out.add('fish')
        if 'soy' in tag:
            out.add('soy')
        if 'gluten' in tag or 'wheat' in tag:
            out.add('gluten')
        if 'sesame' in tag:
            out.add('sesame')
        if 'peanut' in tag:
            out.add('peanuts')
        elif 'nut' in tag:
            out.add('tree-nuts')
        if 'pork' in tag:
            out.add('pork')
    return out
