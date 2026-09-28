from decimal import Decimal

from rest_framework import serializers


class TripPlanRequestSerializer(serializers.Serializer):
    start = serializers.CharField()
    finish = serializers.CharField()
    start_fuel_gallons = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        required=False,
        default=Decimal("0"),
        min_value=Decimal("0"),
        max_value=Decimal("50"),
    )

    def validate(self, attrs: dict) -> dict:
        if attrs["start"].strip().lower() == attrs["finish"].strip().lower():
            raise serializers.ValidationError("start and finish must be different")
        return attrs
