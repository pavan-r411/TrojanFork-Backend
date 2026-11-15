"""Campus vs DPS zone classification for pipeline ownership.

Teammate scope: dining locations inside the University Park Campus academic core
(and campus hospitality dining halls). This pipeline owns businesses that are
outside the campus core but inside the DPS patrol polygon, including USC Village
commercial restaurants.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from trojanbites_extract.boundary.load import load_boundary
from trojanbites_extract.boundary.pip import point_in_polygon
from trojanbites_extract.campus.registry import CampusConfig


CAMPUS_HOSPITALITY_CATEGORIES = {"dining_hall", "campus_dining"}
CAMPUS_HOSPITALITY_SOURCE_TYPES = {"campus_hospitality"}

# Stable hospitality names owned by the on-campus teammate pipeline
TEAMMATE_DINING_NAMES = {
    "everybody's kitchen",
    "evk",
    "parkside restaurant & grill",
    "parkside residential dining hall",
    "parkside",
    "usc village dining hall",
    "village dining hall",
}


@dataclass(frozen=True)
class ZoneClassification:
    dps_status: str
    campus_status: str
    location_zone: str  # off_campus_dps | on_campus | outside_dps | unknown
    pipeline_owner: str  # off_campus | on_campus_teammate | none
    near_uncertain_edge: bool
    reasons: tuple[str, ...]


def _norm_name(name: str | None) -> str:
    return (name or "").strip().lower()


def is_teammate_hospitality(
    *,
    name: str | None = None,
    categories: list[str] | None = None,
    source_type: str | None = None,
) -> bool:
    cats = {c.lower() for c in (categories or [])}
    if cats & CAMPUS_HOSPITALITY_CATEGORIES:
        return True
    if (source_type or "").lower() in CAMPUS_HOSPITALITY_SOURCE_TYPES:
        return True
    n = _norm_name(name)
    if n in TEAMMATE_DINING_NAMES:
        return True
    if "dining hall" in n and "usc" in n:
        return True
    return False


def classify_location(
    lat: float | None,
    lng: float | None,
    campus: CampusConfig,
    *,
    name: str | None = None,
    categories: list[str] | None = None,
    source_type: str | None = None,
    epsilon_m: float | None = None,
) -> ZoneClassification:
    """Classify a point for off-campus DPS ownership.

    Requires independently geocoded lat/lng (not Places display coords) for
    authoritative membership. Places coords may be passed only for provisional
    screening when geocode is pending — mark unknown if policy requires.
    """
    eps = float(epsilon_m if epsilon_m is not None else 15)
    reasons: list[str] = []

    patrol_id = campus.patrol_boundary_id or campus.boundary_id
    patrol_ver = campus.patrol_boundary_version or campus.boundary_version
    if not patrol_id or not patrol_ver:
        return ZoneClassification(
            dps_status="unknown",
            campus_status="unknown",
            location_zone="unknown",
            pipeline_owner="none",
            near_uncertain_edge=False,
            reasons=("missing_patrol_boundary_config",),
        )

    dps = load_boundary(patrol_id, patrol_ver)
    dps_r = point_in_polygon(lat, lng, dps, epsilon_m=eps)

    campus_status = "unknown"
    campus_near = False
    if campus.campus_boundary_id and campus.campus_boundary_version:
        campus_b = load_boundary(campus.campus_boundary_id, campus.campus_boundary_version)
        campus_r = point_in_polygon(lat, lng, campus_b, epsilon_m=eps)
        campus_status = campus_r.status
        campus_near = campus_r.near_uncertain_edge
    else:
        reasons.append("campus_boundary_not_configured")

    hospitality = is_teammate_hospitality(
        name=name, categories=categories, source_type=source_type
    )
    if hospitality:
        reasons.append("campus_hospitality_seed")

    near = bool(dps_r.near_uncertain_edge or campus_near)
    in_dps = dps_r.status in {"inside", "boundary"}
    in_campus = campus_status in {"inside", "boundary"}

    if hospitality:
        return ZoneClassification(
            dps_status=dps_r.status,
            campus_status=campus_status,
            location_zone="on_campus" if in_campus else "off_campus_dps",
            pipeline_owner="on_campus_teammate",
            near_uncertain_edge=near,
            reasons=tuple(reasons),
        )

    if lat is None or lng is None:
        return ZoneClassification(
            dps_status=dps_r.status,
            campus_status=campus_status,
            location_zone="unknown",
            pipeline_owner="none",
            near_uncertain_edge=False,
            reasons=tuple(reasons + ["coords_missing"]),
        )

    if not in_dps:
        return ZoneClassification(
            dps_status=dps_r.status,
            campus_status=campus_status,
            location_zone="outside_dps",
            pipeline_owner="none",
            near_uncertain_edge=near,
            reasons=tuple(reasons + ["outside_dps_patrol"]),
        )

    # Village commercial and other DPS-area businesses outside academic core
    if in_campus:
        reasons.append("inside_campus_core")
        return ZoneClassification(
            dps_status=dps_r.status,
            campus_status=campus_status,
            location_zone="on_campus",
            pipeline_owner="on_campus_teammate",
            near_uncertain_edge=near,
            reasons=tuple(reasons),
        )

    if campus.village_as_off_campus:
        reasons.append("village_commercial_or_off_campus_dps")

    return ZoneClassification(
        dps_status=dps_r.status,
        campus_status=campus_status,
        location_zone="off_campus_dps",
        pipeline_owner="off_campus",
        near_uncertain_edge=near,
        reasons=tuple(reasons),
    )


def zone_service_payload(zone: ZoneClassification) -> dict[str, Any]:
    return {
        "location_zone": zone.location_zone,
        "pipeline_owner": zone.pipeline_owner,
        "dps_membership": zone.dps_status,
        "campus_membership": zone.campus_status,
        "near_uncertain_edge": zone.near_uncertain_edge,
        "zone_reasons": list(zone.reasons),
        "is_campus_dining": zone.pipeline_owner == "on_campus_teammate",
    }
