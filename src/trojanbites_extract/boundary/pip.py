from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import Point

from trojanbites_extract.boundary.load import BoundarySnapshot

# Approx meters-per-degree at USC latitude (~34N)
_M_PER_DEG_LAT = 111_000.0
_M_PER_DEG_LNG = 92_000.0  # cos(34°) * 111km


@dataclass(frozen=True)
class BoundaryResult:
    status: str  # inside | boundary | outside | unknown
    boundary_id: str
    boundary_version: str
    near_uncertain_edge: bool


def _buffer_deg(meters: float) -> float:
    return meters / min(_M_PER_DEG_LAT, _M_PER_DEG_LNG)


def point_in_polygon(
    lat: float | None,
    lng: float | None,
    boundary: BoundarySnapshot,
    epsilon_m: float = 15.0,
) -> BoundaryResult:
    """Classify a point against the campus boundary.

    Coordinates must be independently sourced (not Places lat/lng used for PiP policy).
    """
    if lat is None or lng is None:
        return BoundaryResult(
            status="unknown",
            boundary_id=boundary.boundary_id,
            boundary_version=boundary.version,
            near_uncertain_edge=False,
        )

    pt = Point(lng, lat)
    geom = boundary.geometry
    eps = _buffer_deg(epsilon_m)
    near_edge = geom.boundary.buffer(eps).intersects(pt)

    if geom.contains(pt):
        if near_edge:
            return BoundaryResult("boundary", boundary.boundary_id, boundary.version, True)
        return BoundaryResult("inside", boundary.boundary_id, boundary.version, False)

    if geom.touches(pt) or near_edge:
        return BoundaryResult("boundary", boundary.boundary_id, boundary.version, True)

    return BoundaryResult("outside", boundary.boundary_id, boundary.version, False)