import math

import pytest

from trips.services.geometry import EARTH_RADIUS_MILES, cumulative_miles, haversine_miles, resample


def point_due_north(origin, distance_miles):
    delta_lat_degrees = math.degrees(distance_miles / EARTH_RADIUS_MILES)
    return (origin[0] + delta_lat_degrees, origin[1])


def test_one_degree_of_latitude_is_about_69_09_miles():
    distance = haversine_miles((0.0, 0.0), (1.0, 0.0))

    assert distance == pytest.approx(69.09, abs=0.1)


def test_the_distance_from_a_point_to_itself_is_zero():
    point = (41.8781, -87.6298)

    assert haversine_miles(point, point) == 0


def test_cumulative_miles_are_monotonic_and_end_at_the_total_length():
    coordinates = [(0.0, 0.0), point_due_north((0.0, 0.0), 10), point_due_north((0.0, 0.0), 30)]

    markers = cumulative_miles(coordinates)

    assert markers[0] == 0
    assert markers == sorted(markers)
    assert markers[-1] == pytest.approx(30, abs=0.01)


def test_resampling_a_100_mile_line_every_2_miles_gives_51_points():
    coordinates = [(0.0, 0.0), point_due_north((0.0, 0.0), 100)]

    points = resample(coordinates, every_miles=2)

    assert len(points) == 51
    assert points[0].mile_marker == 0
    assert points[-1].mile_marker == pytest.approx(100, abs=0.01)


def test_resampling_keeps_the_final_vertex_even_when_not_a_multiple_of_the_step():
    coordinates = [(0.0, 0.0), point_due_north((0.0, 0.0), 101)]

    points = resample(coordinates, every_miles=2)

    assert points[-2].mile_marker == pytest.approx(100, abs=0.01)
    assert points[-1].mile_marker == pytest.approx(101, abs=0.01)
