from __future__ import annotations

from dataclasses import dataclass

from trojanbites_extract.campus.registry import (
    CampusConfig,
    list_campuses,
    load_campus,
    load_universities_registry,
)
from trojanbites_extract.query.filters import haversine_miles


@dataclass(frozen=True)
class CampusCandidate:
    campus_id: str
    university_id: str
    display_name: str
    distance_miles: float
    boundary_type: str
    boundary_official: bool


@dataclass(frozen=True)
class CampusResolution:
    status: str  # resolved | needs_confirmation | unresolved | manual
    active_campus_id: str | None
    candidates: list[CampusCandidate]
    message: str
    user_lat: float | None = None
    user_lng: float | None = None


def resolve_campus(
    *,
    lat: float | None = None,
    lng: float | None = None,
    campus_id: str | None = None,
) -> CampusResolution:
    """Resolve active campus from manual selection or coordinates.

    Never silently picks a distant campus. If multiple are plausible, needs_confirmation.
    """
    if campus_id:
        try:
            camp = load_campus(campus_id)
        except KeyError:
            return CampusResolution(
                status="unresolved",
                active_campus_id=None,
                candidates=[],
                message=f"Unknown campus_id '{campus_id}'",
                user_lat=lat,
                user_lng=lng,
            )
        return CampusResolution(
            status="manual",
            active_campus_id=camp.campus_id,
            candidates=[
                CampusCandidate(
                    campus_id=camp.campus_id,
                    university_id=camp.university_id,
                    display_name=camp.display_name,
                    distance_miles=(
                        haversine_miles(lat, lng, camp.center_lat, camp.center_lng)
                        if lat is not None and lng is not None
                        else 0.0
                    ),
                    boundary_type=camp.boundary_type,
                    boundary_official=camp.boundary_official,
                )
            ],
            message=f"Manual campus selection: {camp.display_name}",
            user_lat=lat,
            user_lng=lng,
        )

    if lat is None or lng is None:
        return CampusResolution(
            status="unresolved",
            active_campus_id=None,
            candidates=[],
            message="Provide campus_id or lat/lng",
            user_lat=lat,
            user_lng=lng,
        )

    reg = load_universities_registry()
    auto_max = float(reg.get("auto_select_max_miles", 2.0))
    cand_max = float(reg.get("candidate_max_miles", 8.0))

    scored: list[CampusCandidate] = []
    for camp in list_campuses():
        dist = haversine_miles(lat, lng, camp.center_lat, camp.center_lng)
        if dist <= cand_max:
            scored.append(
                CampusCandidate(
                    campus_id=camp.campus_id,
                    university_id=camp.university_id,
                    display_name=camp.display_name,
                    distance_miles=round(dist, 3),
                    boundary_type=camp.boundary_type,
                    boundary_official=camp.boundary_official,
                )
            )
    scored.sort(key=lambda c: c.distance_miles)

    if not scored:
        return CampusResolution(
            status="unresolved",
            active_campus_id=None,
            candidates=[],
            message="No configured universities near these coordinates",
            user_lat=lat,
            user_lng=lng,
        )

    near = [c for c in scored if c.distance_miles <= auto_max]
    if len(near) == 1:
        return CampusResolution(
            status="resolved",
            active_campus_id=near[0].campus_id,
            candidates=scored,
            message=f"Auto-selected {near[0].display_name} ({near[0].distance_miles} mi)",
            user_lat=lat,
            user_lng=lng,
        )
    if len(near) > 1:
        return CampusResolution(
            status="needs_confirmation",
            active_campus_id=None,
            candidates=near,
            message="Multiple campuses nearby — confirm which university to use",
            user_lat=lat,
            user_lng=lng,
        )

    # Closest is outside auto range but inside candidate range
    return CampusResolution(
        status="needs_confirmation",
        active_campus_id=None,
        candidates=scored[:5],
        message=(
            f"Nearest campus is {scored[0].display_name} "
            f"({scored[0].distance_miles} mi). Confirm to proceed."
        ),
        user_lat=lat,
        user_lng=lng,
    )


def point_in_campus_area(lat: float, lng: float, campus: CampusConfig) -> tuple[str, bool]:
    """Return (status, near_edge) for campus membership.

    official_patrol → GeoJSON PiP
    search_radius → distance to center vs configured radius (labeled non-official)
    """
    if campus.uses_geojson_boundary:
        from trojanbites_extract.boundary.load import load_boundary
        from trojanbites_extract.boundary.pip import point_in_polygon

        boundary = load_boundary(campus.boundary_id or "", campus.boundary_version or "")
        result = point_in_polygon(lat, lng, boundary)
        return result.status, result.near_uncertain_edge

    radius = campus.boundary_radius_miles or 1.0
    dist = haversine_miles(lat, lng, campus.center_lat, campus.center_lng)
    if dist <= radius * 0.95:
        return "inside", False
    if dist <= radius:
        return "boundary", True
    return "outside", False
