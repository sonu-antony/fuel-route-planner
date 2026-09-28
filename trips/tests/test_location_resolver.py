import pytest

from stations.services.city_lookup import CityLookup
from trips.exceptions import LocationNotFound, LocationOutsideUSA
from trips.services.location_resolver import resolve_location


@pytest.fixture
def city_lookup():
    return CityLookup(
        {
            ("CHICAGO", "IL"): (41.8781, -87.6298),
            ("ANCHORAGE", "AK"): (61.2181, -149.9003),
        }
    )


def test_city_and_state_query_uses_the_city_lookup(city_lookup):
    assert resolve_location("Chicago, IL", city_lookup) == (41.8781, -87.6298)


def test_coordinates_are_parsed_directly(city_lookup):
    assert resolve_location("41.8781,-87.6298", city_lookup) == (41.8781, -87.6298)


def test_anything_else_raises_location_not_found(city_lookup):
    with pytest.raises(LocationNotFound):
        resolve_location("Nowhereville, ZZ", city_lookup)


def test_coordinates_outside_the_continental_usa_raise_location_outside_usa(city_lookup):
    with pytest.raises(LocationOutsideUSA):
        resolve_location("61.2181,-149.9003", city_lookup)


def test_a_us_city_outside_the_continental_bounding_box_also_raises(city_lookup):
    with pytest.raises(LocationOutsideUSA):
        resolve_location("Anchorage, AK", city_lookup)


def test_query_is_trimmed_and_case_insensitive(city_lookup):
    assert resolve_location("  chicago , il  ", city_lookup) == (41.8781, -87.6298)
