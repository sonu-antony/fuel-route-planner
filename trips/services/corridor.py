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


def find_corridor_stops(
    route_coordinates: list[Point], sample_every_miles: float, corridor_miles: float
) -> list[CorridorStop]:
    resampled = resample(route_coordinates, sample_every_miles)
    sample_points = [(point.latitude, point.longitude) for point in resampled]

    hits = get_index().stations_near(sample_points, radius_miles=corridor_miles)
    if not hits:
        return []

    stations = Station.objects.in_bulk(station_id for station_id, _ in hits)
    stops = [
        CorridorStop(
            mile_marker=resampled[point_index].mile_marker,
            price_per_gallon=stations[station_id].price_per_gallon,
            station=stations[station_id],
        )
        for station_id, point_index in hits
    ]

    start_point = route_coordinates[0]
    nearest_to_start = min(
        stops,
        key=lambda stop: haversine_miles(
            start_point, (stop.station.latitude, stop.station.longitude)
        ),
    )
    stops = [
        CorridorStop(mile_marker=0.0, price_per_gallon=stop.price_per_gallon, station=stop.station)
        if stop is nearest_to_start
        else stop
        for stop in stops
    ]

    stops.sort(key=lambda stop: stop.mile_marker)
    return stops
