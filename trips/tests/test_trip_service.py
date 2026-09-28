import math

import pytest
from django.core.cache import cache

from stations.models import Station
from stations.services.city_lookup import CityLookup
from stations.services.spatial_index import EARTH_RADIUS_MILES, reset_index
from trips.exceptions import UnreachableRoute
from trips.services.routing_client import Route
from trips.services.trip_service import TripPlanningConfig, plan_trip

START = (39.0, -98.0)


def miles_north(point, distance_miles):
    delta_lat = math.degrees(distance_miles / EARTH_RADIUS_MILES)
    return (point[0] + delta_lat, point[1])


def miles_east(point, distance_miles):
    lat_radians = math.radians(point[0])
    delta_lng = math.degrees(distance_miles / (EARTH_RADIUS_MILES * math.cos(lat_radians)))
    return (point[0], point[1] + delta_lng)


class FakeRoutingClient:
    def __init__(self, route):
        self.route = route
        self.call_count = 0

    def get_route(self, start, finish):
        self.call_count += 1
        return self.route


def make_config(**overrides):
    defaults = {
        "tank_capacity_gallons": 50.0,
        "miles_per_gallon": 10.0,
        "corridor_miles": 10.0,
        "sample_every_miles": 2.0,
        "cache_seconds": 3600,
    }
    defaults.update(overrides)
    return TripPlanningConfig(**defaults)


@pytest.fixture(autouse=True)
def _reset_state():
    reset_index()
    cache.clear()
    yield
    reset_index()
    cache.clear()


@pytest.mark.django_db
def test_a_new_request_calls_the_routing_client_once_and_saves_a_trip_plan():
    finish = miles_north(START, 50)
    Station.objects.create(
        opis_id=1,
        name="MIDWAY FUEL",
        address="I-1",
        city="Somewhere",
        state="KS",
        rack_id=1,
        price_per_gallon="3.199",
        latitude=miles_east(miles_north(START, 25), 0.1)[0],
        longitude=miles_east(miles_north(START, 25), 0.1)[1],
        geocode_source=Station.GeocodeSource.CITY_CENTROID,
    )
    route = Route(coordinates=[START, finish], distance_miles=50.0, duration_seconds=3000)
    routing_client = FakeRoutingClient(route)

    result = plan_trip(
        start_query="39.0,-98.0",
        finish_query=f"{finish[0]},{finish[1]}",
        start_fuel_gallons=0.0,
        routing_client=routing_client,
        city_lookup=CityLookup({}),
        config=make_config(),
    )

    assert routing_client.call_count == 1
    assert result.routing_calls == 1
    assert result.trip.pk is not None


@pytest.mark.django_db
def test_an_identical_second_request_calls_the_routing_client_zero_times():
    finish = miles_north(START, 50)
    Station.objects.create(
        opis_id=1,
        name="MIDWAY FUEL",
        address="I-1",
        city="Somewhere",
        state="KS",
        rack_id=1,
        price_per_gallon="3.199",
        latitude=miles_east(miles_north(START, 25), 0.1)[0],
        longitude=miles_east(miles_north(START, 25), 0.1)[1],
        geocode_source=Station.GeocodeSource.CITY_CENTROID,
    )
    route = Route(coordinates=[START, finish], distance_miles=50.0, duration_seconds=3000)
    routing_client = FakeRoutingClient(route)
    kwargs = {
        "start_query": "39.0,-98.0",
        "finish_query": f"{finish[0]},{finish[1]}",
        "start_fuel_gallons": 0.0,
        "routing_client": routing_client,
        "city_lookup": CityLookup({}),
        "config": make_config(),
    }

    first = plan_trip(**kwargs)
    second = plan_trip(**kwargs)

    assert routing_client.call_count == 1
    assert second.routing_calls == 0
    assert second.cached is True
    assert second.trip.id == first.trip.id


@pytest.mark.django_db
def test_the_returned_plan_contains_stops_totals_and_geojson():
    finish = miles_north(START, 50)
    Station.objects.create(
        opis_id=1,
        name="MIDWAY FUEL",
        address="I-1",
        city="Somewhere",
        state="KS",
        rack_id=1,
        price_per_gallon="3.199",
        latitude=miles_east(miles_north(START, 25), 0.1)[0],
        longitude=miles_east(miles_north(START, 25), 0.1)[1],
        geocode_source=Station.GeocodeSource.CITY_CENTROID,
    )
    route = Route(coordinates=[START, finish], distance_miles=50.0, duration_seconds=3000)
    routing_client = FakeRoutingClient(route)

    result = plan_trip(
        start_query="39.0,-98.0",
        finish_query=f"{finish[0]},{finish[1]}",
        start_fuel_gallons=0.0,
        routing_client=routing_client,
        city_lookup=CityLookup({}),
        config=make_config(),
    )

    assert len(result.trip.stops) == 1
    assert result.trip.total_gallons > 0
    assert result.trip.total_cost > 0
    assert result.trip.route_geojson["type"] == "FeatureCollection"


@pytest.mark.django_db
def test_an_unreachable_route_propagates_unreachable_route():
    finish = miles_north(START, 600)
    route = Route(coordinates=[START, finish], distance_miles=600.0, duration_seconds=60000)
    routing_client = FakeRoutingClient(route)

    with pytest.raises(UnreachableRoute):
        plan_trip(
            start_query="39.0,-98.0",
            finish_query=f"{finish[0]},{finish[1]}",
            start_fuel_gallons=0.0,
            routing_client=routing_client,
            city_lookup=CityLookup({}),
            config=make_config(),
        )
