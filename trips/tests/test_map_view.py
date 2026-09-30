import uuid
from decimal import Decimal

import pytest
import responses

from trips.models import TripPlan


def make_trip_plan():
    return TripPlan.objects.create(
        id=uuid.uuid4(),
        start_query="Chicago, IL",
        finish_query="Denver, CO",
        start_lat=41.8781,
        start_lng=-87.6298,
        finish_lat=39.7392,
        finish_lng=-104.9903,
        distance_miles=1000.0,
        total_gallons=Decimal("100.000"),
        total_cost=Decimal("330.000"),
        route_geojson={"type": "FeatureCollection", "features": []},
        stops=[],
    )


@pytest.mark.django_db
@responses.activate
def test_an_existing_plan_returns_200_with_the_route_geojson_embedded(client):
    trip = make_trip_plan()

    response = client.get(f"/trips/{trip.id}/map/")

    assert response.status_code == 200
    assert b'"type": "FeatureCollection"' in response.content


@pytest.mark.django_db
def test_an_unknown_id_returns_404(client):
    response = client.get(f"/trips/{uuid.uuid4()}/map/")

    assert response.status_code == 404


@pytest.mark.django_db
@responses.activate
def test_rendering_the_map_makes_no_routing_call(client):
    trip = make_trip_plan()

    client.get(f"/trips/{trip.id}/map/")

    assert len(responses.calls) == 0


@pytest.mark.django_db
def test_popups_are_built_from_text_nodes_not_html_strings(client):
    trip = make_trip_plan()

    response = client.get(f"/trips/{trip.id}/map/")

    assert b"textContent" in response.content
    assert b'"<br>' not in response.content


def make_trip_plan_with_a_stop(name="PILOT #1243"):
    return TripPlan.objects.create(
        id=uuid.uuid4(),
        start_query="Chicago, IL",
        finish_query="Denver, CO",
        start_lat=41.8781,
        start_lng=-87.6298,
        finish_lat=39.7392,
        finish_lng=-104.9903,
        distance_miles=1007.5,
        total_gallons=Decimal("102.552"),
        total_cost=Decimal("300.564"),
        route_geojson={"type": "FeatureCollection", "features": []},
        stops=[
            {
                "station_id": 105,
                "name": name,
                "address": "I-8, EXIT 119",
                "city": "Gila Bend",
                "state": "AZ",
                "latitude": 32.9,
                "longitude": -112.7,
                "mile_marker": 0.0,
                "off_route_miles": 0.0,
                "price_per_gallon": "3.269",
                "gallons": 50.0,
                "cost": "163.450",
            }
        ],
    )


@pytest.mark.django_db
def test_the_map_draws_openstreetmap_tiles_under_the_route(client):
    trip = make_trip_plan()

    response = client.get(f"/trips/{trip.id}/map/")

    assert b"tile.openstreetmap.org" in response.content
    assert b'referrerPolicy: "strict-origin-when-cross-origin"' in response.content


@pytest.mark.django_db
def test_the_map_shows_a_trip_summary_and_the_list_of_stops(client):
    trip = make_trip_plan_with_a_stop()

    content = client.get(f"/trips/{trip.id}/map/").content.decode()

    assert "Chicago, IL" in content
    assert "Denver, CO" in content
    assert "1,008 mi" in content
    assert "$300.56" in content
    assert "PILOT #1243" in content
    assert "Gila Bend, AZ" in content


@pytest.mark.django_db
def test_station_names_in_the_stop_list_are_escaped(client):
    trip = make_trip_plan_with_a_stop(name="<img src=x onerror=alert(1)>")

    content = client.get(f"/trips/{trip.id}/map/").content.decode()

    assert "<img src=x" not in content
    assert "&lt;img src=x" in content


@pytest.mark.django_db
def test_the_map_draws_detours_as_dashed_lines(client):
    trip = make_trip_plan()

    content = client.get(f"/trips/{trip.id}/map/").content

    assert b'kind === "detour"' in content
    assert b"dashArray" in content
