"""Walking directions links. No Google request and no API key in the URL."""
from urllib.parse import parse_qs, urlparse

from trojanbites_extract.maps.directions import build_directions, walking_directions_url


def test_walking_url_uses_coordinates_and_place_id():
    url = walking_directions_url(
        place_id="ChIJ-good",
        lat=34.0203,
        lng=-118.2863,
        address="3551 Trousdale Pkwy, Los Angeles, CA",
    )
    query = parse_qs(urlparse(url).query)
    assert url.startswith("https://www.google.com/maps/dir/?")
    assert query["travelmode"] == ["walking"]
    assert "origin" not in query  # Google Maps picks starting location
    assert query["destination"] == ["34.0203,-118.2863"]
    assert query["destination_place_id"] == ["ChIJ-good"]
    assert "key" not in query
    assert "api_key" not in query


def test_optional_origin_is_included_when_provided():
    url = walking_directions_url(
        origin_lat=34.0224,
        origin_lng=-118.2851,
        lat=34.0203,
        lng=-118.2863,
    )
    assert parse_qs(urlparse(url).query)["origin"] == ["34.0224,-118.2851"]


def test_address_is_used_when_coordinates_are_missing():
    url = walking_directions_url(address="Ronald Tutor Campus Center")
    assert parse_qs(urlparse(url).query)["destination"] == ["Ronald Tutor Campus Center"]


def test_missing_destination_returns_none():
    assert walking_directions_url() is None


def test_build_directions_unavailable_without_destination():
    payload = build_directions(name="Unknown cart")
    assert payload["available"] is False
    assert payload["unavailable_reason"] == "missing_destination"
    assert payload["url"] is None


def test_build_directions_marks_unconfirmed_truck():
    payload = build_directions(name="Taco Truck", lat=34.02, lng=-118.28, truck=True)
    assert payload["available"] is False
    assert payload["unavailable_reason"] == "stale_truck_location"
