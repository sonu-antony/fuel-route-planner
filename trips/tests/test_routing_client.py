import pytest
import responses
from requests.exceptions import (
    ChunkedEncodingError,
    ConnectionError,
    InvalidURL,
    Timeout,
    TooManyRedirects,
)

from trips.exceptions import RouteNotFound, RoutingUnavailable
from trips.services.routing_client import RoutingClient

DIRECTIONS_URL = "https://api.heigit.org/openrouteservice/v2/directions/driving-hgv/geojson"


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


@responses.activate
def test_a_point_not_found_error_raises_route_not_found_without_retrying():
    responses.add(
        responses.POST,
        DIRECTIONS_URL,
        json={"error": {"code": 2010, "message": "Could not find routable point"}},
        status=404,
    )

    with pytest.raises(RouteNotFound):
        make_client().get_route((41.8, -87.6), (39.7, -105.0))

    assert len(responses.calls) == 1


@responses.activate
def test_a_body_that_is_not_json_raises_routing_unavailable():
    responses.add(responses.POST, DIRECTIONS_URL, body="<html>bad gateway</html>", status=200)

    with pytest.raises(RoutingUnavailable):
        make_client().get_route((41.8, -87.6), (39.7, -105.0))


@pytest.mark.parametrize(
    "feature",
    [
        {"properties": {"summary": {"distance": 1.0, "duration": 1.0}}},
        {"geometry": {"type": "LineString", "coordinates": [[-87.6, 41.8]]}, "properties": {}},
        {"geometry": {"type": "LineString", "coordinates": "oops"}, "properties": {}},
    ],
)
@responses.activate
def test_a_feature_missing_geometry_or_summary_raises_routing_unavailable(feature):
    responses.add(responses.POST, DIRECTIONS_URL, json={"features": [feature]}, status=200)

    with pytest.raises(RoutingUnavailable):
        make_client().get_route((41.8, -87.6), (39.7, -105.0))


@responses.activate
def test_a_missing_api_key_raises_routing_unavailable_without_calling_the_api():
    client = RoutingClient(api_key="", profile="driving-hgv", timeout_seconds=10)

    with pytest.raises(RoutingUnavailable, match="ORS_API_KEY"):
        client.get_route((41.8, -87.6), (39.7, -105.0))

    assert len(responses.calls) == 0


@responses.activate
def test_a_rate_limit_response_names_the_status_code():
    responses.add(responses.POST, DIRECTIONS_URL, json={"error": "rate limit"}, status=429)

    with pytest.raises(RouteNotFound, match="429"):
        make_client().get_route((41.8, -87.6), (39.7, -105.0))


@pytest.mark.parametrize("coordinates", [[], [[-87.6, 41.8]]])
@responses.activate
def test_a_route_with_fewer_than_two_points_raises_routing_unavailable(coordinates):
    responses.add(responses.POST, DIRECTIONS_URL, json=geojson_response(coordinates), status=200)

    with pytest.raises(RoutingUnavailable):
        make_client().get_route((41.8, -87.6), (39.7, -105.0))


@pytest.mark.parametrize("distance_meters", [-1.0, float("nan"), float("inf")])
@responses.activate
def test_a_negative_or_non_finite_distance_raises_routing_unavailable(distance_meters):
    responses.add(
        responses.POST,
        DIRECTIONS_URL,
        json=geojson_response([[-87.6, 41.8], [-105.0, 39.7]], distance_meters=distance_meters),
        status=200,
    )

    with pytest.raises(RoutingUnavailable):
        make_client().get_route((41.8, -87.6), (39.7, -105.0))


@pytest.mark.parametrize("error", [ChunkedEncodingError(), TooManyRedirects(), InvalidURL()])
@responses.activate
def test_any_requests_failure_raises_routing_unavailable(error):
    responses.add(responses.POST, DIRECTIONS_URL, body=error)

    with pytest.raises(RoutingUnavailable):
        make_client().get_route((41.8, -87.6), (39.7, -105.0))
