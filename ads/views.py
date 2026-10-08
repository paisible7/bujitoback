from django.db.models import Q
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.serializers import resolve_uuid_or_pk
from users.permissions import IsAdminUser
from users.roles import is_app_admin
from .models import AD_SCREEN_KEYS, Advertisement
from .serializers import (
    AdvertisementSerializer,
    parse_screens,
    parse_optional_datetime,
    _as_plain_dict,
)


def _uploaded_ad_image(request):
    for field in ('image', 'photo', 'advertisement_image'):
        uploaded = request.FILES.get(field)
        if uploaded is not None:
            return uploaded
    return None


class AdvertisementListView(generics.ListAPIView):
    """Liste des affiches actives (clients + admin)."""

    serializer_class = AdvertisementSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Advertisement.objects.all()
        if is_app_admin(self.request.user) and self.request.query_params.get('all') == '1':
            return qs

        now = timezone.now()
        qs = qs.filter(is_active=True).filter(
            Q(starts_at__isnull=True) | Q(starts_at__lte=now),
            Q(ends_at__isnull=True) | Q(ends_at__gte=now),
        )
        screen = (self.request.query_params.get('screen') or '').strip().lower()
        if screen and screen in AD_SCREEN_KEYS:
            matched_ids = [
                ad.pk
                for ad in qs.only('id', 'screens')
                if screen in (ad.screens or [])
            ]
            qs = qs.filter(pk__in=matched_ids)
        return qs


class AdvertisementCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        data = _as_plain_dict(request.data)
        uploaded_image = _uploaded_ad_image(request)
        if uploaded_image is not None:
            data['image'] = uploaded_image
        if 'is_active' in data and isinstance(data.get('is_active'), str):
            data['is_active'] = data.get('is_active').lower() in (
                '1', 'true', 'yes', 'on',
            )
        if 'screens' in data:
            data['screens'] = parse_screens(data.get('screens'))
        if 'starts_at' in data:
            data['starts_at'] = parse_optional_datetime(data.get('starts_at'))
        if 'ends_at' in data:
            data['ends_at'] = parse_optional_datetime(data.get('ends_at'))
        serializer = AdvertisementSerializer(
            data=data,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        if not data.get('image'):
            return Response(
                {'image': 'Image obligatoire.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ad = serializer.save()
        return Response(
            AdvertisementSerializer(ad, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )


class AdvertisementDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_object(self, pk):
        try:
            return resolve_uuid_or_pk(Advertisement.objects.all(), pk)
        except Advertisement.DoesNotExist:
            return None

    def patch(self, request, pk):
        ad = self.get_object(pk)
        if ad is None:
            return Response({'detail': 'Introuvable.'}, status=status.HTTP_404_NOT_FOUND)
        data = _as_plain_dict(request.data)
        uploaded_image = _uploaded_ad_image(request)
        if uploaded_image is not None:
            data['image'] = uploaded_image
        if 'is_active' in data and isinstance(data.get('is_active'), str):
            data['is_active'] = data.get('is_active').lower() in (
                '1', 'true', 'yes', 'on',
            )
        if 'screens' in data:
            data['screens'] = parse_screens(data.get('screens'))
        if 'starts_at' in data:
            data['starts_at'] = parse_optional_datetime(data.get('starts_at'))
        if 'ends_at' in data:
            data['ends_at'] = parse_optional_datetime(data.get('ends_at'))
        serializer = AdvertisementSerializer(
            ad,
            data=data,
            partial=True,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        ad = serializer.save()
        return Response(AdvertisementSerializer(ad, context={'request': request}).data)

    def delete(self, request, pk):
        ad = self.get_object(pk)
        if ad is None:
            return Response({'detail': 'Introuvable.'}, status=status.HTTP_404_NOT_FOUND)
        ad.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
