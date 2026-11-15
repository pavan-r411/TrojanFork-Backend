from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from trojanbites_extract.settings import ROOT


@dataclass(frozen=True)
class CampusConfig:
    campus_id: str
    university_id: str
    display_name: str
    short_name: str
    center_lat: float
    center_lng: float
    boundary_type: str  # official_patrol | search_radius
    boundary_id: str | None
    boundary_version: str | None
    boundary_radius_miles: float | None
    boundary_official: bool
    boundary_notes: str | None
    boundary_source_url: str | None
    campus_boundary_id: str | None = None
    campus_boundary_version: str | None = None
    campus_boundary_source_url: str | None = None
    patrol_boundary_id: str | None = None
    patrol_boundary_version: str | None = None
    village_as_off_campus: bool = True
    default_walk_miles: float = 0.3
    max_walk_miles: float = 1.0
    places_tile_radius_m: float = 500.0
    included_types: list[str] = field(default_factory=lambda: ["restaurant"])
    off_campus_discovery: dict[str, Any] = field(default_factory=dict)
    seeds: list[dict[str, Any]] = field(default_factory=list)
    timezone: str = "America/Los_Angeles"
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def uses_geojson_boundary(self) -> bool:
        return self.boundary_type == "official_patrol" and bool(self.boundary_id)


def _campuses_dir() -> Path:
    return ROOT / "config" / "campuses"


@lru_cache
def load_universities_registry() -> dict[str, Any]:
    path = ROOT / "config" / "universities.yaml"
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _parse_campus(data: dict[str, Any]) -> CampusConfig:
    center = data.get("center") or {}
    boundary = data.get("boundary") or {}
    campus_boundary = data.get("campus_boundary") or {}
    patrol_boundary = data.get("patrol_boundary") or {}
    ownership = data.get("pipeline_ownership") or {}
    discovery = data.get("discovery") or {}
    return CampusConfig(
        campus_id=data["campus_id"],
        university_id=data["university_id"],
        display_name=data.get("display_name") or data["campus_id"],
        short_name=data.get("short_name") or data["campus_id"],
        center_lat=float(center["lat"]),
        center_lng=float(center["lng"]),
        boundary_type=boundary.get("type") or "search_radius",
        boundary_id=boundary.get("boundary_id"),
        boundary_version=boundary.get("boundary_version"),
        boundary_radius_miles=(
            float(boundary["radius_miles"])
            if boundary.get("radius_miles") is not None
            else None
        ),
        boundary_official=bool(boundary.get("official", boundary.get("type") == "official_patrol")),
        boundary_notes=boundary.get("notes"),
        boundary_source_url=boundary.get("source_url"),
        campus_boundary_id=campus_boundary.get("boundary_id"),
        campus_boundary_version=campus_boundary.get("boundary_version"),
        campus_boundary_source_url=campus_boundary.get("source_url"),
        patrol_boundary_id=patrol_boundary.get("boundary_id") or boundary.get("boundary_id"),
        patrol_boundary_version=patrol_boundary.get("boundary_version")
        or boundary.get("boundary_version"),
        village_as_off_campus=bool(ownership.get("village_as_off_campus", True)),
        default_walk_miles=float(discovery.get("default_walk_miles", 0.3)),
        max_walk_miles=float(discovery.get("max_walk_miles", 1.0)),
        places_tile_radius_m=float(discovery.get("places_tile_radius_m", 500)),
        included_types=list(discovery.get("included_types") or ["restaurant"]),
        off_campus_discovery=dict(discovery.get("off_campus_dps") or {}),
        seeds=list(data.get("seeds") or []),
        timezone=data.get("timezone") or "America/Los_Angeles",
        raw=data,
    )


@lru_cache
def load_campus(campus_id: str) -> CampusConfig:
    path = _campuses_dir() / f"{campus_id}.yaml"
    if not path.exists():
        # try registry-relative path
        reg = load_universities_registry()
        for uni in reg.get("universities") or []:
            for camp in uni.get("campuses") or []:
                if camp.get("campus_id") == campus_id:
                    rel = camp.get("config")
                    if rel:
                        path = ROOT / "config" / rel
                    break
        if not path.exists():
            raise KeyError(f"Unknown campus_id: {campus_id}")
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if data.get("campus_id") != campus_id:
        # allow file name mismatch only if campus_id inside matches request
        if data.get("campus_id") and data["campus_id"] != campus_id:
            raise ValueError(f"Campus file campus_id mismatch for {campus_id}")
    return _parse_campus(data)


def list_campuses() -> list[CampusConfig]:
    reg = load_universities_registry()
    out: list[CampusConfig] = []
    for uni in reg.get("universities") or []:
        for camp in uni.get("campuses") or []:
            out.append(load_campus(camp["campus_id"]))
    # de-dupe while preserving order
    seen: set[str] = set()
    unique: list[CampusConfig] = []
    for c in out:
        if c.campus_id in seen:
            continue
        seen.add(c.campus_id)
        unique.append(c)
    return unique


def clear_campus_cache() -> None:
    load_universities_registry.cache_clear()
    load_campus.cache_clear()
