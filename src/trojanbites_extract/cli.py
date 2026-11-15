from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict

from pathlib import Path

from trojanbites_extract.export.json_export import build_canonical_snapshot, write_json_export
from trojanbites_extract.export.markdown_export import write_markdown_export
from trojanbites_extract.campus.resolve import resolve_campus
from trojanbites_extract.campus.registry import list_campuses
from trojanbites_extract.import_pilot import ensure_pilot_files_in_place, import_pilot_json
from trojanbites_extract.jobs.ingestion import create_ingestion_job, get_job, tag_existing_pilot_as_usc
from trojanbites_extract.pipeline import discover_places, ingest_seeds, run_restaurant
from trojanbites_extract.query.filters import MealQuery, filter_meals, nearby_restaurants
from trojanbites_extract.settings import get_settings
from trojanbites_extract.store.db import init_db, session_scope
from trojanbites_extract.store.models import Restaurant


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="trojanbites", description="Trojan Fork extraction CLI")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init-db", help="Create SQLite schema")
    p_seeds = sub.add_parser("ingest-seeds", help="Load curated USC dining / pilot seeds")
    p_seeds.add_argument("--geocode", action="store_true", help="Geocode seed addresses via Google")

    p_disc = sub.add_parser("discover-places", help="Places Nearby tiling (needs GOOGLE_MAPS_API_KEY)")

    p_run = sub.add_parser("run", help="Fetch+extract one restaurant")
    p_run.add_argument("restaurant_id")
    p_run.add_argument("--no-claude", action="store_true")
    p_run.add_argument("--force", action="store_true")

    p_run_all = sub.add_parser("run-seeds", help="Extract all seed restaurants")
    p_run_all.add_argument("--no-claude", action="store_true")
    p_run_all.add_argument("--force", action="store_true")

    p_export = sub.add_parser("export", help="Write usc_restaurants.json + .md")
    p_export.add_argument("--out-dir", default=None)

    p_query = sub.add_parser("query", help="Deterministic meal filter")
    p_query.add_argument("--budget-max", type=float, default=None)
    p_query.add_argument("--diet", action="append", default=[])
    p_query.add_argument("--min-protein", type=float, default=None)
    p_query.add_argument("--meal-period", default=None)
    p_query.add_argument("--cuisine", action="append", default=None)
    p_query.add_argument("--strict", action="store_true", default=True)
    p_query.add_argument("--allow-uncertain", action="store_true")
    p_query.add_argument("--lat", type=float, default=None, help="User latitude (location on)")
    p_query.add_argument("--lng", type=float, default=None, help="User longitude (location on)")
    p_query.add_argument(
        "--max-miles",
        type=float,
        default=None,
        help="Max distance miles when lat/lng set (default 0.3)",
    )
    p_query.add_argument("--campus", default=None, help="campus_id filter")

    p_near = sub.add_parser(
        "nearby",
        help="List stored restaurants near user location (default 0.3 mi)",
    )
    p_near.add_argument("--lat", type=float, required=True)
    p_near.add_argument("--lng", type=float, required=True)
    p_near.add_argument("--max-miles", type=float, default=0.3)
    p_near.add_argument("--campus", default=None)

    p_resolve = sub.add_parser("resolve-campus", help="Resolve campus from lat/lng or campus id")
    p_resolve.add_argument("--lat", type=float, default=None)
    p_resolve.add_argument("--lng", type=float, default=None)
    p_resolve.add_argument("--campus", default=None)

    p_campuses = sub.add_parser("list-campuses", help="List configured campuses")

    p_ingest = sub.add_parser("ingest-campus", help="Run campus vertical-slice ingestion job")
    p_ingest.add_argument("campus_id")
    p_ingest.add_argument("--sync", action="store_true", help="Run synchronously")

    p_list = sub.add_parser("list-restaurants", help="List restaurants in DB")

    p_import = sub.add_parser(
        "import-pilot",
        help="Move Claude pilot JSON/MD into data/pilot and load into SQLite",
    )
    p_import.add_argument(
        "--json",
        default=None,
        help="Path to pilot JSON (default: ./usc_restaurants.json or data/pilot/...)",
    )
    p_import.add_argument(
        "--md",
        default=None,
        help="Path to pilot Markdown (default: ./usc_restaurants.md)",
    )
    p_import.add_argument(
        "--skip-move",
        action="store_true",
        help="Import from data/pilot without moving root files",
    )

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.cmd == "init-db":
        init_db()
        n = tag_existing_pilot_as_usc()
        print("DB ready:", get_settings().database_url, "backfilled_usc", n)
        return 0

    if args.cmd == "list-campuses":
        print(
            json.dumps(
                [
                    {
                        "campus_id": c.campus_id,
                        "university_id": c.university_id,
                        "display_name": c.display_name,
                        "boundary_type": c.boundary_type,
                        "boundary_official": c.boundary_official,
                    }
                    for c in list_campuses()
                ],
                indent=2,
            )
        )
        return 0

    if args.cmd == "resolve-campus":
        result = resolve_campus(lat=args.lat, lng=args.lng, campus_id=args.campus)
        print(
            json.dumps(
                {
                    "status": result.status,
                    "active_campus_id": result.active_campus_id,
                    "message": result.message,
                    "candidates": [asdict(c) for c in result.candidates],
                },
                indent=2,
            )
        )
        return 0

    if args.cmd == "ingest-campus":
        out = create_ingestion_job(args.campus_id, run_async=not args.sync)
        if args.sync:
            out = get_job(out["job_id"]) or out
        print(json.dumps(out, indent=2))
        return 0

    if args.cmd == "ingest-seeds":
        ids = ingest_seeds(geocode=args.geocode)
        print(json.dumps({"ingested": ids}, indent=2))
        return 0

    if args.cmd == "discover-places":
        n = discover_places()
        print(json.dumps({"new_shell_restaurants": n}))
        return 0

    if args.cmd == "run":
        result = run_restaurant(
            args.restaurant_id, use_claude=not args.no_claude, force=args.force
        )
        print(json.dumps(asdict(result), indent=2))
        return 0 if result.status in {"succeeded", "partial", "skipped"} else 1

    if args.cmd == "run-seeds":
        init_db()
        with session_scope() as session:
            ids = [
                r.restaurant_id
                for r in session.query(Restaurant).filter(
                    Restaurant.restaurant_id.like("rest_seed_%")
                )
            ]
        results = [
            asdict(run_restaurant(rid, use_claude=not args.no_claude, force=args.force))
            for rid in ids
        ]
        print(json.dumps(results, indent=2))
        return 0

    if args.cmd == "export":
        init_db()
        out_dir = get_settings().exports_dir if not args.out_dir else __import__("pathlib").Path(args.out_dir)
        with session_scope() as session:
            json_path = write_json_export(session, out_dir / "usc_restaurants.json")
            snap = build_canonical_snapshot(session)
        md_path = write_markdown_export(snap, out_dir / "usc_restaurants.md")
        print(json.dumps({"json": str(json_path), "md": str(md_path)}, indent=2))
        return 0

    if args.cmd == "query":
        init_db()
        q = MealQuery(
            campus_id=args.campus,
            budget_max=args.budget_max,
            diet_claims_required=args.diet or [],
            cuisine_any=args.cuisine,
            min_published_protein_g=args.min_protein,
            meal_period=args.meal_period,
            strict=not args.allow_uncertain,
            user_lat=args.lat,
            user_lng=args.lng,
            max_distance_miles=args.max_miles,
        )
        with session_scope() as session:
            hits = filter_meals(session, q)
        print(json.dumps([asdict(h) for h in hits], indent=2))
        return 0

    if args.cmd == "nearby":
        init_db()
        with session_scope() as session:
            rows = nearby_restaurants(
                session,
                user_lat=args.lat,
                user_lng=args.lng,
                max_distance_miles=args.max_miles,
                campus_id=args.campus,
            )
        print(json.dumps([asdict(r) for r in rows], indent=2))
        return 0

    if args.cmd == "list-restaurants":
        init_db()
        with session_scope() as session:
            rows = session.query(Restaurant).all()
            print(
                json.dumps(
                    [
                        {
                            "restaurant_id": r.restaurant_id,
                            "name": r.name,
                            "branch": r.branch_name,
                            "boundary": r.boundary_status,
                            "menu_links": r.menu_links_json,
                        }
                        for r in rows
                    ],
                    indent=2,
                )
            )
        return 0

    if args.cmd == "import-pilot":
        if args.skip_move:
            path = Path(args.json) if args.json else (get_settings().root / "data" / "pilot" / "usc_restaurants.json")
        else:
            json_src = Path(args.json) if args.json else None
            md_src = Path(args.md) if args.md else None
            path, md_path = ensure_pilot_files_in_place(json_src, md_src)
            print(json.dumps({"moved_json": str(path), "moved_md": str(md_path) if md_path else None}))
        counts = import_pilot_json(path)
        # refresh app exports from DB
        out_dir = get_settings().exports_dir
        with session_scope() as session:
            json_path = write_json_export(session, out_dir / "usc_restaurants.json")
            snap = build_canonical_snapshot(session)
        md_path = write_markdown_export(snap, out_dir / "usc_restaurants.md")
        print(json.dumps({"imported": counts, "exports": {"json": str(json_path), "md": str(md_path)}}, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())