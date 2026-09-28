from django.db import models


class Station(models.Model):
    class GeocodeSource(models.TextChoices):
        CITY_CENTROID = "city_centroid"
        MANUAL = "manual"

    opis_id = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=255)
    state = models.CharField(max_length=2, db_index=True)
    rack_id = models.PositiveIntegerField()
    price_per_gallon = models.DecimalField(max_digits=6, decimal_places=3)
    latitude = models.FloatField()
    longitude = models.FloatField()
    geocode_source = models.CharField(max_length=20, choices=GeocodeSource.choices)

    class Meta:
        indexes = [models.Index(fields=["latitude", "longitude"])]
