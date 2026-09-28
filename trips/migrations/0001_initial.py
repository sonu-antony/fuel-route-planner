import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="TripPlan",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("start_query", models.CharField(max_length=255)),
                ("finish_query", models.CharField(max_length=255)),
                ("start_lat", models.FloatField()),
                ("start_lng", models.FloatField()),
                ("finish_lat", models.FloatField()),
                ("finish_lng", models.FloatField()),
                ("distance_miles", models.FloatField()),
                ("total_gallons", models.DecimalField(decimal_places=3, max_digits=10)),
                ("total_cost", models.DecimalField(decimal_places=3, max_digits=12)),
                ("route_geojson", models.JSONField()),
                ("stops", models.JSONField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
    ]
