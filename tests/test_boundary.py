from trojanbites_extract.boundary.load import load_boundary
from trojanbites_extract.boundary.pip import point_in_polygon


def test_boundary_loads():
    b = load_boundary("usc_upc_dps", "v2025-01")
    assert b.approximation is True
    assert not b.geometry.is_empty


def test_campus_center_inside():
    b = load_boundary("usc_upc_dps", "v2025-01")
    # Approximate Tommy Trojan / central campus
    r = point_in_polygon(34.0224, -118.2851, b, epsilon_m=15)
    assert r.status in {"inside", "boundary"}


def test_far_away_outside():
    b = load_boundary("usc_upc_dps", "v2025-01")
    r = point_in_polygon(34.05, -118.25, b, epsilon_m=15)
    assert r.status == "outside"


def test_unknown_without_coords():
    b = load_boundary("usc_upc_dps", "v2025-01")
    r = point_in_polygon(None, None, b)
    assert r.status == "unknown"