import csv
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand

from stations.models import Station
from stations.services.spatial_index import reset_index

DEFAULT_FILE = Path("data/stations_geocoded.csv")


class Command(BaseCommand):
    help = "Load geocoded stations into the database, upserting on opis_id"

    def add_arguments(self, parser):
        parser.add_argument("--file", default=str(DEFAULT_FILE))

    def handle(self, *args, **options):
        with open(options["file"], newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))

        created_count = 0
        updated_count = 0
        for row in rows:
            _, created = Station.objects.update_or_create(
                opis_id=int(row["opis_id"]),
                defaults={
                    "name": row["name"],
                    "address": row["address"],
                    "city": row["city"],
                    "state": row["state"],
                    "rack_id": int(row["rack_id"]),
                    "price_per_gallon": Decimal(row["price_per_gallon"]),
                    "latitude": float(row["latitude"]),
                    "longitude": float(row["longitude"]),
                    "geocode_source": row["geocode_source"],
                },
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        reset_index()

        self.stdout.write(f"created: {created_count}")
        self.stdout.write(f"updated: {updated_count}")
