import uuid

import pytest
import responses
from django.core.cache import cache
from rest_framework.test import APIClient

from stations.models import Station
from stations.services.spatial_index import reset_index

DIRECTIONS_URL = "https://api.openrouteservice.org/v2/directions/driving-hgv/geojson"
START = (39.0, -98.0)
FINISH = (39.7236, -98.0)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture(autouse=True)
def _reset_state():
    reset_index()
    cache.clear()
    yield
    reset_index()
    cache.clear()


def ors_response(start=START, finish=FINISH, distance_meters=80467.2, duration_seconds=3600):
    return {
        "features": [
            {
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[start[1], start[0]], [finish[1], finish[0]]],
                },
                "properties": {
                    "summary": {"distance": distance_meters, "duration": duration_seconds}
                },
            }
        ]
    }


def make_station():
    return Station.objects.create(
        opis_id=1,
        name="MIDWAY FUEL",
        address="I-1",
        city="Somewhere",
        state="KS",
        rack_id=1,
        price_per_gallon="3.199",
        latitude=39.36,
        longitude=-97.95,
        geocode_source=Station.GeocodeSource.CITY_CENTROID,
    )


@pytest.mark.django_db
def test_health_endpoint_returns_ok(api_client):
    response = api_client.get("/api/v1/health/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
@responses.activate
def test_happy_path_returns_200_with_every_documented_field_and_nothing_else(api_client):
    responses.add(responses.POST, DIRECTIONS_URL, json=ors_response(), status=200)
    make_station()

    response = api_client.post(
        "/api/v1/trips/plan/",
        {"start": f"{START[0]},{START[1]}", "finish": f"{FINISH[0]},{FINISH[1]}"},
        format="json",
    )

    assert response.status_code == 200
    body = response.json()
    expected_top_level_keys = {
        "id",
        "start",
        "finish",
        "distance_miles",
        "total_gallons",
        "total_cost",
        "fuel_stops",
        "route",
        "map_url",
        "meta",
    }
    assert set(body.keys()) == expected_top_level_keys
    assert body["meta"] == {
        "routing_calls": 1,
        "cached": False,
        "elapsed_ms": body["meta"]["elapsed_ms"],
    }
    assert len(body["fuel_stops"]) >= 1
    expected_stop_keys = {
        "station_id",
        "name",
        "address",
        "city",
        "state",
        "mile_marker",
        "price_per_gallon",
        "gallons",
        "cost",
    }
    assert set(body["fuel_stops"][0].keys()) == expected_stop_keys
    uuid.UUID(body["id"])


@pytest.mark.django_db
def test_missing_finish_returns_400(api_client):
    response = api_client.post("/api/v1/trips/plan/", {"start": "39.0,-98.0"}, format="json")

    assert response.status_code == 400
    assert response.json()["error"] == "validation_error"


@pytest.mark.django_db
def test_an_unknown_city_returns_404(api_client):
    response = api_client.post(
        "/api/v1/trips/plan/",
        {"start": "Nowhereville, ZZ", "finish": "39.7236,-98.0"},
        format="json",
    )

    assert response.status_code == 404
    assert response.json()["error"] == "location_not_found"


@pytest.mark.django_db
@responses.activate
def test_an_unreachable_route_returns_422(api_client):
    responses.add(responses.POST, DIRECTIONS_URL, json=ors_response(), status=200)

    response = api_client.post(
        "/api/v1/trips/plan/",
        {"start": f"{START[0]},{START[1]}", "finish": f"{FINISH[0]},{FINISH[1]}"},
        format="json",
    )

    assert response.status_code == 422
    assert response.json()["error"] == "unreachable_route"


@pytest.mark.django_db
@responses.activate
def test_routing_failure_returns_502(api_client):
    responses.add(responses.POST, DIRECTIONS_URL, json={"error": "boom"}, status=500)

    response = api_client.post(
        "/api/v1/trips/plan/",
        {"start": f"{START[0]},{START[1]}", "finish": f"{FINISH[0]},{FINISH[1]}"},
        format="json",
    )

    assert response.status_code == 502
    assert response.json()["error"] == "routing_unavailable"


@pytest.mark.django_db
@responses.activate
def test_a_repeated_request_returns_cached_true_and_zero_routing_calls(api_client):
    responses.add(responses.POST, DIRECTIONS_URL, json=ors_response(), status=200)
    make_station()
    payload = {"start": f"{START[0]},{START[1]}", "finish": f"{FINISH[0]},{FINISH[1]}"}

    first = api_client.post("/api/v1/trips/plan/", payload, format="json")
    second = api_client.post("/api/v1/trips/plan/", payload, format="json")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["meta"]["cached"] is True
    assert second.json()["meta"]["routing_calls"] == 0
    assert len(responses.calls) == 1
