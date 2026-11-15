from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.geometry.base import BaseGeometry

from trojanbites_extract.settings import get_settings


@dataclass(frozen=True)
class BoundarySnapshot:
    boundary_id: str
    version: str
    source_url: str | None
    retrieved_at: str | None
    geometry: BaseGeometry
    metadata: dict[str, Any]
    geojson_path: Path
    approximation: bool


def boundary_dir(boundary_id: str, version: str) -> Path:
    return get_settings().boundaries_dir / boundary_id / version


def load_boundary(boundary_id: str, version: str) -> BoundarySnapshot:
    base = boundary_dir(boundary_id, version)
    geojson_path = base / "boundary.geojson"
    meta_path = base / "metadata.json"
    if not geojson_path.exists():
        raise FileNotFoundError(f"Missing boundary GeoJSON: {geojson_path}")
    if not meta_path.exists():
        raise FileNotFoundError(f"Missing boundary metadata: {meta_path}")

    with geojson_path.open(encoding="utf-8") as f:
        gj = json.load(f)
    with meta_path.open(encoding="utf-8") as f:
        meta = json.load(f)

    features = gj.get("features") or []
    if not features:
        raise ValueError("Boundary GeoJSON has no features")
    geom = shape(features[0]["geometry"])
    if not isinstance(geom, (Polygon, MultiPolygon)):
        raise ValueError(f"Unsupported geometry type: {geom.geom_type}")
    if not geom.is_valid:
        raise ValueError("Boundary geometry is invalid")
    if geom.is_empty:
        raise ValueError("Boundary geometry is empty")

    return BoundarySnapshot(
        boundary_id=meta.get("boundary_id", boundary_id),
        version=meta.get("version", version),
        source_url=meta.get("source_url"),
        retrieved_at=meta.get("source_retrieved_at"),
        geometry=geom,
        metadata=meta,
        geojson_path=geojson_path,
        approximation=bool(meta.get("approximation", True)),
    )