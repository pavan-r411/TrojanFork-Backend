#!/usr/bin/env python3
"""Load sample_menu.html through deterministic extract → DB → export (no API keys)."""

from __future__ import annotations

import json
from pathlib import Path

from trojanbites_extract.boundary.load import load_boundary
from trojanbites_extract.boundary.pip import point_in_polygon
from trojanbites_extract.export.json_export import build_canonical_snapshot, write_json_export
from trojanbites_extract.export.markdown_export import write_markdown_export
from trojanbites_extract.extract.deterministic import deterministic_extract
from trojanbites_extract.parse.html import parse_html_file
from trojanbites_extract.settings import ROOT, get_settings, load_extraction_config
from trojanbites_extract.store.db import init_db, session_scope
from trojanbites_extract.store.upserts import replace_menu_for_restaurant, upsert_restaurant
from trojanbites_extract.validate.rules import validate_extraction


def main() -> None:
    init_db()
    cfg = load_extraction_config()
    boundary = load_boundary(cfg["boundary_id"], cfg["boundary_version"])
    fixture = ROOT / "tests" / "fixtures" / "sample_menu.html"
    rid = "rest_demo_example_bowl"
    lat, lng = 34.0224, -118.2851
    br = point_in_polygon(lat, lng, boundary)

    doc = parse_html_file(fixture, f"file://{fixture}", "fixture")
    extraction = deterministic_extract(doc, rid)
    # Enrich first matching tofu line nutrition from fixture text via Claude-less heuristic:
    # deterministic_extract already attempts macros from the same line.
    report = validate_extraction(extraction, boundary_status=br.status, restaurant_id=rid)
    assert not report.hard_fail, report

    with session_scope() as session:
        upsert_restaurant(
            session,
            {
                "restaurant_id": rid,
                "name": "Example Bowl Co.",
                "branch_name": "University Park",
                "address": {
                    "formatted": "123 Example Ave, Los Angeles, CA 90007",
                    "source": "fixture",
                },
                "lat": lat,
                "lng": lng,
                "geocode_provider": "fixture",
                "boundary_status": br.status,
                "boundary_id": br.boundary_id,
                "boundary_version": br.boundary_version,
                "near_uncertain_edge": br.near_uncertain_edge,
                "categories": ["quick_service"],
                "cuisines": ["american", "bowls"],
                "website": "https://example-bowl.example/",
                "menu_links": [
                    {
                        "url": str(fixture),
                        "label": "fixture",
                        "priority_tier": 3,
                    }
                ],
                "business_status": "operational",
            },
        )
        replace_menu_for_restaurant(session, rid, extraction)
        out = get_settings().exports_dir
        json_path = write_json_export(session, out / "usc_restaurants.json")
        snap = build_canonical_snapshot(session)
    write_markdown_export(snap, out / "usc_restaurants.md")
    print(json.dumps({"restaurant_id": rid, "items": len(extraction["menu_items"]), "json": str(json_path)}, indent=2))
    for item in snap["menu_items"]:
        if item["restaurant_id"] == rid:
            print(item["name"], item["variants"][0]["price"])
    for n in snap["nutrition"]:
        if n["item_id"].startswith("item_") or True:
            if any(i["item_id"] == n["item_id"] and i["restaurant_id"] == rid for i in snap["menu_items"]):
                print("nutrition", n["published"])


if __name__ == "__main__":
    main()