from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsAppAdmin

from .models import BusinessSettings
from .serializers import BusinessSettingsSerializer, EstimateSerializer
from parcels.expedition_utils import cbm_cost
from .utils import grouping_cost, shipping_cost


class BusinessSettingsView(APIView):
    """
    GET  : authentifié — tarifs + taux (affichage client / admin).
    PATCH: admin — mise à jour (JSON ou multipart pour QR).
    """

    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def get_permissions(self):
        if self.request.method in ("PATCH", "PUT"):
            return [IsAppAdmin()]
        return [IsAuthenticated()]

    def get(self, request):
        settings = BusinessSettings.load()
        return Response(
            BusinessSettingsSerializer(settings, context={"request": request}).data
        )

    def patch(self, request):
        settings = BusinessSettings.load()
        serializer = BusinessSettingsSerializer(
            settings,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        # Upload QR images (not in ModelSerializer writable fields as URLs)
        update_fields = []
        if request.FILES.get("alipay_qr_image"):
            settings.alipay_qr_image = request.FILES["alipay_qr_image"]
            update_fields.append("alipay_qr_image")
        if request.FILES.get("wechat_qr_image"):
            settings.wechat_qr_image = request.FILES["wechat_qr_image"]
            update_fields.append("wechat_qr_image")
        if update_fields:
            settings.save(update_fields=update_fields)

        settings.refresh_from_db()
        return Response(
            BusinessSettingsSerializer(settings, context={"request": request}).data
        )


class PricingEstimateView(APIView):
    """Calcule frais d'expédition, groupage ou CBM selon le poids / catégorie."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = EstimateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        cfg = BusinessSettings.load()
        kind = data["kind"]
        weight = data.get("weight_kg")

        if kind == "grouping":
            if weight is None:
                return Response(
                    {"message": "weight_kg is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            result = grouping_cost(weight_kg=weight, settings=cfg)
        elif kind == "cbm":
            volume = data.get("volume_cbm")
            if volume is None:
                return Response(
                    {"message": "volume_cbm is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            result = cbm_cost(volume_cbm=volume, settings=cfg)
        else:
            category = data.get("category") or "ordinary"
            if category != "phone" and weight is None:
                return Response(
                    {"message": "weight_kg is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            result = shipping_cost(
                category=category,
                weight_kg=weight,
                settings=cfg,
            )

        return Response(result)
