from __future__ import annotations

from typing import Any

import httpx
from trojanbites_extract.provider_records import record_response

from trojanbites_extract.discovery.base import DiscoveryCandidate, Tile
from trojanbites_extract.settings import require_google_key


class PlacesDiscoveryAdapter:
    """Places API (New) Nearby Search — store Place IDs; treat display fields as runtime-only."""

    nearby_url = "https://places.googleapis.com/v1/places:searchNearby"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or require_google_key()

    def discover(
        self,
        tiles: list[Tile],
        types: list[str],
        max_result_count: int = 20,
    ) -> list[DiscoveryCandidate]:
        seen: set[str] = set()
        out: list[DiscoveryCandidate] = []
        field_mask = ",".join(
            [
                "places.id",
                "places.types",
                "places.displayName",
                "places.formattedAddress",
                "places.location",
                "places.businessStatus",
                "places.websiteUri",
                "places.photos",
            ]
        )
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": field_mask,
        }
        with httpx.Client(timeout=30.0) as client:
            for i, tile in enumerate(tiles):
                body: dict[str, Any] = {
                    "includedTypes": types,
                    "maxResultCount": max_result_count,
                    "locationRestriction": {
                        "circle": {
                            "center": {"latitude": tile.lat, "longitude": tile.lng},
                            "radius": float(tile.radius_m),
                        }
                    },
                }
                resp = client.post(self.nearby_url, headers=headers, json=body)
                record_response('google_maps','nearby_search',resp)
                if resp.status_code == 429:
                    resp.raise_for_status()
                resp.raise_for_status()
                data = resp.json()
                for place in data.get("places") or []:
                    pid = place.get("id")
                    if not pid or pid in seen:
                        continue
                    seen.add(pid)
                    loc = place.get("location") or {}
                    name = (place.get("displayName") or {}).get("text")
                    photo = next((ph for ph in place.get("photos") or [] if isinstance(ph, dict) and ph.get("name")), {})
                    credit = next((a.get("displayName") for a in photo.get("authorAttributions") or [] if isinstance(a, dict) and a.get("displayName")), None)
                    out.append(
                        DiscoveryCandidate(
                            provider="google_places",
                            provider_place_id=pid,
                            query_id=f"tile_{i}",
                            raw_types=list(place.get("types") or []),
                            display_name=name,
                            formatted_address=place.get("formattedAddress"),
                            website_uri=place.get("websiteUri"),
                            business_status=place.get("businessStatus"),
                            lat=loc.get("latitude"),
                            lng=loc.get("longitude"),
                            photo_name=photo.get("name"),
                            photo_credit=credit,
                        )
                    )
        return out