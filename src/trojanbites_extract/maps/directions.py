"""Google Maps walking-directions URLs.

These are links the student can open. They do not call the Directions API,
do not embed an API key, and do not replace the straight-line walk estimate.

Origin is omitted by default so Google Maps uses the device location.
"""
from __future__ import annotations

from urllib.parse import urlencode

_DIRECTIONS = "https://www.google.com/maps/dir/"


def walking_directions_url(
    *,
    origin_lat: float | None = None,
    origin_lng: float | None = None,
    place_id: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
    address: str | None = None,
) -> str | None:
    """Return a walking directions URL, or None when destination is missing.

    Prefer verified coordinates, then a complete address, then place_id alone.
    When origin is omitted, Google Maps chooses the starting location.
    """
    destination = None
    if lat is not None and lng is not None:
        destination = f"{lat},{lng}"
    elif address and str(address).strip():
        destination = str(address).strip()
    elif place_id:
        # Place ID alone is accepted by destination_place_id; still need a destination string.
        destination = str(place_id).strip()
    if not destination:
        return None
    params: dict[str, str] = {
        "api": "1",
        "destination": destination,
        "travelmode": "walking",
    }
    if origin_lat is not None and origin_lng is not None:
        params["origin"] = f"{origin_lat},{origin_lng}"
    if place_id:
        params["destination_place_id"] = place_id
    return _DIRECTIONS + "?" + urlencode(params)


def build_directions(
    *,
    name: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
    address: str | None = None,
    place_id: str | None = None,
    origin_lat: float | None = None,
    origin_lng: float | None = None,
    location_confirmed_at: str | None = None,
    truck: bool = False,
) -> dict:
    """Structured directions payload for meal cards."""
    url = walking_directions_url(
        origin_lat=origin_lat,
        origin_lng=origin_lng,
        place_id=place_id,
        lat=lat,
        lng=lng,
        address=address,
    )
    if truck and not location_confirmed_at:
        return {
            "available": False,
            "label": "Get directions",
            "travel_mode": "walking",
            "url": None,
            "destination": {
                "name": name,
                "lat": lat,
                "lng": lng,
                "address": address,
                "place_id": place_id,
            },
            "location_confirmed_at": location_confirmed_at,
            "unavailable_reason": "stale_truck_location",
            "notes": "No recently verified truck location is available.",
        }
    if not url:
        return {
            "available": False,
            "label": "Get directions",
            "travel_mode": "walking",
            "url": None,
            "destination": {
                "name": name,
                "lat": lat,
                "lng": lng,
                "address": address,
                "place_id": place_id,
            },
            "location_confirmed_at": location_confirmed_at,
            "unavailable_reason": "missing_destination",
            "notes": "Destination coordinates or address are unavailable.",
        }
    return {
        "available": True,
        "label": "Get directions",
        "travel_mode": "walking",
        "url": url,
        "destination": {
            "name": name,
            "lat": lat,
            "lng": lng,
            "address": address,
            "place_id": place_id,
        },
        "location_confirmed_at": location_confirmed_at,
        "unavailable_reason": None,
        "notes": "Starting location is determined by Google Maps when origin is omitted.",
    }
