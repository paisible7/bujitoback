from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsAppAdmin

from .models import BusinessSettings
from .serializers import BusinessSettingsSerializer, EstimateSerializer
from .utils import grouping_cost, shipping_cost


class BusinessSettingsView(APIView):
    """
    GET  : authentifié — tarifs + taux (affichage client / admin).
    PATCH: admin — mise à jour.
    """

    def get_permissions(self):
        if self.request.method in ("PATCH", "PUT"):
            return [IsAppAdmin()]
        return [IsAuthenticated()]

    def get(self, request):
        settings = BusinessSettings.load()
        return Response(BusinessSettingsSerializer(settings).data)

    def patch(self, request):
        settings = BusinessSettings.load()
        serializer = BusinessSettingsSerializer(
            settings,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class PricingEstimateView(APIView):
    """Calcule frais d'expédition ou de groupage selon le poids / catégorie."""

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
