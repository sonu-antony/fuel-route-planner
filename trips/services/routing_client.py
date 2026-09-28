from dataclasses import dataclass

import requests
from requests.exceptions import ConnectionError, Timeout

from trips.exceptions import RouteNotFound, RoutingUnavailable

DIRECTIONS_URL_TEMPLATE = "https://api.openrouteservice.org/v2/directions/{profile}/geojson"
METERS_PER_MILE = 1609.344


@dataclass(frozen=True)
class Route:
    coordinates: list[tuple[float, float]]
    distance_miles: float
    duration_seconds: float


class RoutingClient:
    def __init__(self, api_key: str, profile: str, timeout_seconds: float):
        self._api_key = api_key
        self._profile = profile
        self._timeout_seconds = timeout_seconds

    def get_route(self, start: tuple[float, float], finish: tuple[float, float]) -> Route:
        start_lat, start_lng = start
        finish_lat, finish_lng = finish
        url = DIRECTIONS_URL_TEMPLATE.format(profile=self._profile)
        body = {"coordinates": [[start_lng, start_lat], [finish_lng, finish_lat]]}
        headers = {"Authorization": self._api_key}

        try:
            response = requests.post(url, json=body, headers=headers, timeout=self._timeout_seconds)
        except (Timeout, ConnectionError) as error:
            raise RoutingUnavailable(str(error)) from error

        if response.status_code >= 400:
            raise RouteNotFound(f"routing api returned {response.status_code}")

        payload = response.json()
        features = payload.get("features", [])
        if not features:
            raise RouteNotFound("no route features returned")

        feature = features[0]
        raw_coordinates = feature["geometry"]["coordinates"]
        coordinates = [(lat, lng) for lng, lat in raw_coordinates]
        summary = feature["properties"]["summary"]
        distance_miles = summary["distance"] / METERS_PER_MILE
        duration_seconds = summary["duration"]

        return Route(
            coordinates=coordinates,
            distance_miles=distance_miles,
            duration_seconds=duration_seconds,
        )
