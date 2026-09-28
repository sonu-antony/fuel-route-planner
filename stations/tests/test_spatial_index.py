import math

import pytest

from stations.models import Station
from stations.services.spatial_index import EARTH_RADIUS_MILES, SpatialIndex, get_index, reset_index

ORIGIN = (0.0, 0.0)


def point_due_north(origin, distance_miles):
    delta_lat_degrees = math.degrees(distance_miles / EARTH_RADIUS_MILES)
    return (origin[0] + delta_lat_degrees, origin[1])


def test_a_station_one_mile_from_a_point_is_returned_at_a_five_mile_radius():
    station_point = point_due_north(ORIGIN, 1)
    index = SpatialIndex.from_records([(1, *station_point)])

    results = index.stations_near([ORIGIN], radius_miles=5)

    assert [station_id for station_id, _ in results] == [1]


def test_a_station_twenty_miles_away_is_not_returned_at_a_ten_mile_radius():
    station_point = point_due_north(ORIGIN, 20)
    index = SpatialIndex.from_records([(1, *station_point)])

    results = index.stations_near([ORIGIN], radius_miles=10)

    assert results == []


def test_each_station_is_returned_once_even_when_near_several_points():
    station_point = point_due_north(ORIGIN, 1)
    index = SpatialIndex.from_records([(1, *station_point)])
    points = [ORIGIN, point_due_north(ORIGIN, 2), point_due_north(ORIGIN, 0.5)]

    results = index.stations_near(points, radius_miles=5)

    assert len(results) == 1


def test_each_station_reports_the_nearest_point_index():
    station_point = point_due_north(ORIGIN, 10)
    index = SpatialIndex.from_records([(1, *station_point)])
    points = [ORIGIN, point_due_north(ORIGIN, 9), point_due_north(ORIGIN, 30)]

    [(station_id, nearest_point_index)] = index.stations_near(points, radius_miles=20)

    assert station_id == 1
    assert nearest_point_index == 1


def test_an_empty_station_table_returns_an_empty_result_without_errors():
    index = SpatialIndex.from_records([])

    results = index.stations_near([ORIGIN], radius_miles=10)

    assert results == []


@pytest.mark.django_db
def test_the_spatial_index_is_built_once_across_two_requests(django_assert_num_queries):
    Station.objects.create(
        opis_id=1,
        name="STATION 1",
        address="I-1",
        city="Somewhere",
        state="IL",
        rack_id=1,
        price_per_gallon="3.000",
        latitude=0.0,
        longitude=0.0,
        geocode_source=Station.GeocodeSource.CITY_CENTROID,
    )
    reset_index()

    with django_assert_num_queries(1):
        get_index()
        get_index()
