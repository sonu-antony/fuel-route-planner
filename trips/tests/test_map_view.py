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
