import math

import pytest

from stations.models import Station
from stations.services.spatial_index import EARTH_RADIUS_MILES, reset_index
from trips.services.corridor import find_corridor_stops

ORIGIN = (0.0, 0.0)


@pytest.fixture(autouse=True)
def _reset_spatial_index():
    reset_index()
    yield
    reset_index()


def point_due_north(origin, distance_miles):
    delta_lat_degrees = math.degrees(distance_miles / EARTH_RADIUS_MILES)
    return (origin[0] + delta_lat_degrees, origin[1])


def point_offset_east(point, distance_miles):
    lat_radians = math.radians(point[0])
    delta_lng_degrees = math.degrees(distance_miles / (EARTH_RADIUS_MILES * math.cos(lat_radians)))
    return (point[0], point[1] + delta_lng_degrees)


def make_station(opis_id, latitude, longitude, price="3.000"):
    return Station.objects.create(
        opis_id=opis_id,
        name=f"STATION {opis_id}",
        address="I-1",
        city="Somewhere",
        state="IL",
        rack_id=1,
        price_per_gallon=price,
        latitude=latitude,
        longitude=longitude,
        geocode_source=Station.GeocodeSource.CITY_CENTROID,
    )


@pytest.mark.django_db
def test_stations_inside_the_corridor_are_returned_with_the_correct_mile_marker():
    near_start = point_offset_east(ORIGIN, 0.1)
    near_mile_10 = point_offset_east(point_due_north(ORIGIN, 10), 0.1)
    make_station(1, *near_start)
    make_station(2, *near_mile_10)
    route = [ORIGIN, point_due_north(ORIGIN, 100)]

    stops = find_corridor_stops(route, sample_every_miles=2, corridor_miles=5)

    stop = next(stop for stop in stops if stop.station.opis_id == 2)
    assert stop.mile_marker == pytest.approx(10, abs=0.01)


@pytest.mark.django_db
def test_stations_outside_the_corridor_are_excluded():
    far_from_route = point_offset_east(point_due_north(ORIGIN, 50), 20)
    make_station(1, *far_from_route)
    route = [ORIGIN, point_due_north(ORIGIN, 100)]

    stops = find_corridor_stops(route, sample_every_miles=2, corridor_miles=5)

    assert stops == []


@pytest.mark.django_db
def test_the_result_is_sorted_by_mile_marker():
    near_mile_30 = point_offset_east(point_due_north(ORIGIN, 30), 0.1)
    near_mile_10 = point_offset_east(point_due_north(ORIGIN, 10), 0.1)
    make_station(1, *near_mile_30)
    make_station(2, *near_mile_10)
    route = [ORIGIN, point_due_north(ORIGIN, 100)]

    stops = find_corridor_stops(route, sample_every_miles=2, corridor_miles=5)

    assert [stop.mile_marker for stop in stops] == sorted(stop.mile_marker for stop in stops)


@pytest.mark.django_db
def test_a_nearest_station_beyond_the_corridor_width_keeps_its_real_mile_marker():
    near_mile_50 = point_offset_east(point_due_north(ORIGIN, 50), 0.1)
    make_station(1, *near_mile_50)
    route = [ORIGIN, point_due_north(ORIGIN, 100)]

    [stop] = find_corridor_stops(route, sample_every_miles=2, corridor_miles=5)

    assert stop.mile_marker == pytest.approx(50, abs=0.01)


@pytest.mark.django_db
def test_the_station_nearest_the_start_becomes_the_start_node_at_mile_zero():
    near_mile_10 = point_offset_east(point_due_north(ORIGIN, 10), 0.1)
    near_mile_4 = point_offset_east(point_due_north(ORIGIN, 4), 0.1)
    make_station(1, *near_mile_10)
    make_station(2, *near_mile_4)
    route = [ORIGIN, point_due_north(ORIGIN, 100)]

    stops = find_corridor_stops(route, sample_every_miles=2, corridor_miles=5)

    assert stops[0].station.opis_id == 2
    assert stops[0].mile_marker == 0.0


@pytest.mark.django_db
def test_each_stop_reports_how_far_it_is_off_the_route():
    make_station(1, *point_offset_east(ORIGIN, 0.1))
    make_station(2, *point_offset_east(point_due_north(ORIGIN, 20), 3))
    route = [ORIGIN, point_due_north(ORIGIN, 100)]

    stops = find_corridor_stops(route, sample_every_miles=2, corridor_miles=5)

    stop = next(stop for stop in stops if stop.station.opis_id == 2)
    assert stop.offset_miles == pytest.approx(3.0, abs=0.05)


@pytest.mark.django_db
@pytest.mark.parametrize("prices", [("3.500", "3.200"), ("3.200", "3.500")])
def test_among_stations_sharing_the_nearest_location_the_cheapest_becomes_the_start(prices):
    shared_location = point_offset_east(point_due_north(ORIGIN, 4), 0.1)
    make_station(1, *shared_location, price=prices[0])
    make_station(2, *shared_location, price=prices[1])
    route = [ORIGIN, point_due_north(ORIGIN, 100)]

    stops = find_corridor_stops(route, sample_every_miles=2, corridor_miles=5)

    start = next(stop for stop in stops if stop.mile_marker == 0.0)
    assert str(start.price_per_gallon) == "3.200"


@pytest.mark.django_db
def test_the_start_station_counts_as_on_the_route():
    make_station(1, *point_offset_east(point_due_north(ORIGIN, 4), 0.1))
    route = [ORIGIN, point_due_north(ORIGIN, 100)]

    [stop] = find_corridor_stops(route, sample_every_miles=2, corridor_miles=5)

    assert stop.mile_marker == 0.0
    assert stop.offset_miles == 0.0
