from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from trojanbites_extract.boundary.load import load_boundary
from trojanbites_extract.boundary.pip import point_in_polygon
from trojanbites_extract.discovery.seeds import SeedRestaurant, load_seed_restaurants
from trojanbites_extract.extract.claude import ClaudeExtractor
from trojanbites_extract.extract.deterministic import deterministic_extract
from trojanbites_extract.extract.merge import merge_extractions
from trojanbites_extract.ids import new_id
from trojanbites_extract.parse.dispatch import artifact_to_evidence
from trojanbites_extract.parse.html import EvidenceDoc
from trojanbites_extract.retrieve.fetcher import SafeFetcher
from trojanbites_extract.settings import get_settings, load_extraction_config
from trojanbites_extract.store.db import init_db, session_scope
from trojanbites_extract.store.models import ExtractionRun, ProviderRef, Restaurant, Source
from trojanbites_extract.store.upserts import (
    replace_menu_for_restaurant,
    upsert_restaurant,
    upsert_source,
)
from trojanbites_extract.validate.review import enqueue_review
from trojanbites_extract.validate.rules import validate_extraction

logger = logging.getLogger(__name__)


@dataclass
class RunResult:
    restaurant_id: str
    status: str
    detail: str | None = None


def ingest_seeds(geocode: bool = False) -> list[str]:
    """Load curated seed restaurants, apply PiP with independent coords."""
    init_db()
    cfg = load_extraction_config()
    boundary = load_boundary(cfg["boundary_id"], cfg["boundary_version"])
    epsilon = float(cfg.get("boundary", {}).get("edge_epsilon_m", 15))
    ids: list[str] = []

    with session_scope() as session:
        for seed in load_seed_restaurants():
            rid = _seed_to_db(session, seed, boundary, epsilon, geocode=geocode)
            ids.append(rid)
    return ids


def _seed_to_db(session, seed: SeedRestaurant, boundary, epsilon: float, geocode: bool) -> str:
    lat, lng = seed.lat, seed.lng
    geocode_provider = "seed_curated"
    geocoded_at = datetime.utcnow()
    if geocode and seed.address:
        try:
            from trojanbites_extract.geocoding.adapter import GoogleGeocoder

            result = GoogleGeocoder().geocode(seed.address)
            if result:
                lat, lng = result.lat, result.lng
                geocode_provider = result.provider
                geocoded_at = result.geocoded_at.replace(tzinfo=None)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Geocode failed for %s: %s", seed.name, exc)

    br = point_in_polygon(lat, lng, boundary, epsilon_m=epsilon)
    rid = new_id("rest")
    # Stable-ish id from name+branch for re-runs
    digest = hashlib.sha1(f"{seed.name}|{seed.branch_name}|{seed.address}".encode()).hexdigest()[:10]
    rid = f"rest_seed_{digest}"

    upsert_restaurant(
        session,
        {
            "restaurant_id": rid,
            "name": seed.name,
            "branch_name": seed.branch_name,
            "address": {"formatted": seed.address, "source": "seed"},
            "lat": lat,
            "lng": lng,
            "geocode_provider": geocode_provider,
            "geocoded_at": geocoded_at,
            "boundary_status": br.status,
            "boundary_id": br.boundary_id,
            "boundary_version": br.boundary_version,
            "near_uncertain_edge": br.near_uncertain_edge,
            "categories": seed.categories,
            "cuisines": seed.cuisines,
            "website": seed.website,
            "menu_links": [
                {"url": u, "label": None, "priority_tier": 1} for u in seed.menu_urls
            ],
            "business_status": "operational",
            "service": {},
        },
    )
    for url in seed.menu_urls:
        upsert_source(
            session,
            {
                "source_id": f"src_{digest}_{hashlib.sha1(url.encode()).hexdigest()[:8]}",
                "restaurant_id": rid,
                "url": url,
                "publisher": seed.name,
                "source_type": seed.source_type,
                "priority_tier": 1,
                "export_allowed": True,
                "limitations": seed.notes,
            },
        )
    return rid


def run_restaurant(
    restaurant_id: str,
    *,
    use_claude: bool = True,
    force: bool = False,
) -> RunResult:
    init_db()
    cfg = load_extraction_config()
    fetcher = SafeFetcher()
    run_id = new_id("run")

    with session_scope() as session:
        rest = session.get(Restaurant, restaurant_id)
        if rest is None:
            return RunResult(restaurant_id, "failed", "restaurant_not_found")

        run = ExtractionRun(
            run_id=run_id,
            restaurant_id=restaurant_id,
            started_at=datetime.utcnow(),
            status="running",
            prompt_version=cfg.get("claude", {}).get("prompt_version"),
            model_id=get_settings().anthropic_model if use_claude else None,
        )
        session.add(run)

        sources = (
            session.query(Source)
            .filter(Source.restaurant_id == restaurant_id)
            .order_by(Source.priority_tier.asc())
            .all()
        )
        if not sources and rest.menu_links_json:
            # synthesize from menu_links
            for link in rest.menu_links_json:
                sources.append(
                    upsert_source(
                        session,
                        {
                            "restaurant_id": restaurant_id,
                            "url": link["url"],
                            "source_type": "other_permitted",
                            "priority_tier": link.get("priority_tier", 5),
                        },
                    )
                )

        docs: list[EvidenceDoc] = []
        errors: list[str] = []
        hashes: list[str] = []
        for src in sources:
            if not src.url:
                continue
            art = fetcher.fetch(src.url)
            if not art.ok:
                errors.append(f"{src.url}: {art.error}")
                enqueue_review(
                    session,
                    entity_type="source",
                    entity_id=src.source_id,
                    reason_codes=["SOURCE_INACCESSIBLE"],
                    evidence_snapshot_ref=src.url,
                )
                continue
            if art.content_hash:
                hashes.append(art.content_hash)
                src.content_hash = art.content_hash
            docs.append(artifact_to_evidence(art))

        combined_hash = hashlib.sha256("|".join(hashes).encode()).hexdigest() if hashes else None
        if (
            not force
            and combined_hash
            and rest.last_content_hash == combined_hash
            and cfg.get("refresh", {}).get("skip_unchanged_hash", True)
        ):
            run.status = "succeeded"
            run.finished_at = datetime.utcnow()
            run.validation_status = "skipped"
            run.errors_json = errors
            return RunResult(restaurant_id, "skipped", "unchanged")

        if not docs:
            run.status = "failed"
            run.finished_at = datetime.utcnow()
            run.errors_json = errors or ["no_evidence"]
            return RunResult(restaurant_id, "failed", "no_evidence")

        # Merge evidence blocks
        merged_doc = EvidenceDoc(
            source_url=docs[0].source_url,
            content_hash=combined_hash,
            blocks=[b for d in docs for b in d.blocks],
            tables=[t for d in docs for t in d.tables],
        )

        det = deterministic_extract(merged_doc, restaurant_id)
        costs: dict[str, Any] = {}
        method = "deterministic"
        if use_claude:
            try:
                extractor = ClaudeExtractor()
                llm, costs = extractor.extract(
                    merged_doc,
                    restaurant_id=restaurant_id,
                    restaurant_name=rest.name,
                    branch_name=rest.branch_name,
                    address_formatted=(rest.address_json or {}).get("formatted"),
                )
                extraction = merge_extractions(det, llm)
                method = "hybrid"
            except Exception as exc:  # noqa: BLE001
                logger.exception("Claude extraction failed; using deterministic only")
                errors.append(f"claude_failed: {exc}")
                extraction = det
                method = "deterministic"
                enqueue_review(
                    session,
                    entity_type="restaurant",
                    entity_id=restaurant_id,
                    reason_codes=["SCHEMA_INVALID"],
                    evidence_snapshot_ref=combined_hash,
                    model_review_signals={"error": str(exc)},
                )
        else:
            extraction = det

        report = validate_extraction(
            extraction,
            boundary_status=rest.boundary_status,
            restaurant_id=restaurant_id,
        )
        run.extraction_method = method
        run.cost_metrics_json = costs
        run.conflicts_json = extraction.get("conflicts") or []
        run.errors_json = errors
        run.validation_status = "failed" if report.hard_fail else "passed"

        if report.hard_fail or report.reason_codes:
            enqueue_review(
                session,
                entity_type="restaurant",
                entity_id=restaurant_id,
                reason_codes=report.reason_codes or report.flags,
                evidence_snapshot_ref=combined_hash,
            )

        if report.hard_fail:
            run.status = "needs_review"
            run.finished_at = datetime.utcnow()
            return RunResult(restaurant_id, "needs_review", ",".join(report.reason_codes))

        replace_menu_for_restaurant(session, restaurant_id, extraction)
        rest.last_content_hash = combined_hash
        run.status = "partial" if errors else "succeeded"
        run.finished_at = datetime.utcnow()
        return RunResult(restaurant_id, run.status, None)


def discover_places() -> int:
    """Tile the boundary and upsert Place ID provider refs (+ seed-independent shell restaurants)."""
    init_db()
    cfg = load_extraction_config()
    boundary = load_boundary(cfg["boundary_id"], cfg["boundary_version"])
    from trojanbites_extract.discovery.places import PlacesDiscoveryAdapter
    from trojanbites_extract.discovery.tiles import cover_polygon_with_circles

    tiles = cover_polygon_with_circles(
        boundary.geometry, float(cfg.get("places", {}).get("tile_radius_m", 500))
    )
    adapter = PlacesDiscoveryAdapter()
    candidates = adapter.discover(
        tiles,
        cfg.get("places", {}).get("included_types", ["restaurant"]),
        max_result_count=int(cfg.get("places", {}).get("max_result_count", 20)),
    )

    count = 0
    with session_scope() as session:
        for cand in candidates:
            # Create shell restaurant without using Places lat/lng for PiP
            rid = f"rest_places_{hashlib.sha1(cand.provider_place_id.encode()).hexdigest()[:12]}"
            existing = session.get(Restaurant, rid)
            if existing is None:
                upsert_restaurant(
                    session,
                    {
                        "restaurant_id": rid,
                        "name": cand.display_name or "Unknown (Places discovery)",
                        "branch_name": None,
                        "address": {
                            "formatted": None,
                            "places_runtime_hint": cand.formatted_address,
                            "note": "Independently verify address before PiP/export coords",
                        },
                        "lat": None,
                        "lng": None,
                        "boundary_status": "unknown",
                        "boundary_id": boundary.boundary_id,
                        "boundary_version": boundary.version,
                        "categories": cand.raw_types,
                        "cuisines": [],
                        "website": cand.website_uri,
                        "menu_links": [],
                        "business_status": (cand.business_status or "unknown").lower(),
                    },
                )
                count += 1
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
    return count