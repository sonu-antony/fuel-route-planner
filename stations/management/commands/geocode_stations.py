import csv
import time
from pathlib import Path

import requests
from django.core.management.base import BaseCommand

from stations.models import Station
from stations.services.city_lookup import load_city_lookup
from stations.services.cleaning import clean_rows

DEFAULT_INPUT = Path("data/fuel-prices-for-be-assessment.csv")
DEFAULT_CITIES = Path("data/us_cities.csv")
DEFAULT_OUTPUT = Path("data/stations_geocoded.csv")

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_USER_AGENT = "FuelRoutePlanner/1.0 (spotter-assessment)"
NOMINATIM_DELAY_SECONDS = 1

OUTPUT_FIELDNAMES = [
    "opis_id",
    "name",
    "address",
    "city",
    "state",
    "rack_id",
    "price_per_gallon",
    "latitude",
    "longitude",
    "geocode_source",
]


def _nominatim_lookup(city: str, state: str) -> tuple[float, float] | None:
    response = requests.get(
        NOMINATIM_URL,
        params={"q": f"{city}, {state}, USA", "format": "json", "limit": 1},
        headers={"User-Agent": NOMINATIM_USER_AGENT},
        timeout=10,
    )
    time.sleep(NOMINATIM_DELAY_SECONDS)
    results = response.json() if response.ok else []
    if not results:
        return None
    return float(results[0]["lat"]), float(results[0]["lon"])


class Command(BaseCommand):
    help = "Clean, deduplicate and geocode the raw fuel price CSV"

    def add_arguments(self, parser):
        parser.add_argument("--input", default=str(DEFAULT_INPUT))
        parser.add_argument("--cities", default=str(DEFAULT_CITIES))
        parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
        parser.add_argument("--nominatim-fallback", action="store_true")

    def handle(self, *args, **options):
        with open(options["input"], newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        cleaned = clean_rows(rows)
        lookup = load_city_lookup(options["cities"])

        matched_rows = []
        unmatched_pairs = set()
        nominatim_cache: dict[tuple[str, str], tuple[float, float] | None] = {}
        for station in cleaned:
            coordinates = lookup.find(station.city, station.state)
            source = Station.GeocodeSource.CITY_CENTROID
            if coordinates is None and options["nominatim_fallback"]:
                key = (station.city, station.state)
                if key not in nominatim_cache:
                    nominatim_cache[key] = _nominatim_lookup(station.city, station.state)
                coordinates = nominatim_cache[key]
                source = Station.GeocodeSource.MANUAL
            if coordinates is None:
                unmatched_pairs.add((station.city, station.state))
                continue
            matched_rows.append((station, coordinates, source))

        with open(options["output"], "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDNAMES)
            writer.writeheader()
            for station, (latitude, longitude), source in matched_rows:
                writer.writerow(
                    {
                        "opis_id": station.opis_id,
                        "name": station.name,
                        "address": station.address,
                        "city": station.city,
                        "state": station.state,
                        "rack_id": station.rack_id,
                        "price_per_gallon": station.price_per_gallon,
                        "latitude": latitude,
                        "longitude": longitude,
                        "geocode_source": source,
                    }
                )

        self.stdout.write(f"matched: {len(matched_rows)}")
        self.stdout.write(f"unmatched: {len(unmatched_pairs)}")
        for city, state in sorted(unmatched_pairs):
            self.stdout.write(f"  {city}, {state}")
