from pathlib import Path

import pytest
from django.core.management import call_command

from stations.models import Station

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.django_db
def test_load_stations_creates_one_station_per_row_of_a_fixture_file():
    call_command("load_stations", file=str(FIXTURES / "sample_geocoded.csv"))

    assert Station.objects.count() == 2
    station = Station.objects.get(opis_id=1)
    assert station.name == "PILOT A"
    assert station.city == "Springfield"
    assert station.state == "IL"
    assert station.geocode_source == Station.GeocodeSource.CITY_CENTROID


@pytest.mark.django_db
def test_running_load_stations_twice_does_not_duplicate_rows_and_updates_prices():
    call_command("load_stations", file=str(FIXTURES / "sample_geocoded.csv"))
    call_command("load_stations", file=str(FIXTURES / "sample_geocoded_updated.csv"))

    assert Station.objects.count() == 2
    station = Station.objects.get(opis_id=1)
    assert str(station.price_per_gallon) == "2.899"


@pytest.mark.django_db
def test_geocode_stations_writes_only_us_stations_deduplicated_with_coordinates(tmp_path):
    output_path = tmp_path / "geocoded.csv"

    call_command(
        "geocode_stations",
        input=str(FIXTURES / "geocode_prices.csv"),
        cities=str(FIXTURES / "geocode_cities.csv"),
        output=str(output_path),
    )

    rows = output_path.read_text().splitlines()
    assert len(rows) == 3
    assert "Toronto" not in output_path.read_text()
    assert "3.050" in output_path.read_text()
    assert "3.100" not in output_path.read_text()


@pytest.mark.django_db
def test_geocode_stations_reports_unmatched_pairs_and_excludes_them_from_output(capsys, tmp_path):
    output_path = tmp_path / "geocoded.csv"

    call_command(
        "geocode_stations",
        input=str(FIXTURES / "geocode_prices.csv"),
        cities=str(FIXTURES / "geocode_cities.csv"),
        output=str(output_path),
    )

    captured = capsys.readouterr()
    assert "Nowhereton" in captured.out
    assert "Nowhereton" not in output_path.read_text()
