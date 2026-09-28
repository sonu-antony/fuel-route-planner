import pytest
import responses
from requests.exceptions import ConnectionError, Timeout

from trips.exceptions import RouteNotFound, RoutingUnavailable
from trips.services.routing_client import RoutingClient

DIRECTIONS_URL = "https://api.openrouteservice.org/v2/directions/driving-hgv/geojson"


def make_client():
    return RoutingClient(api_key="test-key", profile="driving-hgv", timeout_seconds=10)


def geojson_response(coordinates, distance_meters=160934.4, duration_seconds=6000):
    return {
        "features": [
            {
                "geometry": {"type": "LineString", "coordinates": coordinates},
                "properties": {
                    "summary": {"distance": distance_meters, "duration": duration_seconds}
                },
            }
        ]
    }


@responses.activate
def test_parses_geometry_and_converts_distance_from_meters_to_miles():
    coordinates = [[-87.6298, 41.8781], [-104.9903, 39.7392]]
    responses.add(
        responses.POST,
        DIRECTIONS_URL,
        json=geojson_response(coordinates, distance_meters=160934.4),
        status=200,
    )

    route = make_client().get_route((41.8781, -87.6298), (39.7392, -104.9903))

    assert route.coordinates == [(41.8781, -87.6298), (39.7392, -104.9903)]
    assert route.distance_miles == pytest.approx(100.0, abs=0.01)
    assert route.duration_seconds == 6000


@responses.activate
def test_sends_coordinates_in_lng_lat_order():
    responses.add(
        responses.POST, DIRECTIONS_URL, json=geojson_response([[-87.6, 41.8], [-105.0, 39.7]])
    )

    make_client().get_route((41.8, -87.6), (39.7, -105.0))

    sent_body = responses.calls[0].request.body
    assert b'"coordinates": [[-87.6, 41.8], [-105.0, 39.7]]' in sent_body


@responses.activate
def test_sends_the_api_key_in_the_authorization_header():
    responses.add(
        responses.POST, DIRECTIONS_URL, json=geojson_response([[-87.6, 41.8], [-105.0, 39.7]])
    )

    make_client().get_route((41.8, -87.6), (39.7, -105.0))

    assert responses.calls[0].request.headers["Authorization"] == "test-key"


@responses.activate
def test_makes_exactly_one_http_call_for_a_normal_route():
    responses.add(
        responses.POST, DIRECTIONS_URL, json=geojson_response([[-87.6, 41.8], [-105.0, 39.7]])
    )

    make_client().get_route((41.8, -87.6), (39.7, -105.0))

    assert len(responses.calls) == 1


@responses.activate
def test_a_timeout_raises_routing_unavailable():
    responses.add(responses.POST, DIRECTIONS_URL, body=Timeout())

    with pytest.raises(RoutingUnavailable):
        make_client().get_route((41.8, -87.6), (39.7, -105.0))


@responses.activate
def test_a_connection_error_raises_routing_unavailable():
    responses.add(responses.POST, DIRECTIONS_URL, body=ConnectionError())

    with pytest.raises(RoutingUnavailable):
        make_client().get_route((41.8, -87.6), (39.7, -105.0))


@responses.activate
def test_a_404_response_raises_route_not_found():
    responses.add(responses.POST, DIRECTIONS_URL, json={"error": "not found"}, status=404)

    with pytest.raises(RouteNotFound):
        make_client().get_route((41.8, -87.6), (39.7, -105.0))


@responses.activate
def test_empty_feature_list_raises_route_not_found():
    responses.add(responses.POST, DIRECTIONS_URL, json={"features": []}, status=200)

    with pytest.raises(RouteNotFound):
        make_client().get_route((41.8, -87.6), (39.7, -105.0))
