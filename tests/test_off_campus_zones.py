from trojanbites_extract.boundary.load import load_boundary
from trojanbites_extract.boundary.pip import point_in_polygon
from trojanbites_extract.campus.registry import clear_campus_cache, load_campus
from trojanbites_extract.campus.zones import classify_location, is_teammate_hospitality
from trojanbites_extract.extract.gemini import extract_links_from_html


def setup_function():
    clear_campus_cache()


def test_campus_and_dps_boundaries_load():
    campus_b = load_boundary("usc_upc_campus", "v2025-01")
    dps = load_boundary("usc_upc_dps", "v2025-01")
    assert campus_b.approximation is True
    assert dps.approximation is True
    # Tommy Trojan inside both
    assert point_in_polygon(34.0224, -118.2851, campus_b).status in {"inside", "boundary"}
    assert point_in_polygon(34.0224, -118.2851, dps).status in {"inside", "boundary"}


def test_village_retail_is_off_campus_dps():
    campus = load_campus("usc_upc")
    # North of Jefferson / Village commercial
    zone = classify_location(
        34.0256,
        -118.2852,
        campus,
        name="Sweetgreen",
        categories=["restaurant"],
    )
    assert zone.location_zone == "off_campus_dps"
    assert zone.pipeline_owner == "off_campus"
    assert zone.dps_status in {"inside", "boundary"}
    assert zone.campus_status == "outside"


def test_evk_hospitality_owned_by_teammate():
    campus = load_campus("usc_upc")
    zone = classify_location(
        34.0211,
        -118.2858,
        campus,
        name="Everybody's Kitchen",
        categories=["dining_hall"],
    )
    assert zone.pipeline_owner == "on_campus_teammate"
    assert is_teammate_hospitality(name="USC Village Dining Hall", categories=[])


def test_extract_menu_links_from_html():
    html = """
    <html><body>
      <a href="/menu">View Menu</a>
      <a href="/nutrition-info">Nutrition</a>
      <a href="https://order.example.com/usc">Order Online</a>
      <a href="/files/menu.pdf">PDF Menu</a>
    </body></html>
    """
    links = extract_links_from_html(html, "https://example.com/")
    kinds = {x["kind"] for x in links}
    assert "html_menu" in kinds
    assert "nutrition" in kinds
    assert "ordering" in kinds
    assert "pdf_menu" in kinds
