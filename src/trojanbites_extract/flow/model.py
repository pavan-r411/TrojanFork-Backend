"""Normalised venue/dish records plus the allergy and diet rules used by every filter.

Safety rules are fail-closed: a published allergen (or a 'verify' note about one) hides the dish,
and unknown evidence never counts as proof that a dish is safe.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

CANONICAL_ALLERGENS = ('dairy', 'eggs', 'fish', 'shellfish', 'soy', 'gluten', 'sesame', 'peanuts', 'tree-nuts', 'pork')

_SHELLFISH = re.compile(r'shellfish|shrimp|prawn|crab|lobster|mollusk|mollusc|clam|oyster|scallop|mussel|crustacean|squid|octopus', re.I)
_FISH = re.compile(r'fish|anchov|salmon|tuna|tilapia|cod\b|halibut|mahi|sardine|bonito|dashi', re.I)
_TREE_NUT = re.compile(r'tree[ _-]?nut|almond|walnut|cashew|pecan|pistachio|hazelnut|macadamia|pine nut|coconut|pesto', re.I)


def canonical_allergen_tags(entries) -> tuple[frozenset[str], frozenset[str]]:
    """Map the dataset's free-text allergen strings to canonical tags.

    Returns (canonical tags, other raw entries we could not map, lowercased) so an unmapped
    user allergy (for example mustard) can still be matched against them.
    """
    tags: set[str] = set()
    other: set[str] = set()
    for raw in entries or []:
        text = str(raw).lower().strip()
        if not text or text in {'none', 'none obvious'}:
            continue
        found = False
        gluten_free_phrase = bool(re.search(r'gluten[ -]?free', text))
        if not gluten_free_phrase and re.search(r'wheat|gluten|barley|\brye\b|flour|bread|batter|tortilla strips', text):
            tags.add('gluten'); found = True
        if re.search(r'milk|dairy|cheese|lactose|cream|yogurt|whey|casein|butter(?!\s*(?:nut|bean))', text):
            tags.add('dairy'); found = True
        if re.search(r'\begg', text):
            tags.add('eggs'); found = True
        if re.search(r'\bsoy|soya|tofu|edamame', text):
            tags.add('soy'); found = True
        if _SHELLFISH.search(text):
            tags.add('shellfish'); found = True
        if _FISH.search(_SHELLFISH.sub(' ', text)):
            tags.add('fish'); found = True
        if re.search(r'sesame|tahini', text):
            tags.add('sesame'); found = True
        if re.search(r'peanut|groundnut', text):
            tags.add('peanuts'); found = True
        if _TREE_NUT.search(text):
            tags.add('tree-nuts'); found = True
        if re.search(r'\bpork\b|bacon|\bham\b|prosciutto|chorizo|lard', text):
            tags.add('pork'); found = True
        if not found and not gluten_free_phrase:
            other.add(text)
    return frozenset(tags), frozenset(other)


MEAT = re.compile(
    r"\b(chicken|beef|pork|bacon|ham|turkey|lamb|steak|brisket|sausage|pepperoni|salami|prosciutto|meatballs?|carnitas|carne|"
    r"asada|al pastor|barbacoa|chorizo|duck|veal|bison|anchov\w*|tuna|salmon|shrimp|prawns?|crab|lobster|fish|tilapia|"
    r"cod|halibut|mahi|calamari|squid|octopus|oysters?|clams?|mussels?|scallops?|gelatin|lard|jerky|hot dogs?|gyro|shawarma|"
    r"kebab|spam|bulgogi|kalbi|katsu|pastrami|bologna|pulled pork|ribs?|rib-eye|ribeye|tenderloin|filet|fillet|patty melt)\b", re.I)
ANIMAL_NON_MEAT = re.compile(r"\b(honey|egg|eggs|milk|cheese|butter|cream|yogurt|whey|casein|ghee|paneer|mayo|mayonnaise|aioli|custard)\b", re.I)
NON_MEAL_CATEGORIES = {
    'beverage', 'beverages', 'drink', 'side', 'sides', 'dessert', 'desserts', 'cookie', 'donut', 'cronut', 'ice cream creation',
    'ice_cream', 'dessert toast', 'kids meal', 'appetizer', 'appetizers', 'bread', 'condiment', 'sauce', 'topping', 'pastry',
}
DRINK_NAME = re.compile(r'\b(coffee|latte|espresso|cappuccino|macchiato|mocha|tea|chai|matcha|boba|lemonade|juice|soda|cola|water|'
                        r'cold brew|frappe|smoothie|shake|milkshake|refresher|kombucha|cider)\b', re.I)


@dataclass(frozen=True)
class Venue:
    id: str
    name: str
    kind: str                      # hall | retail | restaurant
    category: str                  # usc_dining | off_campus
    cuisines: tuple[str, ...]
    lat: float | None
    lng: float | None
    address: str | None
    price_level: str | None
    weekly_hours: dict
    eligible: bool
    status: str
    hall_key: str | None = None
    website: str | None = None
    source_url: str | None = None
    phone: str | None = None


@dataclass
class Dish:
    id: str
    venue_id: str
    name: str
    category: str
    meal_times: frozenset[str]
    description: str
    price_usd: float | None
    price_kind: str                # cash | swipe
    calories: float | None
    protein_g: float | None
    carbs_g: float | None
    fat_g: float | None
    nutrition_status: str          # verified_published | chain_pattern_estimate | estimated | name_estimate
    nutrition_confidence: float
    allergens: frozenset[str]
    allergen_other: frozenset[str]
    allergen_raw: tuple[str, ...]
    allergen_status: str           # published | estimated | not_analyzed
    is_vegetarian: bool
    is_vegan: bool
    ingredients_text: str
    goal_tags: tuple[str, ...] = ()
    image_url: str | None = None
    source_kind: str = 'dataset'   # dataset | usc_feed
    source_label: str = 'Saved menu'
    source_date: str | None = None
    station: str | None = None
    availability_note: str | None = None
    extra: dict = field(default_factory=dict)

    def text_blob(self) -> str:
        return f'{self.name} {self.description} {self.ingredients_text}'.lower()
