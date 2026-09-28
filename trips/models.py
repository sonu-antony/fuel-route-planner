import uuid

from django.db import models


class TripPlan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    start_query = models.CharField(max_length=255)
    finish_query = models.CharField(max_length=255)
    start_lat = models.FloatField()
    start_lng = models.FloatField()
    finish_lat = models.FloatField()
    finish_lng = models.FloatField()
    distance_miles = models.FloatField()
    total_gallons = models.DecimalField(max_digits=10, decimal_places=3)
    total_cost = models.DecimalField(max_digits=12, decimal_places=3)
    route_geojson = models.JSONField()
    stops = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
