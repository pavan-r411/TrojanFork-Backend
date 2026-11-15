"""Resumable off-campus DPS restaurant discovery + menu ingestion.

Scope: businesses outside the UPC academic campus core but inside the DPS
patrol polygon. USC Village commercial is included. Campus hospitality dining
halls remain teammate-owned and are skipped.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from trojanbites_extract.boundary.load import load_boundary
from trojanbites_extract.campus.registry import CampusConfig, load_campus
from trojanbites_extract.campus.zones import classify_location, zone_service_payload
from trojanbites_extract.discovery.places import PlacesDiscoveryAdapter
from trojanbites_extract.discovery.tiles import cover_polygon_with_circles
from trojanbites_extract.extract.deterministic import deterministic_extract
from trojanbites_extract.extract.gemini import GeminiExtractor, GeminiMenuFinder, extract_links_from_html
from trojanbites_extract.extract.merge import merge_extractions
from trojanbites_extract.geocoding.adapter import GoogleGeocoder
from trojanbites_extract.ids import new_id
from trojanbites_extract.parse.dispatch import artifact_to_evidence
from trojanbites_extract.parse.html import parse_html_file
from trojanbites_extract.retrieve.fetcher import SafeFetcher
from trojanbites_extract.settings import get_settings
from trojanbites_extract.store.db import init_db, session_scope
from trojanbites_extract.store.models import IngestionJob, ProviderRef, Restaurant, Source
from trojanbites_extract.store.upserts import (
    replace_menu_for_restaurant,
    upsert_restaurant,
    upsert_source,
)
from trojanbites_extract.validate.rules import validate_extraction

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_workers: dict[str, threading.Thread] = {}


def _idempotency_key(campus_id: str, batch_limit: int) -> str:
    day = datetime.utcnow().strftime("%Y-%m-%d")
    return f"off_campus_dps:{campus_id}:{day}:limit{batch_limit}"


def create_off_campus_dps_job(
    campus_id: str = "usc_upc",
    *,
    batch_limit: int | None = None,
    run_async: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Queue or return today's off-campus DPS ingestion job."""
    init_db()
    campus = load_campus(campus_id)
    limit = int(
        batch_limit
        if batch_limit is not None
        else (campus.off_campus_discovery.get("batch_limit") or 5)
    )
    key = _idempotency_key(campus_id, limit)

    with session_scope() as session:
        existing = (
            session.query(IngestionJob)
            .filter(IngestionJob.idempotency_key == key)
            .one_or_none()
        )
        if existing and existing.status in {"queued", "running", "completed", "partial"} and not force:
            job_id = existing.job_id
            status = existing.status
        else:
            if existing and force:
                existing.idempotency_key = f"{key}:superseded:{existing.job_id}"
            job_id = new_id("job")
            session.add(
                IngestionJob(
                    job_id=job_id,
                    campus_id=campus_id,
                    job_type="off_campus_dps",
                    status="queued",
                    progress_json={"stage": "queued", "percent": 0, "batch_limit": limit},
                    errors_json=[],
                    result_json={},
                    idempotency_key=key if not force else f"{key}:{job_id}",
                    created_at=datetime.utcnow(),
                )
            )
            status = "queued"

    if status == "queued" and run_async:
        _start_worker(job_id)
    elif status == "queued" and not run_async:
        run_off_campus_dps_job(job_id)
    return get_off_campus_job(job_id) or {"job_id": job_id, "status": status}


def _start_worker(job_id: str) -> None:
    with _lock:
        t = _workers.get(job_id)
        if t and t.is_alive():
            return
        thread = threading.Thread(
            target=run_off_campus_dps_job,
            args=(job_id,),
            daemon=True,
            name=f"offcampus-{job_id}",
        )
        _workers[job_id] = thread
        thread.start()


def get_off_campus_job(job_id: str) -> dict[str, Any] | None:
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


def run_off_campus_dps_job(job_id: str) -> dict[str, Any]:
    init_db()
    with session_scope() as session:
        job = session.get(IngestionJob, job_id)
        if not job:
            return {"error": "job_not_found"}
        if job.status == "completed":
            return get_off_campus_job(job_id) or {}
        job.status = "running"
        job.started_at = datetime.utcnow()
        campus_id = job.campus_id
        batch_limit = int((job.progress_json or {}).get("batch_limit") or 5)

    errors: list[str] = []
    summary: dict[str, Any] = {
        "discovered_candidates": 0,
        "geocoded": 0,
        "off_campus_dps_matched": 0,
        "skipped_teammate_or_on_campus": 0,
        "skipped_outside_dps": 0,
        "skipped_duplicates": 0,
        "restaurants_upserted": 0,
        "menus_from_website": 0,
        "menus_from_pdf": 0,
        "menus_from_gemini_search": 0,
        "menus_missing": 0,
        "dishes_extracted": 0,
        "with_price": 0,
        "with_published_nutrition": 0,
        "access_blockers": [],
        "processed": [],
        "live_data": True,
        "fixtures_used": False,
    }

    try:
        campus = load_campus(campus_id)
        settings = get_settings()
        cfg = campus.off_campus_discovery or {}
        max_tiles = int(cfg.get("max_places_tiles") or 12)
        max_geocode = int(cfg.get("max_geocode_per_run") or 40)
        max_menu_urls = int(cfg.get("max_menu_urls_per_restaurant") or 3)

        if not settings.google_maps_api_key:
            errors.append("GOOGLE_MAPS_API_KEY missing — Places/Geocoding blocked")
            return _finish(job_id, "failed", errors, summary)

        _set_progress(job_id, "places_discovery", 10)
        candidates = _discover_candidates(campus, max_tiles=max_tiles)
        summary["discovered_candidates"] = len(candidates)

        _set_progress(job_id, "geocode_and_filter", 30)
        geocoder = GoogleGeocoder()
        matched: list[dict[str, Any]] = []
        geocode_count = 0

        for cand in candidates:
            if len(matched) >= batch_limit:
                break
            if geocode_count >= max_geocode:
                errors.append("geocode_budget_exhausted")
                break

            address = cand.formatted_address
            if not address:
                summary["access_blockers"].append(
                    {"name": cand.display_name, "reason": "missing_places_address_hint"}
                )
                continue

            # Dedup by Place ID first (unless re-enrich of incomplete menus)
            existing_rid = _place_id_restaurant(cand.provider_place_id)
            enriching = bool(existing_rid and _needs_menu_enrichment(existing_rid))
            if existing_rid and not enriching:
                summary["skipped_duplicates"] += 1
                continue

            try:
                geo = geocoder.geocode(address)
                geocode_count += 1
                summary["geocoded"] += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"geocode:{cand.display_name}:{exc}")
                continue
            if not geo:
                summary["access_blockers"].append(
                    {"name": cand.display_name, "reason": "geocode_failed", "address": address}
                )
                continue

            zone = classify_location(
                geo.lat,
                geo.lng,
                campus,
                name=cand.display_name,
                categories=list(cand.raw_types or []),
            )
            if zone.pipeline_owner == "on_campus_teammate":
                summary["skipped_teammate_or_on_campus"] += 1
                continue
            if zone.location_zone == "outside_dps":
                summary["skipped_outside_dps"] += 1
                continue
            if zone.pipeline_owner != "off_campus":
                continue

            # Name+address soft dedupe against existing off-campus / pilot rows
            if not enriching and _soft_duplicate(cand.display_name or "", address):
                summary["skipped_duplicates"] += 1
                continue

            matched.append(
                {
                    "candidate": cand,
                    "geo": geo,
                    "zone": zone,
                    "address": address,
                }
            )

        summary["off_campus_dps_matched"] = len(matched)
        _set_progress(job_id, "menu_ingest", 55)

        gemini_ok = bool(settings.gemini_api_key)
        if not gemini_ok:
            errors.append("GEMINI_API_KEY missing — menu search/extract limited to deterministic HTML")

        finder = GeminiMenuFinder() if gemini_ok else None
        extractor = GeminiExtractor() if gemini_ok else None
        fetcher = SafeFetcher()

        for i, row in enumerate(matched):
            pct = 55 + int(40 * (i + 1) / max(len(matched), 1))
            _set_progress(job_id, f"restaurant_{i+1}_of_{len(matched)}", pct)
            try:
                result = _ingest_one(
                    campus=campus,
                    cand=row["candidate"],
                    geo=row["geo"],
                    zone=row["zone"],
                    address=row["address"],
                    finder=finder,
                    extractor=extractor,
                    fetcher=fetcher,
                    max_menu_urls=max_menu_urls,
                )
                summary["restaurants_upserted"] += 1
                summary["dishes_extracted"] += result["dishes"]
                summary["with_price"] += result["with_price"]
                summary["with_published_nutrition"] += result["with_nutrition"]
                for key in ("menus_from_website", "menus_from_pdf", "menus_from_gemini_search", "menus_missing"):
                    summary[key] += result.get(key, 0)
                if result.get("blocker"):
                    summary["access_blockers"].append(result["blocker"])
                summary["processed"].append(result["report"])
            except Exception as exc:  # noqa: BLE001
                logger.exception("off-campus ingest failed")
                errors.append(f"{row['candidate'].display_name}: {exc}")

        status = "completed" if not errors else "partial"
        if summary["restaurants_upserted"] == 0 and errors:
            status = "failed"
        return _finish(job_id, status, errors, summary)
    except Exception as exc:  # noqa: BLE001
        logger.exception("off-campus DPS job failed")
        errors.append(str(exc))
        return _finish(job_id, "failed", errors, summary)


def _discover_candidates(campus: CampusConfig, *, max_tiles: int):
    patrol_id = campus.patrol_boundary_id or campus.boundary_id
    patrol_ver = campus.patrol_boundary_version or campus.boundary_version
    assert patrol_id and patrol_ver
    boundary = load_boundary(patrol_id, patrol_ver)
    tiles = cover_polygon_with_circles(boundary.geometry, campus.places_tile_radius_m)
    # Prefer tiles near campus center first (cheaper pilot)
    tiles = sorted(
        tiles,
        key=lambda t: (t.lat - campus.center_lat) ** 2 + (t.lng - campus.center_lng) ** 2,
    )[:max_tiles]
    adapter = PlacesDiscoveryAdapter()
    return adapter.discover(
        tiles,
        campus.included_types,
        max_result_count=20,
    )


def _place_id_restaurant(place_id: str) -> str | None:
    with session_scope() as session:
        pref = (
            session.query(ProviderRef)
            .filter_by(provider="google_places", place_id=place_id)
            .one_or_none()
        )
        return pref.restaurant_id if pref else None


def _needs_menu_enrichment(restaurant_id: str) -> bool:
    with session_scope() as session:
        rest = session.get(Restaurant, restaurant_id)
        if not rest:
            return True
        svc = rest.service_json or {}
        if svc.get("menu_status") in {None, "missing_or_inaccessible"}:
            return True
        from trojanbites_extract.store.models import MenuItem

        n = session.query(MenuItem).filter(MenuItem.restaurant_id == restaurant_id).count()
        return n == 0


def _soft_duplicate(name: str, address: str) -> bool:
    digest = hashlib.sha1(f"{name.strip().lower()}|{address.strip().lower()}".encode()).hexdigest()[:12]
    rid = f"rest_offcampus_{digest}"
    with session_scope() as session:
        if session.get(Restaurant, rid):
            return True
        # Also skip if an existing row has nearly the same name inside DPS exports
        needle = name.strip().lower()
        for row in session.query(Restaurant).all():
            if (row.name or "").strip().lower() != needle:
                continue
            svc = row.service_json or {}
            if svc.get("pipeline_owner") == "on_campus_teammate":
                return True
            if svc.get("location_zone") == "off_campus_dps":
                return True
            # Pilot rows with same name — treat as duplicate to preserve teammate/pilot work
            if row.restaurant_id.startswith("tb-r-") or row.restaurant_id.startswith("rest_seed_"):
                return True
    return False


def _stable_offcampus_id(place_id: str) -> str:
    return f"rest_offcampus_{hashlib.sha1(place_id.encode()).hexdigest()[:12]}"


def _ingest_one(
    *,
    campus: CampusConfig,
    cand,
    geo,
    zone,
    address: str,
    finder: GeminiMenuFinder | None,
    extractor: GeminiExtractor | None,
    fetcher: SafeFetcher,
    max_menu_urls: int,
) -> dict[str, Any]:
    rid = _stable_offcampus_id(cand.provider_place_id)
    attempts: list[str] = []
    menu_urls: list[dict[str, Any]] = []
    website = cand.website_uri
    menus_from_website = 0
    menus_from_pdf = 0
    menus_from_gemini_search = 0
    menus_missing = 0
    blocker = None

    # 1) Gemini grounded search for official menu links
    if finder is not None:
        found, meta = finder.find_menu_links(
            name=cand.display_name or "Unknown",
            address=address,
            website=website,
        )
        attempts.extend(found.get("attempts") or [])
        if meta.get("error"):
            attempts.append(f"gemini_search:{meta['error']}")
        if found.get("official_website"):
            website = found["official_website"]
        for row in found.get("menu_urls") or []:
            if isinstance(row, dict) and row.get("url"):
                menu_urls.append(
                    {
                        "url": row["url"],
                        "label": row.get("kind"),
                        "priority_tier": 2,
                        "via": "gemini_search",
                    }
                )
                menus_from_gemini_search = 1
        for url in found.get("nutrition_urls") or []:
            menu_urls.append({"url": url, "label": "nutrition", "priority_tier": 2, "via": "gemini_search"})
        for url in found.get("ordering_urls") or []:
            menu_urls.append({"url": url, "label": "ordering", "priority_tier": 3, "via": "gemini_search"})
    else:
        attempts.append("gemini_unavailable")

    # 2) Fetch official website and inspect nav/menu/PDF links
    if website:
        art = fetcher.fetch(website)
        if art.ok and art.bytes_path:
            attempts.append(f"fetched_website:{website}")
            ctype = (art.content_type or "").lower()
            if "html" in ctype or "text" in ctype:
                html = Path(art.bytes_path).read_text(encoding="utf-8", errors="replace")
                for link in extract_links_from_html(html, art.final_url or website):
                    menu_urls.append(
                        {
                            "url": link["url"],
                            "label": link.get("kind"),
                            "priority_tier": 1,
                            "via": "website_nav",
                        }
                    )
                    menus_from_website = 1
                    if link.get("kind") == "pdf_menu":
                        menus_from_pdf = 1
            elif "pdf" in ctype:
                menu_urls.insert(
                    0,
                    {"url": website, "label": "pdf_menu", "priority_tier": 1, "via": "website_pdf"},
                )
                menus_from_pdf = 1
                menus_from_website = 1
        else:
            attempts.append(f"website_blocked:{website}:{art.error}")
            blocker = {"name": cand.display_name, "reason": art.error or "website_unreachable", "url": website}

    # de-dupe menu urls
    seen_u: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for m in sorted(menu_urls, key=lambda x: int(x.get("priority_tier") or 5)):
        u = m["url"]
        if u in seen_u:
            continue
        seen_u.add(u)
        deduped.append(m)
    menu_urls = deduped[:max_menu_urls]

    if not menu_urls and website:
        # Last resort: treat homepage as menu candidate
        menu_urls = [{"url": website, "label": "homepage", "priority_tier": 5, "via": "homepage_fallback"}]
        attempts.append("homepage_as_menu_candidate")

    if not menu_urls:
        menus_missing = 1
        attempts.append("menu_missing_or_inaccessible")
        blocker = blocker or {
            "name": cand.display_name,
            "reason": "menu_missing_or_inaccessible",
            "attempts": attempts,
        }

    service = zone_service_payload(zone)
    service.update(
        {
            "contact": {"website": website},
            "places_types": list(cand.raw_types or []),
            "menu_discovery_attempts": attempts,
            "last_checked_at": datetime.utcnow().isoformat() + "Z",
        }
    )

    with session_scope() as session:
        upsert_restaurant(
            session,
            {
                "restaurant_id": rid,
                "campus_id": campus.campus_id,
                "university_id": campus.university_id,
                "name": cand.display_name or "Unknown restaurant",
                "branch_name": None,
                "address": {
                    "formatted": geo.formatted_address or address,
                    "source": "google_geocoding_api",
                    "places_runtime_hint": cand.formatted_address,
                },
                "lat": geo.lat,
                "lng": geo.lng,
                "geocode_provider": geo.provider,
                "geocoded_at": geo.geocoded_at.replace(tzinfo=None),
                "boundary_status": zone.dps_status,
                "boundary_id": campus.patrol_boundary_id or campus.boundary_id,
                "boundary_version": campus.patrol_boundary_version or campus.boundary_version,
                "near_uncertain_edge": zone.near_uncertain_edge,
                "categories": list(cand.raw_types or []),
                "cuisines": [],
                "website": website,
                "menu_links": [
                    {"url": m["url"], "label": m.get("label"), "priority_tier": m.get("priority_tier", 5)}
                    for m in menu_urls
                ],
                "business_status": (cand.business_status or "unknown").lower(),
                "service": service,
            },
        )
        pref = (
            session.query(ProviderRef)
            .filter_by(provider="google_places", place_id=cand.provider_place_id)
            .one_or_none()
        )
        if pref is None:
            session.add(
                ProviderRef(
                    restaurant_id=rid,
                    provider="google_places",
                    place_id=cand.provider_place_id,
                    refreshed_at=datetime.utcnow(),
                )
            )
        else:
            pref.restaurant_id = rid
            pref.refreshed_at = datetime.utcnow()

        for m in menu_urls:
            upsert_source(
                session,
                {
                    "source_id": f"src_{rid}_{hashlib.sha1(m['url'].encode()).hexdigest()[:10]}",
                    "restaurant_id": rid,
                    "url": m["url"],
                    "publisher": cand.display_name,
                    "source_type": m.get("label") or "other_permitted",
                    "priority_tier": int(m.get("priority_tier") or 5),
                    "limitations": f"discovered_via={m.get('via')}",
                },
            )

    # Fetch + extract
    docs = []
    fetch_errors: list[str] = []
    for m in menu_urls:
        art = fetcher.fetch(m["url"])
        if not art.ok:
            fetch_errors.append(f"{m['url']}: {art.error}")
            continue
        docs.append(artifact_to_evidence(art))

    dishes = 0
    with_price = 0
    with_nutrition = 0
    extraction: dict[str, Any] = {"menu_items": [], "conflicts": [], "ambiguities": []}

    if docs:
        from trojanbites_extract.parse.html import EvidenceDoc

        merged = EvidenceDoc(
            source_url=docs[0].source_url,
            content_hash=docs[0].content_hash,
            blocks=[b for d in docs for b in d.blocks],
            tables=[t for d in docs for t in d.tables],
        )
        det = deterministic_extract(merged, rid)
        extraction = det
        if extractor is not None:
            try:
                llm, meta = extractor.extract(
                    merged,
                    restaurant_id=rid,
                    restaurant_name=cand.display_name or "Unknown",
                    address_formatted=geo.formatted_address or address,
                )
                if meta.get("error"):
                    attempts.append(f"gemini_extract:{meta['error']}")
                elif llm.get("menu_items"):
                    extraction = merge_extractions(det, llm)
            except Exception as exc:  # noqa: BLE001
                fetch_errors.append(f"gemini_extract:{exc}")
                attempts.append(f"gemini_extract_failed:{exc}")

        # Claude fallback when Gemini quota/extraction yields nothing useful
        if not (extraction.get("menu_items") or []) and get_settings().anthropic_api_key:
            try:
                from trojanbites_extract.extract.claude import ClaudeExtractor

                claude_out, _costs = ClaudeExtractor().extract(
                    merged,
                    restaurant_id=rid,
                    restaurant_name=cand.display_name or "Unknown",
                    branch_name=None,
                    address_formatted=geo.formatted_address or address,
                )
                extraction = merge_extractions(det, claude_out)
                attempts.append("claude_extract_fallback")
            except Exception as exc:  # noqa: BLE001
                attempts.append(f"claude_fallback_failed:{exc}")

        report = validate_extraction(
            extraction, boundary_status=zone.dps_status, restaurant_id=rid
        )
        if not report.hard_fail:
            with session_scope() as session:
                replace_menu_for_restaurant(session, rid, extraction)
                # stamp last checked
                rest = session.get(Restaurant, rid)
                if rest:
                    svc = dict(rest.service_json or {})
                    svc["last_checked_at"] = datetime.utcnow().isoformat() + "Z"
                    svc["menu_discovery_attempts"] = attempts + fetch_errors
                    if not docs:
                        svc["menu_status"] = "missing_or_inaccessible"
                    else:
                        svc["menu_status"] = "extracted"
                    rest.service_json = svc
            for item in extraction.get("menu_items") or []:
                dishes += 1
                variants = item.get("variants") or []
                if any((v.get("price") or {}).get("amount") is not None for v in variants):
                    with_price += 1
                nut = item.get("nutrition") or {}
                pub = nut.get("published") or {}
                if any(pub.get(k) is not None for k in ("calories_kcal", "protein_g", "carbohydrates_g", "fat_g")):
                    with_nutrition += 1
        else:
            attempts.append(f"validation_failed:{report.reason_codes}")
            menus_missing = 1
    else:
        menus_missing = 1
        with session_scope() as session:
            rest = session.get(Restaurant, rid)
            if rest:
                svc = dict(rest.service_json or {})
                svc["menu_status"] = "missing_or_inaccessible"
                svc["menu_discovery_attempts"] = attempts + fetch_errors
                rest.service_json = svc

    return {
        "dishes": dishes,
        "with_price": with_price,
        "with_nutrition": with_nutrition,
        "menus_from_website": menus_from_website,
        "menus_from_pdf": menus_from_pdf,
        "menus_from_gemini_search": menus_from_gemini_search,
        "menus_missing": menus_missing,
        "blocker": blocker,
        "report": {
            "restaurant_id": rid,
            "name": cand.display_name,
            "address": geo.formatted_address or address,
            "lat": geo.lat,
            "lng": geo.lng,
            "location_zone": zone.location_zone,
            "dps_status": zone.dps_status,
            "campus_status": zone.campus_status,
            "website": website,
            "menu_urls": [m["url"] for m in menu_urls],
            "dishes": dishes,
            "with_price": with_price,
            "with_published_nutrition": with_nutrition,
            "attempts": attempts + fetch_errors,
            "last_checked_at": datetime.utcnow().isoformat() + "Z",
        },
    }


def _set_progress(job_id: str, stage: str, percent: int) -> None:
    with session_scope() as session:
        job = session.get(IngestionJob, job_id)
        if job:
            progress = dict(job.progress_json or {})
            progress.update({"stage": stage, "percent": percent})
            job.progress_json = progress
            job.status = "running"


def _finish(
    job_id: str, status: str, errors: list[str], summary: dict[str, Any]
) -> dict[str, Any]:
    with session_scope() as session:
        job = session.get(IngestionJob, job_id)
        if job:
            job.status = status
            job.errors_json = errors
            job.result_json = summary
            job.progress_json = {"stage": status, "percent": 100, **(job.progress_json or {})}
            job.finished_at = datetime.utcnow()
    return get_off_campus_job(job_id) or {"job_id": job_id, "status": status}
