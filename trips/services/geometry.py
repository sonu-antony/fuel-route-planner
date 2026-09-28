import math
from dataclasses import dataclass

EARTH_RADIUS_MILES = 3958.8

Point = tuple[float, float]


@dataclass(frozen=True)
class ResampledPoint:
    latitude: float
    longitude: float
    mile_marker: float


def haversine_miles(a: Point, b: Point) -> float:
    lat1, lng1 = math.radians(a[0]), math.radians(a[1])
    lat2, lng2 = math.radians(b[0]), math.radians(b[1])
    delta_lat = lat2 - lat1
    delta_lng = lng2 - lng1
    h = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lng / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(h))


def cumulative_miles(coordinates: list[Point]) -> list[float]:
    markers = [0.0]
    for previous, current in zip(coordinates, coordinates[1:], strict=False):
        markers.append(markers[-1] + haversine_miles(previous, current))
    return markers


def resample(coordinates: list[Point], every_miles: float) -> list[ResampledPoint]:
    markers = cumulative_miles(coordinates)
    total = markers[-1]

    target_markers = []
    marker = 0.0
    while marker < total:
        target_markers.append(marker)
        marker += every_miles
    target_markers.append(total)

    points = []
    segment_index = 0
    for target in target_markers:
        while segment_index < len(markers) - 2 and markers[segment_index + 1] < target:
            segment_index += 1
        segment_start, segment_end = markers[segment_index], markers[segment_index + 1]
        segment_length = segment_end - segment_start
        fraction = 0.0 if segment_length == 0 else (target - segment_start) / segment_length
        start_point, end_point = coordinates[segment_index], coordinates[segment_index + 1]
        latitude = start_point[0] + fraction * (end_point[0] - start_point[0])
        longitude = start_point[1] + fraction * (end_point[1] - start_point[1])
        points.append(ResampledPoint(latitude=latitude, longitude=longitude, mile_marker=target))

    return points
