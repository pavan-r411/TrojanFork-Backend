from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from trojanbites_extract.settings import require_google_key


@dataclass(frozen=True)
class GeocodeResult:
    lat: float
    lng: float
    provider: str
    geocoded_at: datetime
    precision: str | None
    formatted_address: str | None


class GoogleGeocoder:
    """Geocode independently obtained addresses. Do not feed Places lat/lng into PiP."""

    endpoint = "https://maps.googleapis.com/maps/api/geocode/json"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or require_google_key()

    def geocode(self, address: str) -> GeocodeResult | None:
        params = {"address": address, "key": self.api_key}
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(self.endpoint, params=params)
            resp.raise_for_status()
            data = resp.json()
        if data.get("status") != "OK" or not data.get("results"):
            return None
        top = data["results"][0]
        loc = top["geometry"]["location"]
        return GeocodeResult(
            lat=float(loc["lat"]),
            lng=float(loc["lng"]),
            provider="google_geocoding_api",
            geocoded_at=datetime.now(timezone.utc),
            precision=top["geometry"].get("location_type"),
            formatted_address=top.get("formatted_address"),
        )