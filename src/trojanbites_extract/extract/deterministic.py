from __future__ import annotations

import re
from typing import Any

from trojanbites_extract.ids import new_id
from trojanbites_extract.parse.html import EvidenceDoc

# Name ... $12.50 ...optional rest of line (macros, claims)
PRICE_RE = re.compile(
    r"(?P<name>[A-Za-z][^\$\n]{1,80}?)\s+\$?(?P<price>\d+(?:\.\d{1,2})?)\b(?P<rest>.*)$"
)

CAL_RE = re.compile(r"(?P<cal>\d+)\s*(?:cal|kcal)\b", re.I)
PROTEIN_RE = re.compile(r"protein[:\s]*(?P<v>\d+(?:\.\d+)?)\s*g", re.I)
CARBS_RE = re.compile(r"carb(?:ohydrate)?s?[:\s]*(?P<v>\d+(?:\.\d+)?)\s*g", re.I)
FAT_RE = re.compile(r"\bfat[:\s]*(?P<v>\d+(?:\.\d+)?)\s*g", re.I)
FIBER_RE = re.compile(r"fiber[:\s]*(?P<v>\d+(?:\.\d+)?)\s*g", re.I)
SUGAR_RE = re.compile(r"sugar[:\s]*(?P<v>\d+(?:\.\d+)?)\s*g", re.I)
SODIUM_RE = re.compile(r"sodium[:\s]*(?P<v>\d+(?:\.\d+)?)\s*mg", re.I)
VEG_RE = re.compile(r"\b(vegetarian|vegan|halal|gluten-?free)\b", re.I)


def deterministic_extract(doc: EvidenceDoc, restaurant_id: str) -> dict[str, Any]:
    """Best-effort line parser for simple menus. Prefer Claude for messy layouts."""
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    lines: list[tuple[str, str]] = []
    for block in doc.blocks:
        for line in block.text.splitlines() or [block.text]:
            lines.append((line.strip(), block.block_id))

    for line, block_id in lines:
        if not line or len(line) > 300:
            continue
        m = PRICE_RE.search(line)
        if not m:
            continue
        name = m.group("name").strip(" -–—\t•|")
        # Drop leading list artifacts
        name = re.sub(r"^(li|p|h\d)\s+", "", name, flags=re.I).strip()
        if len(name) < 2 or name.lower() in {"menu", "lunch menu", "dinner menu"}:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)

        price = float(m.group("price"))
        rest = m.group("rest") or ""
        item_id = new_id("item")
        variant_id = new_id("var")

        published = {
            "calories_kcal": _num(_search(CAL_RE, rest, line)),
            "protein_g": _num(_search(PROTEIN_RE, rest, line)),
            "carbohydrates_g": _num(_search(CARBS_RE, rest, line)),
            "fat_g": _num(_search(FAT_RE, rest, line)),
            "fiber_g": _num(_search(FIBER_RE, rest, line)),
            "sugar_g": _num(_search(SUGAR_RE, rest, line)),
            "sodium_mg": _num(_search(SODIUM_RE, rest, line)),
        }
        has_macro = any(v is not None for v in published.values())
        nutrition = None
        if has_macro:
            nutrition = {
                "nutrition_id": new_id("nut"),
                "item_id": item_id,
                "variant_id": variant_id,
                "evidence_status": "restaurant_published",
                "serving_basis": None,
                "published": published,
                "estimated": None,
            }

        claims = []
        for cm in VEG_RE.finditer(line):
            claims.append(
                {
                    "claim": cm.group(1).lower().replace("glutenfree", "gluten-free"),
                    "raw_text": cm.group(0),
                    "evidence_status": "restaurant_published",
                    "is_guarantee": False,
                }
            )

        items.append(
            {
                "item_id": item_id,
                "restaurant_id": restaurant_id,
                "name": name,
                "raw_name": name,
                "description": None,
                "category": None,
                "menu_section": None,
                "variants": [
                    {
                        "variant_id": variant_id,
                        "size_label": None,
                        "serving_label": None,
                        "price": {"amount": price, "currency": "USD"},
                        "addons": [],
                    }
                ],
                "ingredients_published": None,
                "dietary_claims": claims,
                "allergen_claims": [],
                "availability": {
                    "status": "available",
                    "meal_periods": ["lunch"],
                    "days": None,
                },
                "nutrition": nutrition,
                "ambiguities": [],
                "field_sources": {
                    "price": {
                        "source_url": doc.source_url,
                        "locator": block_id,
                        "raw_text": line,
                    }
                },
            }
        )
    return {"menu_items": items, "conflicts": [], "ambiguities": []}


def _search(pattern: re.Pattern[str], *texts: str) -> str | None:
    for text in texts:
        m = pattern.search(text)
        if m:
            return m.groupdict().get("v") or m.groupdict().get("cal")
    return None


def _num(v: str | None) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except ValueError:
        return None
