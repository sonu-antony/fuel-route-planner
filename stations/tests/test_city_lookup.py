from pathlib import Path

import pytest

from stations.services.city_lookup import load_city_lookup

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_cities.csv"


@pytest.fixture
def lookup():
    return load_city_lookup(FIXTURE_PATH)


def test_finds_coordinates_for_an_exact_city_and_state(lookup):
    assert lookup.find("Chicago", "IL") == (41.8781, -87.6298)


def test_matching_ignores_case_and_extra_whitespace(lookup):
    assert lookup.find("  chicago  ", " il ") == lookup.find("Chicago", "IL")


def test_st_louis_and_saint_louis_resolve_to_the_same_entry(lookup):
    assert lookup.find("St. Louis", "MO") == lookup.find("Saint Louis", "MO")


def test_returns_none_for_an_unknown_city(lookup):
    assert lookup.find("Nowhereville", "ZZ") is None


def test_the_same_city_name_in_two_states_resolves_to_the_correct_state(lookup):
    missouri = lookup.find("Kansas City", "MO")
    kansas = lookup.find("Kansas City", "KS")

    assert missouri == (39.0997, -94.5786)
    assert kansas == (39.1147, -94.6275)
    assert missouri != kansas
