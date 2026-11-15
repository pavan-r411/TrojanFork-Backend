from __future__ import annotations

from shapely.geometry.base import BaseGeometry

from trojanbites_extract.discovery.base import Tile


def cover_polygon_with_circles(geom: BaseGeometry, radius_m: float) -> list[Tile]:
    """Simple grid of circle centers covering the polygon bbox.

    Circles are for Places search tiling only — not membership tests.
    """
    minx, miny, maxx, maxy = geom.bounds
    # Convert radius meters → rough degrees
    step_lat = (radius_m * 0.75) / 111_000.0
    step_lng = (radius_m * 0.75) / 92_000.0
    tiles: list[Tile] = []
    y = miny
    while y <= maxy:
        x = minx
        while x <= maxx:
            tiles.append(Tile(lat=y, lng=x, radius_m=radius_m))
            x += step_lng
        y += step_lat
    return tiles