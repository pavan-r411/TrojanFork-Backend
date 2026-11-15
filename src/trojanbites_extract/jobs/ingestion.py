from __future__ import annotations

import hashlib
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from trojanbites_extract.campus.registry import CampusConfig, load_campus
from trojanbites_extract.campus.resolve import point_in_campus_area
from trojanbites_extract.extract.deterministic import deterministic_extract
from trojanbites_extract.ids import new_id
from trojanbites_extract.parse.html import parse_html_file
from trojanbites_extract.retrieve.fetcher import SafeFetcher
from trojanbites_extract.settings import ROOT, get_settings
from trojanbites_extract.store.db import init_db, session_scope
from trojanbites_extract.store.models import IngestionJob, Restaurant
from trojanbites_extract.store.upserts import (
    replace_menu_for_restaurant,
    upsert_restaurant,
    upsert_source,
)
from trojanbites_extract.validate.rules import validate_extraction

logger = logging.getLogger(__name__)

# In-process worker for tonight's pilot (no Redis required)
_lock = threading.Lock()
_workers: dict[str, threading.Thread] = {}


def _idempotency_key(campus_id: str, job_type: str) -> str:
    day = datetime.utcnow().strftime("%Y-%m-%d")
    return f"{job_type}:{campus_id}:{day}"


def create_ingestion_job(
    campus_id: str,
    *,
    job_type: str = "campus_slice",
    run_async: bool = True,
) -> dict[str, Any]:
    """Queue (or return existing) campus ingestion job. Idempotent per campus/day."""
    init_db()
    load_campus(campus_id)  # validate
    key = _idempotency_key(campus_id, job_type)

    with session_scope() as session:
        existing = (
            session.query(IngestionJob)
            .filter(IngestionJob.idempotency_key == key)
            .one_or_none()
        )
        if existing and existing.status in {"queued", "running", "completed", "partial"}:
            job_id = existing.job_id
            status = existing.status
        else:
            job_id = new_id("job")
            job = IngestionJob(
                job_id=job_id,
                campus_id=campus_id,
                job_type=job_type,
                status="queued",
                progress_json={"stage": "queued", "percent": 0},
                errors_json=[],
                result_json={},
                idempotency_key=key,
                created_at=datetime.utcnow(),
            )
            session.add(job)
            status = "queued"

    if status == "queued" and run_async:
        _start_worker(job_id)
    elif status == "queued" and not run_async:
        run_ingestion_job(job_id)

    return get_job(job_id) or {"job_id": job_id, "status": status}


def _start_worker(job_id: str) -> None:
    with _lock:
        t = _workers.get(job_id)
        if t and t.is_alive():
            return
        thread = threading.Thread(
            target=run_ingestion_job, args=(job_id,), daemon=True, name=f"ingest-{job_id}"
        )
        _workers[job_id] = thread
        thread.start()


def get_job(job_id: str) -> dict[str, Any] | None:
    init_db()
    with session_scope() as session:
        job = session.get(IngestionJob, job_id)
        if not job:
            return None
        return {
            "job_id": job.job_id,
            "campus_id": job.campus_id,
            "job_type": job.job_type,
            "status": job.status,
            "progress": job.progress_json,
            "errors": job.errors_json,
            "result": job.result_json,
            "idempotency_key": job.idempotency_key,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        }


def run_ingestion_job(job_id: str) -> dict[str, Any]:
    """Execute campus vertical slice: seeds → fetch/parse → extract → store."""
    init_db()
    with session_scope() as session:
        job = session.get(IngestionJob, job_id)
        if not job:
            return {"error": "job_not_found"}
        if job.status == "completed":
            return get_job(job_id) or {}
        job.status = "running"
        job.started_at = datetime.utcnow()
        job.progress_json = {"stage": "running", "percent": 5}
        campus_id = job.campus_id

    errors: list[str] = []
    stored_restaurants = 0
    stored_items = 0
    try:
        campus = load_campus(campus_id)
        _set_progress(job_id, "loading_seeds", 15)
        for seed in campus.seeds:
            try:
                n_items = _ingest_seed(campus, seed)
                stored_restaurants += 1
                stored_items += n_items
            except Exception as exc:  # noqa: BLE001
                logger.exception("Seed ingest failed")
                errors.append(f"{seed.get('name')}: {exc}")

        # Optional Places discovery if key present
        places_added = 0
        settings = get_settings()
        if settings.google_maps_api_key:
            _set_progress(job_id, "places_discovery", 55)
            try:
                places_added = _discover_places_limited(campus, limit=5)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"places_discovery: {exc}")
        else:
            errors.append("places_discovery_blocked: GOOGLE_MAPS_API_KEY missing")

        _set_progress(job_id, "finalizing", 90)
        status = "completed" if not errors else "partial"
        with session_scope() as session:
            job = session.get(IngestionJob, job_id)
            assert job
            job.status = status
            job.errors_json = errors
            job.result_json = {
                "restaurants_upserted": stored_restaurants,
                "menu_items_upserted": stored_items,
                "places_shells_added": places_added,
                "claude_used": False,
                "nutrition_estimation": False,
                "notes": (
                    "Pilot slice uses deterministic extraction for fixtures/HTML; "
                    "Claude live extraction blocked without ANTHROPIC_API_KEY."
                ),
            }
            job.progress_json = {"stage": status, "percent": 100}
            job.finished_at = datetime.utcnow()
        return get_job(job_id) or {}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Job failed")
        with session_scope() as session:
            job = session.get(IngestionJob, job_id)
            if job:
                job.status = "failed"
                job.errors_json = errors + [str(exc)]
                job.progress_json = {"stage": "failed", "percent": 100}
                job.finished_at = datetime.utcnow()
        return get_job(job_id) or {"status": "failed", "error": str(exc)}


def _set_progress(job_id: str, stage: str, percent: int) -> None:
    with session_scope() as session:
        job = session.get(IngestionJob, job_id)
        if job:
            job.progress_json = {"stage": stage, "percent": percent}
            job.status = "running"


def _stable_seed_id(campus_id: str, seed: dict[str, Any]) -> str:
    raw = f"{campus_id}|{seed.get('name')}|{seed.get('branch_name')}|{seed.get('address')}"
    return f"rest_{campus_id}_{hashlib.sha1(raw.encode()).hexdigest()[:10]}"


def _ingest_seed(campus: CampusConfig, seed: dict[str, Any]) -> int:
    rid = _stable_seed_id(campus.campus_id, seed)
    lat, lng = seed.get("lat"), seed.get("lng")
    status, near_edge = ("unknown", False)
    if lat is not None and lng is not None:
        status, near_edge = point_in_campus_area(float(lat), float(lng), campus)

    menu_urls = list(seed.get("menu_urls") or [])
    fixture_rel = seed.get("fixture_menu_path")
    extraction: dict[str, Any] = {"menu_items": [], "conflicts": [], "ambiguities": []}

    with session_scope() as session:
        upsert_restaurant(
            session,
            {
                "restaurant_id": rid,
                "campus_id": campus.campus_id,
                "university_id": campus.university_id,
                "name": seed["name"],
                "branch_name": seed.get("branch_name"),
                "address": {"formatted": seed.get("address"), "source": "campus_seed"},
                "lat": lat,
                "lng": lng,
                "geocode_provider": "campus_seed",
                "boundary_status": status,
                "boundary_id": campus.boundary_id,
                "boundary_version": campus.boundary_version,
                "near_uncertain_edge": near_edge,
                "categories": seed.get("categories") or [],
                "cuisines": seed.get("cuisines") or [],
                "website": seed.get("website"),
                "menu_links": [
                    {"url": u, "label": None, "priority_tier": 1} for u in menu_urls
                ],
                "business_status": "operational",
                "service": {"is_campus_dining": "campus" in (seed.get("categories") or [])},
            },
        )
        for url in menu_urls:
            upsert_source(
                session,
                {
                    "source_id": f"src_{rid}_{hashlib.sha1(url.encode()).hexdigest()[:8]}",
                    "restaurant_id": rid,
                    "url": url,
                    "publisher": seed["name"],
                    "source_type": seed.get("source_type") or "other_permitted",
                    "priority_tier": 1,
                },
            )

    # Fixture menu path (second university / offline)
    if fixture_rel:
        path = ROOT / fixture_rel
        if path.exists():
            doc = parse_html_file(path, f"file://{path}", "fixture")
            extraction = deterministic_extract(doc, rid)
            report = validate_extraction(
                extraction, boundary_status=status, restaurant_id=rid
            )
            if report.hard_fail:
                raise RuntimeError(f"validation_failed:{report.reason_codes}")
            with session_scope() as session:
                upsert_source(
                    session,
                    {
                        "source_id": f"src_{rid}_fixture",
                        "restaurant_id": rid,
                        "url": str(path),
                        "publisher": "fixture",
                        "source_type": "fixture",
                        "priority_tier": 3,
                        "limitations": "Test fixture — not live university data",
                    },
                )
                replace_menu_for_restaurant(session, rid, extraction)
            return len(extraction.get("menu_items") or [])

    # Live fetch first permitted menu URL (best-effort)
    if menu_urls:
        fetcher = SafeFetcher()
        art = fetcher.fetch(menu_urls[0])
        if art.ok and art.bytes_path:
            ctype = (art.content_type or "").lower()
            path = Path(art.bytes_path)
            if "pdf" in ctype:
                from trojanbites_extract.parse.pdf import parse_pdf_file

                doc = parse_pdf_file(path, menu_urls[0], art.content_hash)
            else:
                doc = parse_html_file(path, menu_urls[0], art.content_hash)
            extraction = deterministic_extract(doc, rid)
            # Claude optional
            settings = get_settings()
            if settings.anthropic_api_key and not extraction.get("menu_items"):
                try:
                    from trojanbites_extract.extract.claude import ClaudeExtractor

                    extractor = ClaudeExtractor()
                    llm, _ = extractor.extract(
                        doc,
                        restaurant_id=rid,
                        restaurant_name=seed["name"],
                        branch_name=seed.get("branch_name"),
                        address_formatted=seed.get("address"),
                    )
                    extraction = llm
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Claude extract skipped: %s", exc)
            with session_scope() as session:
                if art.content_hash:
                    # update source hash
                    pass
                replace_menu_for_restaurant(session, rid, extraction)
            return len(extraction.get("menu_items") or [])

    return 0


def _discover_places_limited(campus: CampusConfig, limit: int = 5) -> int:
    from trojanbites_extract.discovery.base import Tile
    from trojanbites_extract.discovery.places import PlacesDiscoveryAdapter

    adapter = PlacesDiscoveryAdapter()
    tile = Tile(
        lat=campus.center_lat,
        lng=campus.center_lng,
        radius_m=campus.places_tile_radius_m,
    )
    candidates = adapter.discover([tile], campus.included_types, max_result_count=limit)
    added = 0
    with session_scope() as session:
        for cand in candidates[:limit]:
            rid = (
                f"rest_{campus.campus_id}_places_"
                f"{hashlib.sha1(cand.provider_place_id.encode()).hexdigest()[:10]}"
            )
            if session.get(Restaurant, rid):
                continue
            # Do NOT use Places lat/lng for PiP; leave coords null until independent geocode
            upsert_restaurant(
                session,
                {
                    "restaurant_id": rid,
                    "campus_id": campus.campus_id,
                    "university_id": campus.university_id,
                    "name": cand.display_name or "Unknown (Places)",
                    "branch_name": None,
                    "address": {
                        "places_runtime_hint": cand.formatted_address,
                        "note": "Independent address required before boundary membership",
                    },
                    "lat": None,
                    "lng": None,
                    "boundary_status": "unknown",
                    "boundary_id": campus.boundary_id,
                    "boundary_version": campus.boundary_version,
                    "categories": cand.raw_types,
                    "cuisines": [],
                    "website": cand.website_uri,
                    "menu_links": [],
                    "business_status": (cand.business_status or "unknown").lower(),
                },
            )
            added += 1
    return added


def tag_existing_pilot_as_usc() -> int:
    """Backfill campus_id on previously imported USC pilot restaurants."""
    init_db()
    n = 0
    with session_scope() as session:
        rows = session.query(Restaurant).all()
        for r in rows:
            if r.campus_id:
                continue
            # Heuristic: pilot ids tb-r-* and rest_seed_* / rest_demo belong to USC
            if (
                r.restaurant_id.startswith("tb-r-")
                or r.restaurant_id.startswith("rest_seed_")
                or r.restaurant_id.startswith("rest_demo_")
            ):
                r.campus_id = "usc_upc"
                r.university_id = "usc"
                n += 1
    return n
