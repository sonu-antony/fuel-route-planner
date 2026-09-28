from dataclasses import dataclass

import requests
from requests.exceptions import ConnectionError, Timeout

from trips.exceptions import RouteNotFound, RoutingUnavailable

DIRECTIONS_URL_TEMPLATE = "https://api.openrouteservice.org/v2/directions/{profile}/geojson"
METERS_PER_MILE = 1609.344
HGV_LENGTH_EXCEEDED_ERROR_CODE = 2010
FALLBACK_PROFILE = "driving-car"


@dataclass(frozen=True)
class Route:
    coordinates: list[tuple[float, float]]
    distance_miles: float
    duration_seconds: float


def _hgv_length_exceeded(response: requests.Response) -> bool:
    try:
        payload = response.json()
    except ValueError:
        return False
    error = payload.get("error")
    if not isinstance(error, dict):
        return False
    return error.get("code") == HGV_LENGTH_EXCEEDED_ERROR_CODE


class RoutingClient:
    def __init__(self, api_key: str, profile: str, timeout_seconds: float):
        self._api_key = api_key
        self._profile = profile
        self._timeout_seconds = timeout_seconds

    def get_route(self, start: tuple[float, float], finish: tuple[float, float]) -> Route:
        return self._request(self._profile, start, finish, allow_fallback=True)

    def _request(
        self,
        profile: str,
        start: tuple[float, float],
        finish: tuple[float, float],
        allow_fallback: bool,
    ) -> Route:
        start_lat, start_lng = start
        finish_lat, finish_lng = finish
        url = DIRECTIONS_URL_TEMPLATE.format(profile=profile)
        body = {"coordinates": [[start_lng, start_lat], [finish_lng, finish_lat]]}
        headers = {"Authorization": self._api_key}

        try:
            response = requests.post(url, json=body, headers=headers, timeout=self._timeout_seconds)
        except (Timeout, ConnectionError) as error:
            raise RoutingUnavailable(str(error)) from error

        if response.status_code >= 400:
            if allow_fallback and profile == "driving-hgv" and _hgv_length_exceeded(response):
                return self._request(FALLBACK_PROFILE, start, finish, allow_fallback=False)
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
