from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Tile:
    lat: float
    lng: float
    radius_m: float


@dataclass
class DiscoveryCandidate:
    provider: str
    provider_place_id: str
    query_id: str | None = None
    raw_types: list[str] = field(default_factory=list)
    display_name: str | None = None  # runtime-only; not for redistributable export
    formatted_address: str | None = None  # runtime-only
    website_uri: str | None = None  # runtime hint for source discovery
    business_status: str | None = None
    lat: float | None = None  # Places coords: cache ≤30d; NEVER use for PiP
    lng: float | None = None


class DiscoveryAdapter(Protocol):
    def discover(self, tiles: list[Tile], types: list[str]) -> list[DiscoveryCandidate]: ...