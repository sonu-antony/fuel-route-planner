from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Station",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("opis_id", models.PositiveIntegerField(unique=True)),
                ("name", models.CharField(max_length=255)),
                ("address", models.CharField(max_length=255)),
                ("city", models.CharField(max_length=255)),
                ("state", models.CharField(db_index=True, max_length=2)),
                ("rack_id", models.PositiveIntegerField()),
                ("price_per_gallon", models.DecimalField(decimal_places=3, max_digits=6)),
                ("latitude", models.FloatField()),
                ("longitude", models.FloatField()),
                (
                    "geocode_source",
                    models.CharField(
                        choices=[("city_centroid", "City Centroid"), ("manual", "Manual")],
                        max_length=20,
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["latitude", "longitude"], name="stations_st_latitud_ba98b4_idx"
                    )
                ],
            },
        ),
    ]
