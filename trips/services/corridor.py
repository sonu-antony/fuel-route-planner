from dataclasses import dataclass
from decimal import Decimal

from stations.models import Station
from stations.services.spatial_index import get_index
from trips.services.geometry import Point, haversine_miles, resample


@dataclass(frozen=True)
class CorridorStop:
    mile_marker: float
    price_per_gallon: Decimal
    station: Station
    offset_miles: float = 0.0


def find_corridor_stops(
    route_coordinates: list[Point], sample_every_miles: float, corridor_miles: float
) -> list[CorridorStop]:
    resampled = resample(route_coordinates, sample_every_miles)
    sample_points = [(point.latitude, point.longitude) for point in resampled]

    hits = get_index().stations_near(sample_points, radius_miles=corridor_miles)
    if not hits:
        return []

    stations = Station.objects.only(
        "opis_id", "name", "address", "city", "state", "latitude", "longitude", "price_per_gallon"
    ).in_bulk(station_id for station_id, _ in hits)
    stops = [
        CorridorStop(
            mile_marker=resampled[point_index].mile_marker,
            price_per_gallon=stations[station_id].price_per_gallon,
            station=stations[station_id],
            offset_miles=haversine_miles(
                sample_points[point_index],
                (stations[station_id].latitude, stations[station_id].longitude),
            ),
        )
        for station_id, point_index in hits
    ]

    start_point = route_coordinates[0]
    distance_to_start = {
        id(stop): haversine_miles(start_point, (stop.station.latitude, stop.station.longitude))
        for stop in stops
    }
    nearest_to_start = min(stops, key=lambda stop: distance_to_start[id(stop)])
    if distance_to_start[id(nearest_to_start)] <= corridor_miles:
        stops = [
            CorridorStop(
                mile_marker=0.0,
                price_per_gallon=stop.price_per_gallon,
                station=stop.station,
                offset_miles=0.0,
            )
            if stop is nearest_to_start
            else stop
            for stop in stops
        ]

    stops.sort(key=lambda stop: (stop.mile_marker, stop.offset_miles))
    return stops
