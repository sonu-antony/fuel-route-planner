import math

import pytest
from django.core.cache import cache

from stations.models import Station
from stations.services.city_lookup import CityLookup
from stations.services.spatial_index import EARTH_RADIUS_MILES, reset_index
from trips.exceptions import SameStartAndFinish, UnreachableRoute
from trips.models import TripPlan
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
        latitude=miles_east(START, 1)[0],
        longitude=miles_east(START, 1)[1],
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
        latitude=miles_east(START, 1)[0],
        longitude=miles_east(START, 1)[1],
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
        latitude=miles_east(START, 1)[0],
        longitude=miles_east(START, 1)[1],
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


@pytest.mark.django_db
def test_queries_differing_only_in_comma_spacing_share_a_cache_entry():
    finish = miles_north(START, 50)
    Station.objects.create(
        opis_id=1,
        name="MIDWAY FUEL",
        address="I-1",
        city="Somewhere",
        state="KS",
        rack_id=1,
        price_per_gallon="3.199",
        latitude=miles_east(START, 1)[0],
        longitude=miles_east(START, 1)[1],
        geocode_source=Station.GeocodeSource.CITY_CENTROID,
    )
    route = Route(coordinates=[START, finish], distance_miles=50.0, duration_seconds=3000)
    routing_client = FakeRoutingClient(route)
    shared = {
        "start_fuel_gallons": 0.0,
        "routing_client": routing_client,
        "city_lookup": CityLookup({}),
        "config": make_config(),
    }

    plan_trip(start_query="39.0,-98.0", finish_query=f"{finish[0]},{finish[1]}", **shared)
    second = plan_trip(
        start_query="39.0 , -98.0", finish_query=f"{finish[0]}, {finish[1]}", **shared
    )

    assert routing_client.call_count == 1
    assert second.cached is True


@pytest.mark.django_db
def test_the_configured_cost_per_stop_reaches_the_fuel_planner():
    finish = miles_north(START, 50)
    for opis_id, point, price in (
        (1, miles_east(START, 1), "3.199"),
        (2, miles_north(START, 4), "3.189"),
    ):
        Station.objects.create(
            opis_id=opis_id,
            name=f"STATION {opis_id}",
            address="I-1",
            city="Somewhere",
            state="KS",
            rack_id=1,
            price_per_gallon=price,
            latitude=point[0],
            longitude=point[1],
            geocode_source=Station.GeocodeSource.CITY_CENTROID,
        )
    route = Route(coordinates=[START, finish], distance_miles=50.0, duration_seconds=3000)

    result = plan_trip(
        start_query="39.0,-98.0",
        finish_query=f"{finish[0]},{finish[1]}",
        start_fuel_gallons=0.0,
        routing_client=FakeRoutingClient(route),
        city_lookup=CityLookup({}),
        config=make_config(cost_per_stop=5.0),
    )

    assert len(result.trip.stops) == 1


def make_midway_station(opis_id=1):
    return Station.objects.create(
        opis_id=opis_id,
        name="MIDWAY FUEL",
        address="I-1",
        city="Somewhere",
        state="KS",
        rack_id=1,
        price_per_gallon="3.199",
        latitude=miles_east(START, 1)[0],
        longitude=miles_east(START, 1)[1],
        geocode_source=Station.GeocodeSource.CITY_CENTROID,
    )


def plan_short_trip(routing_client, start_query="39.0,-98.0"):
    finish = miles_north(START, 50)
    return plan_trip(
        start_query=start_query,
        finish_query=f"{finish[0]},{finish[1]}",
        start_fuel_gallons=0.0,
        routing_client=routing_client,
        city_lookup=CityLookup({}),
        config=make_config(),
    )


def short_route():
    finish = miles_north(START, 50)
    return Route(coordinates=[START, finish], distance_miles=50.0, duration_seconds=3000)


@pytest.mark.django_db
def test_stops_carry_the_opis_station_id_from_the_price_file():
    make_midway_station(opis_id=4242)

    result = plan_short_trip(FakeRoutingClient(short_route()))

    assert result.trip.stops[0]["station_id"] == 4242


@pytest.mark.django_db
def test_start_and_finish_that_resolve_to_the_same_point_raise_same_start_and_finish():
    routing_client = FakeRoutingClient(short_route())

    with pytest.raises(SameStartAndFinish):
        plan_trip(
            start_query="39,-98",
            finish_query="39.0,-98.0",
            start_fuel_gallons=0.0,
            routing_client=routing_client,
            city_lookup=CityLookup({}),
            config=make_config(),
        )

    assert routing_client.call_count == 0


@pytest.mark.django_db
def test_a_cached_trip_that_was_deleted_is_planned_again():
    make_midway_station()
    routing_client = FakeRoutingClient(short_route())
    first = plan_short_trip(routing_client)
    TripPlan.objects.filter(id=first.trip.id).delete()

    second = plan_short_trip(routing_client)

    assert routing_client.call_count == 2
    assert second.cached is False
    assert TripPlan.objects.filter(id=second.trip.id).exists()


@pytest.mark.django_db
def test_an_empty_tank_trip_begins_at_a_station_near_the_start_without_charging_the_approach():
    near_start = miles_east(START, 8)
    Station.objects.create(
        opis_id=8,
        name="EIGHT MILES OUT",
        address="I-1",
        city="Somewhere",
        state="KS",
        rack_id=1,
        price_per_gallon="3.000",
        latitude=near_start[0],
        longitude=near_start[1],
        geocode_source=Station.GeocodeSource.CITY_CENTROID,
    )

    result = plan_short_trip(FakeRoutingClient(short_route()))

    [stop] = result.trip.stops
    assert stop["station_id"] == 8
    assert stop["mile_marker"] == 0.0
    assert stop["off_route_miles"] == 0.0
    assert stop["gallons"] == pytest.approx(5.0)


@pytest.mark.django_db
def test_the_configured_fuel_reserve_reaches_the_fuel_planner():
    make_midway_station()

    result = plan_trip(
        start_query="39.0,-98.0",
        finish_query=f"{miles_north(START, 50)[0]},{miles_north(START, 50)[1]}",
        start_fuel_gallons=0.0,
        routing_client=FakeRoutingClient(short_route()),
        city_lookup=CityLookup({}),
        config=make_config(fuel_reserve_gallons=5.0),
    )

    [stop] = result.trip.stops
    assert stop["gallons"] == pytest.approx(10.0)


@pytest.mark.django_db
def test_a_different_planning_config_does_not_reuse_a_cached_plan():
    make_midway_station()
    routing_client = FakeRoutingClient(short_route())
    finish = miles_north(START, 50)
    shared = {
        "start_query": "39.0,-98.0",
        "finish_query": f"{finish[0]},{finish[1]}",
        "start_fuel_gallons": 0.0,
        "routing_client": routing_client,
        "city_lookup": CityLookup({}),
    }

    plan_trip(config=make_config(), **shared)
    second = plan_trip(config=make_config(fuel_reserve_gallons=5.0), **shared)

    assert routing_client.call_count == 2
    assert second.cached is False


@pytest.mark.django_db
def test_the_route_geojson_draws_a_detour_line_to_each_off_route_stop():
    make_midway_station()
    off_route = miles_east(miles_north(START, 20), 3)
    Station.objects.create(
        opis_id=2,
        name="CHEAP BUT OFF ROUTE",
        address="I-1",
        city="Somewhere",
        state="KS",
        rack_id=1,
        price_per_gallon="2.500",
        latitude=off_route[0],
        longitude=off_route[1],
        geocode_source=Station.GeocodeSource.CITY_CENTROID,
    )

    result = plan_short_trip(FakeRoutingClient(short_route()))

    detours = [
        feature
        for feature in result.trip.route_geojson["features"]
        if feature["properties"]["kind"] == "detour"
    ]
    [detour] = detours
    station_end, route_end = detour["geometry"]["coordinates"]
    assert station_end == pytest.approx([off_route[1], off_route[0]])
    route_point = miles_north(START, 20)
    assert route_end == pytest.approx([route_point[1], route_point[0]], abs=1e-6)
    assert detour["properties"]["miles"] == pytest.approx(3.0, abs=0.05)
