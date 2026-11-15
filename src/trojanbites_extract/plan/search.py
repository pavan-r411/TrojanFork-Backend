from __future__ import annotations

from typing import Any, Literal

from trojanbites_extract.plan.menus import load_off_campus_menu, load_usc_dining_menu

SearchMode = Literal["usc_dining", "off_campus", "all", "hybrid"]


def _haystack(dish: dict[str, Any]) -> str:
    parts = [
        str(dish.get("name") or ""),
        str(dish.get("description") or ""),
        str(dish.get("venue_name") or ""),
        str(dish.get("venue_id") or ""),
        " ".join(str(x) for x in (dish.get("cuisines") or [])),
        " ".join(str(x) for x in (dish.get("dietary_labels") or [])),
        " ".join(str(x) for x in (dish.get("meal_periods") or [])),
    ]
    return " ".join(parts).lower()


def search_menus(
    q: str,
    mode: SearchMode = "all",
    limit: int = 20,
    menu_date: str | None = None,
) -> dict[str, Any]:
    query = (q or "").strip().lower()
    if not query:
        return {
            "query": q,
            "mode": mode,
            "count": 0,
            "results": [],
            "note": "Provide a non-empty q.",
        }

    dishes: list[tuple[str, dict[str, Any]]] = []
    if mode in {"usc_dining", "all", "hybrid"}:
        dining = load_usc_dining_menu(menu_date)
        for d in dining.get("dishes") or []:
            dishes.append(("usc_dining", d))
    if mode in {"off_campus", "all", "hybrid"}:
        off = load_off_campus_menu()
        for d in off.get("dishes") or []:
            dishes.append(("off_campus", d))

    hits: list[dict[str, Any]] = []
    for source, dish in dishes:
        if query not in _haystack(dish):
            continue
        hits.append(
            {
                "source": source,
                "dish_id": dish.get("dish_id"),
                "name": dish.get("name"),
                "venue_id": dish.get("venue_id"),
                "venue_name": dish.get("venue_name"),
                "meal_periods": dish.get("meal_periods") or [],
                "dietary_labels": dish.get("dietary_labels") or [],
                "cuisines": dish.get("cuisines") or [],
                "price_amount": dish.get("price_amount"),
                "payment_model": dish.get("payment_model"),
            }
        )
        if len(hits) >= limit:
            break

    return {
        "query": q,
        "mode": mode,
        "count": len(hits),
        "results": hits,
        "note": "Grounded snapshot matches only — no invented dishes.",
    }
