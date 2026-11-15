"""Name-based nutrition estimates for dishes whose source publishes no nutrition (USC's daily feed).

These are rough typical-serving figures, always labelled as estimates with low confidence. They exist so
a calorie target can still shape the ranking; they are never presented as published facts.
"""
from __future__ import annotations

import re

# (pattern, kcal, protein g, carbs g, fat g). First match wins, so specific dishes come before generic words.
_RULES: tuple[tuple[re.Pattern, tuple[int, int, int, int]], ...] = tuple((re.compile(p, re.I), v) for p, v in (
    (r'omelet|omelette|frittata|quiche|scrambled|egg white|egg bites|breakfast burrito|breakfast sandwich', (400, 25, 14, 27)),
    (r'^(?:crispy |thick cut |smoked |turkey |applewood )*bacon\b(?!.*(?:burger|sandwich))|bacon strips|canadian bacon', (130, 9, 0, 10)),
    (r'^(?:breakfast |pork |chicken |turkey |maple )*sausage(?: links| patty| patties)?$|sausage links|breakfast sausage', (220, 11, 2, 19)),
    (r'^(?:honey |glazed |baked )*ham$|deli ham|salami|pepperoni|prosciutto|chorizo$', (160, 12, 2, 11)),
    (r'hot ?dogs?|corn ?dogs?|bratwurst|brats?\b', (330, 13, 28, 20)),
    (r'oatmeal|porridge|granola|cereal|overnight oats', (310, 9, 54, 6)),
    (r'pancake|waffle|french toast|crepe|crêpe', (480, 10, 72, 16)),
    (r'bagel|toast|croissant|muffin|pastry|danish|biscuit|scone', (360, 9, 52, 13)),
    (r'yogurt|parfait|cottage cheese', (210, 14, 26, 5)),
    (r'cookie|brownie|cake|(?<!shepherds )(?<!shepherd.s )(?<!pot )(?<!meat )(?<!cottage )pie\b|ice cream|dessert|pudding|donut|cobbler|cupcake|cheesecake|churro', (330, 4, 48, 14)),
    (r'\b(?:fruits?|melon|berries|apples?|bananas?|oranges?|grapes)\b', (95, 1, 23, 0)),
    (r'burger|cheeseburger', (640, 33, 42, 35)),
    (r'pizza|calzone|flatbread', (570, 25, 66, 23)),
    (r'lasagna|mac(?:aroni)? and cheese|mac & cheese|baked ziti', (640, 27, 68, 27)),
    (r'pasta|spaghetti|penne|rigatoni|fettuccine|linguine|gnocchi|noodle|ramen|pho\b|udon|lo mein|pad thai', (620, 24, 84, 20)),
    (r'taco|burrito|quesadilla|enchilada|fajita|nachos?|tostada|mulita|torta', (590, 29, 58, 25)),
    (r'sandwich|wrap|panini|sub\b|hoagie|gyro|banh mi|po.?boy|reuben', (540, 28, 52, 23)),
    (r'soup|chowder|bisque|stew|chili|dal\b|lentil', (250, 13, 30, 9)),
    (r'salmon|tilapia|cod\b|halibut|mahi|fish|shrimp|tuna|seafood|poke|scallop|crab', (390, 34, 14, 19)),
    (r'chicken|turkey|poultry', (440, 42, 16, 23)),
    (r'beef|steak|pot roast|brisket|meatball|pork|ham\b|carnitas|sausage|bacon|lamb|ribs?', (540, 38, 18, 33)),
    (r'tofu|tempeh|seitan|jackfruit|falafel|chickpea|bean|veggie|vegetable|cauliflower|eggplant|mushroom', (370, 19, 46, 13)),
    (r'curry|stir.?fry|teriyaki|fried rice|bowl|biryani', (540, 26, 68, 17)),
    (r'salad|slaw|greens', (270, 10, 20, 17)),
    (r'rice|potato|fries|quinoa|couscous|grain|corn|bread|roll\b|pilaf|polenta', (230, 5, 42, 4)),
))


_SIDE_RULES: tuple[tuple[re.Pattern, tuple[int, int, int, int]], ...] = tuple((re.compile(p, re.I), v) for p, v in (
    (r'bacon|sausage|ham\b|salami|pepperoni|prosciutto|chorizo', (140, 9, 1, 11)),
    (r'yogurt|parfait', (150, 9, 20, 3)),
    (r'fruit|melon|berries|apple|banana|orange|grapes|pineapple|mango|papaya', (80, 1, 20, 0)),
    (r'rice|grain|quinoa|couscous|pilaf|polenta|barley|farro|noodles?|pasta', (210, 5, 42, 3)),
    (r'potato|fries|plantain|corn|mashed|yam|tots?|hash brown', (190, 3, 36, 5)),
    (r'beans?|lentils?|chickpeas?|hummus|dal\b', (180, 10, 30, 2)),
    (r'bread|roll|biscuit|cornbread|toast|bagel|muffin|naan|pita|tortilla', (170, 5, 30, 3)),
    (r'salad|slaw|greens|coleslaw', (120, 4, 10, 8)),
    (r'soup|broth|bisque', (180, 8, 22, 7)),
    (r'squash|broccoli|carrot|spinach|kale|green beans|asparagus|zucchini|cabbage|peppers?|vegetables?|brussels|cauliflower|beets?|mushrooms?|eggplant|onions?|tomato|chard|bok choy|medley', (80, 3, 14, 3)),
))


def guess(name: str, station: str | None = None, role: str = 'main') -> dict | None:
    """Typical-serving {calories, protein_g, carbs_g, fat_g} from the dish name, with a generic fallback by role."""
    rules = _SIDE_RULES if role == 'side' else _RULES
    for pattern, (kcal, protein, carbs, fat) in rules:
        if pattern.search(name):
            return {'calories': float(kcal), 'protein_g': float(protein), 'carbs_g': float(carbs), 'fat_g': float(fat)}
    kcal, protein, carbs, fat = (140, 4, 22, 4) if role == 'side' else (450, 24, 40, 20)
    return {'calories': float(kcal), 'protein_g': float(protein), 'carbs_g': float(carbs), 'fat_g': float(fat)}


def tokens(text: str) -> set[str]:
    return {t for t in re.findall(r'[a-z]{3,}', text.lower()) if t not in {'with', 'and', 'the', 'served', 'fresh', 'house'}}


def similar(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)
