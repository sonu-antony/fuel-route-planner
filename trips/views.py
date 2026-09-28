from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.shortcuts import get_object_or_404, render
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from stations.services.city_lookup import CityLookup, load_city_lookup
from trips.exceptions import (
    LocationNotFound,
    LocationOutsideUSA,
    RouteNotFound,
    RoutingUnavailable,
    UnreachableRoute,
)
from trips.models import TripPlan
from trips.serializers import TripPlanRequestSerializer
from trips.services.routing_client import RoutingClient
from trips.services.trip_service import TripPlanningConfig, plan_trip

_city_lookup_cache: CityLookup | None = None


def _get_city_lookup() -> CityLookup:
    global _city_lookup_cache
    if _city_lookup_cache is None:
        _city_lookup_cache = load_city_lookup(settings.BASE_DIR / "data" / "us_cities.csv")
    return _city_lookup_cache


def _round_money(value) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _serialize_trip(
    trip: TripPlan, request: Request, routing_calls: int, cached: bool, elapsed_ms: float
) -> dict:
    fuel_stops = [
        {
            "station_id": stop["station_id"],
            "name": stop["name"],
            "address": stop["address"],
            "city": stop["city"],
            "state": stop["state"],
            "mile_marker": stop["mile_marker"],
            "price_per_gallon": float(stop["price_per_gallon"]),
            "gallons": round(stop["gallons"], 3),
            "cost": _round_money(stop["cost"]),
        }
        for stop in trip.stops
    ]
    return {
        "id": str(trip.id),
        "start": {"query": trip.start_query, "lat": trip.start_lat, "lng": trip.start_lng},
        "finish": {"query": trip.finish_query, "lat": trip.finish_lat, "lng": trip.finish_lng},
        "distance_miles": trip.distance_miles,
        "total_gallons": round(float(trip.total_gallons), 3),
        "total_cost": _round_money(trip.total_cost),
        "fuel_stops": fuel_stops,
        "route": trip.route_geojson,
        "map_url": request.build_absolute_uri(f"/trips/{trip.id}/map/"),
        "meta": {
            "routing_calls": routing_calls,
            "cached": cached,
            "elapsed_ms": round(elapsed_ms, 1),
        },
    }


class TripPlanView(APIView):
    def post(self, request: Request) -> Response:
        serializer = TripPlanRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": "validation_error", "detail": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = serializer.validated_data

        routing_client = RoutingClient(
            api_key=settings.ORS_API_KEY,
            profile=settings.ORS_PROFILE,
            timeout_seconds=settings.ROUTING_TIMEOUT_SECONDS,
        )
        config = TripPlanningConfig(
            tank_capacity_gallons=settings.VEHICLE_RANGE_MILES / settings.VEHICLE_MILES_PER_GALLON,
            miles_per_gallon=settings.VEHICLE_MILES_PER_GALLON,
            corridor_miles=settings.CORRIDOR_MILES,
            sample_every_miles=settings.ROUTE_SAMPLE_MILES,
            cache_seconds=settings.TRIP_CACHE_SECONDS,
        )

        try:
            result = plan_trip(
                start_query=data["start"],
                finish_query=data["finish"],
                start_fuel_gallons=float(data["start_fuel_gallons"]),
                routing_client=routing_client,
                city_lookup=_get_city_lookup(),
                config=config,
            )
        except LocationNotFound:
            return Response(
                {
                    "error": "location_not_found",
                    "detail": "start or finish location was not found",
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        except LocationOutsideUSA:
            return Response(
                {
                    "error": "location_outside_usa",
                    "detail": "location is outside the continental usa",
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        except UnreachableRoute:
            return Response(
                {
                    "error": "unreachable_route",
                    "detail": "no fuel stop is reachable along the route",
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        except (RoutingUnavailable, RouteNotFound):
            return Response(
                {"error": "routing_unavailable", "detail": "the routing service is unavailable"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        payload = _serialize_trip(
            result.trip, request, result.routing_calls, result.cached, result.elapsed_ms
        )
        return Response(payload, status=status.HTTP_200_OK)


@api_view(["GET"])
def health(request):
    return Response({"status": "ok"})


def trip_map(request, trip_id):
    trip = get_object_or_404(TripPlan, pk=trip_id)
    return render(request, "trips/map.html", {"route_geojson": trip.route_geojson})
