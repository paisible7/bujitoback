from rest_framework import serializers

from .models import BusinessSettings


class BusinessSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessSettings
        fields = [
            "ordinary_rate_per_kg",
            "ordinary_days",
            "express_available",
            "express_rate_per_kg",
            "express_days",
            "sensitive_rate_per_kg",
            "sensitive_days",
            "sensitive_note",
            "phone_flat_fee",
            "phone_days",
            "grouping_flat_max_kg",
            "grouping_flat_fee",
            "grouping_rate_per_kg",
            "usd_to_cdf",
            "usd_to_gbp",
            "usd_to_xof",
            "china_warehouse_phone",
            "china_warehouse_street",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]


class EstimateSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["shipping", "grouping"])
    category = serializers.ChoiceField(
        choices=["ordinary", "express", "sensitive", "phone"],
        required=False,
        default="ordinary",
    )
    weight_kg = serializers.DecimalField(
        max_digits=10,
        decimal_places=3,
        required=False,
        allow_null=True,
        min_value=0,
    )
