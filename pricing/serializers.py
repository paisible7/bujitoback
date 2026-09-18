from rest_framework import serializers

from parcels.media_urls import absolute_media_url

from .models import BusinessSettings


class BusinessSettingsSerializer(serializers.ModelSerializer):
    alipay_qr_url = serializers.SerializerMethodField()
    wechat_qr_url = serializers.SerializerMethodField()

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
            "cbm_rate_usd",
            "usd_to_cdf",
            "usd_to_gbp",
            "usd_to_xof",
            "usd_to_cny",
            "china_warehouse_phone",
            "china_warehouse_street",
            "alipay_qr_url",
            "wechat_qr_url",
            "updated_at",
        ]
        read_only_fields = ["updated_at", "alipay_qr_url", "wechat_qr_url"]

    def get_alipay_qr_url(self, obj):
        return absolute_media_url(
            obj.alipay_qr_image,
            self.context.get("request"),
            label="Alipay QR",
        )

    def get_wechat_qr_url(self, obj):
        return absolute_media_url(
            obj.wechat_qr_image,
            self.context.get("request"),
            label="WeChat QR",
        )


class EstimateSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["shipping", "grouping", "cbm"])
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
    volume_cbm = serializers.DecimalField(
        max_digits=12,
        decimal_places=4,
        required=False,
        allow_null=True,
        min_value=0,
    )
