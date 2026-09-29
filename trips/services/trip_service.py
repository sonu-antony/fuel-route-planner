import hashlib
import time
import uuid
from dataclasses import dataclass
from decimal import Decimal

from django.core.cache import cache

from stations.services.city_lookup import CityLookup
from trips.exceptions import SameStartAndFinish
from trips.models import TripPlan
from trips.services.corridor import find_corridor_stops
from trips.services.fuel_planner import FuelCandidate, FuelStop, plan_fuel
from trips.services.geometry import Point
from trips.services.location_resolver import resolve_location
from trips.services.routing_client import RoutingClient


@dataclass(frozen=True)
class TripPlanningConfig:
    tank_capacity_gallons: float
    miles_per_gallon: float
    corridor_miles: float
    sample_every_miles: float
    cache_seconds: int
    cost_per_stop: float = 0.0


@dataclass(frozen=True)
class TripServiceResult:
    trip: TripPlan
    routing_calls: int
    elapsed_ms: float
    cached: bool


def _normalize_query(query: str) -> str:
    return ",".join(" ".join(part.lower().split()) for part in query.split(","))


def _cache_key(start_query: str, finish_query: str, start_fuel_gallons: float) -> str:
    normalized_start = _normalize_query(start_query)
    normalized_finish = _normalize_query(finish_query)
    raw_key = f"{normalized_start}|{normalized_finish}|{start_fuel_gallons:.2f}"
    digest = hashlib.sha256(raw_key.encode()).hexdigest()
    return f"trip-plan:{digest}"


def _serialize_stops(fuel_stops: list[FuelStop]) -> list[dict]:
    serialized = []
    for stop in fuel_stops:
        station = stop.station
        serialized.append(
            {
                "station_id": station.opis_id,
                "name": station.name,
                "address": station.address,
                "city": station.city,
                "state": station.state,
                "latitude": station.latitude,
                "longitude": station.longitude,
                "mile_marker": stop.mile_marker,
                "off_route_miles": stop.offset_miles,
                "price_per_gallon": str(stop.price_per_gallon),
                "gallons": stop.gallons,
                "cost": str(stop.cost),
            }
        )
    return serialized


def _build_route_geojson(coordinates: list[Point], serialized_stops: list[dict]) -> dict:
    features = [
        {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[lng, lat] for lat, lng in coordinates],
            },
            "properties": {"kind": "route"},
        }
    ]
    for stop in serialized_stops:
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [stop["longitude"], stop["latitude"]],
                },
                "properties": {
                    "kind": "stop",
                    "name": stop["name"],
                    "price_per_gallon": stop["price_per_gallon"],
                    "gallons": stop["gallons"],
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def plan_trip(
    start_query: str,
    finish_query: str,
    start_fuel_gallons: float,
    routing_client: RoutingClient,
    city_lookup: CityLookup,
    config: TripPlanningConfig,
) -> TripServiceResult:
    start_time = time.monotonic()
    key = _cache_key(start_query, finish_query, start_fuel_gallons)

    cached_id = cache.get(key)
    cached_trip = TripPlan.objects.filter(id=cached_id).first() if cached_id else None
    if cached_trip is not None:
        elapsed_ms = (time.monotonic() - start_time) * 1000
        return TripServiceResult(
            trip=cached_trip, routing_calls=0, elapsed_ms=elapsed_ms, cached=True
        )

    start_coordinates = resolve_location(start_query, city_lookup)
    finish_coordinates = resolve_location(finish_query, city_lookup)
    if start_coordinates == finish_coordinates:
        raise SameStartAndFinish("start and finish resolve to the same location")

    route = routing_client.get_route(start_coordinates, finish_coordinates)

    corridor_stops = find_corridor_stops(
        route.coordinates,
        sample_every_miles=config.sample_every_miles,
        corridor_miles=config.corridor_miles,
    )
    candidates = [
        FuelCandidate(
            station=stop.station,
            mile_marker=stop.mile_marker,
            price_per_gallon=stop.price_per_gallon,
            offset_miles=stop.offset_miles,
        )
        for stop in corridor_stops
    ]

    fuel_plan = plan_fuel(
        candidates,
        total_distance_miles=route.distance_miles,
        tank_capacity_gallons=config.tank_capacity_gallons,
        miles_per_gallon=config.miles_per_gallon,
        start_fuel_gallons=start_fuel_gallons,
        cost_per_stop=config.cost_per_stop,
    )

    serialized_stops = _serialize_stops(fuel_plan.stops)
    route_geojson = _build_route_geojson(route.coordinates, serialized_stops)

    trip = TripPlan.objects.create(
        id=uuid.uuid4(),
        start_query=start_query,
        finish_query=finish_query,
        start_lat=start_coordinates[0],
        start_lng=start_coordinates[1],
        finish_lat=finish_coordinates[0],
        finish_lng=finish_coordinates[1],
        distance_miles=route.distance_miles,
        total_gallons=Decimal(str(round(fuel_plan.total_gallons, 6))),
        total_cost=fuel_plan.total_cost,
        route_geojson=route_geojson,
        stops=serialized_stops,
    )

    cache.set(key, str(trip.id), timeout=config.cache_seconds)

    elapsed_ms = (time.monotonic() - start_time) * 1000
    return TripServiceResult(trip=trip, routing_calls=1, elapsed_ms=elapsed_ms, cached=False)
