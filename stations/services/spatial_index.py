import math
from collections.abc import Iterable

import numpy as np
from scipy.spatial import cKDTree

EARTH_RADIUS_MILES = 3958.8


def _to_unit_vector(latitude: float, longitude: float) -> tuple[float, float, float]:
    lat_radians = math.radians(latitude)
    lng_radians = math.radians(longitude)
    return (
        math.cos(lat_radians) * math.cos(lng_radians),
        math.cos(lat_radians) * math.sin(lng_radians),
        math.sin(lat_radians),
    )


def _miles_to_chord_distance(radius_miles: float) -> float:
    central_angle = radius_miles / EARTH_RADIUS_MILES
    return 2 * math.sin(central_angle / 2)


class SpatialIndex:
    def __init__(self, station_ids: list[int], vectors: np.ndarray):
        self._station_ids = station_ids
        self._vectors = vectors
        self._tree = cKDTree(vectors) if len(station_ids) else None

    @classmethod
    def from_records(cls, records: Iterable[tuple[int, float, float]]) -> "SpatialIndex":
        station_ids = []
        vectors = []
        for station_id, latitude, longitude in records:
            station_ids.append(station_id)
            vectors.append(_to_unit_vector(latitude, longitude))
        return cls(station_ids, np.array(vectors) if vectors else np.empty((0, 3)))

    def stations_near(
        self, points: list[tuple[float, float]], radius_miles: float
    ) -> list[tuple[int, int]]:
        if self._tree is None or not points:
            return []

        chord_radius = _miles_to_chord_distance(radius_miles)
        point_vectors = np.array([_to_unit_vector(lat, lng) for lat, lng in points])
        candidates_per_point = self._tree.query_ball_point(point_vectors, chord_radius)

        best_distance: dict[int, float] = {}
        best_point_index: dict[int, int] = {}
        for point_index, station_indices in enumerate(candidates_per_point):
            point_vector = point_vectors[point_index]
            for station_index in station_indices:
                distance = np.linalg.norm(point_vector - self._vectors[station_index])
                if station_index not in best_distance or distance < best_distance[station_index]:
                    best_distance[station_index] = distance
                    best_point_index[station_index] = point_index

        return [
            (self._station_ids[station_index], point_index)
            for station_index, point_index in best_point_index.items()
        ]


_cached_index: SpatialIndex | None = None


def get_index() -> SpatialIndex:
    global _cached_index
    if _cached_index is None:
        from stations.models import Station

        records = Station.objects.values_list("id", "latitude", "longitude")
        _cached_index = SpatialIndex.from_records(records)
    return _cached_index


def reset_index() -> None:
    global _cached_index
    _cached_index = None
