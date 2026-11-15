from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SeedRestaurant:
    name: str
    branch_name: str | None
    address: str
    website: str | None
    menu_urls: list[str]
    cuisines: list[str]
    categories: list[str]
    source_type: str
    lat: float | None = None
    lng: float | None = None
    notes: str | None = None


# Curated pilot seeds — official / campus sources. Expand as URLs are verified.
USC_DINING_AND_PILOT_SEEDS: list[SeedRestaurant] = [
    SeedRestaurant(
        name="Everybody's Kitchen",
        branch_name="EVK",
        address="642 W 34th St, Los Angeles, CA 90089",
        website="https://hospitality.usc.edu/dining-hall-menus/",
        menu_urls=["https://hospitality.usc.edu/dining-hall-menus/"],
        cuisines=["american", "campus_dining"],
        categories=["dining_hall"],
        source_type="campus_hospitality",
        lat=34.0211,
        lng=-118.2858,
        notes="USC residential dining; AYCE / meal swipe model — item prices may be null.",
    ),
    SeedRestaurant(
        name="USC Village Dining Hall",
        branch_name="Village",
        address="3301 S Hoover St, Los Angeles, CA 90007",
        website="https://hospitality.usc.edu/dining-hall-menus/",
        menu_urls=["https://hospitality.usc.edu/dining-hall-menus/"],
        cuisines=["american", "campus_dining"],
        categories=["dining_hall"],
        source_type="campus_hospitality",
        lat=34.0252,
        lng=-118.2851,
    ),
    SeedRestaurant(
        name="Parkside Residential Dining Hall",
        branch_name="Parkside",
        address="3771 McClintock Ave, Los Angeles, CA 90089",
        website="https://hospitality.usc.edu/dining-hall-menus/",
        menu_urls=["https://hospitality.usc.edu/dining-hall-menus/"],
        cuisines=["american", "campus_dining"],
        categories=["dining_hall"],
        source_type="campus_hospitality",
        lat=34.0189,
        lng=-118.2901,
    ),
]


def load_seed_restaurants() -> list[SeedRestaurant]:
    return list(USC_DINING_AND_PILOT_SEEDS)