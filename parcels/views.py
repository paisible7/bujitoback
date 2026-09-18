import base64
import os
import re
import zipfile
from django.core.files.base import ContentFile
from rest_framework import generics, status, filters
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from django.db import transaction # Pour les opérations atomiques
from django.http import Http404
from .models import Order, Parcel, Consolidation, OrderImage, ImportBatch, ShipmentBatch, ExpeditionRequest
from .serializers import (
    OrderSerializer,
    ParcelSerializer,
    OrderCreateSerializer,
    OrderClientUpdateSerializer,
    OrderQuoteSerializer,
    ConsolidationSerializer,
    ConsolidationCreateSerializer,
    ConsolidationClientUpdateSerializer,
    ConsolidationUpdateSerializer,
    ShipmentBatchSerializer,
    ExpeditionRequestSerializer,
)
from .expedition_utils import build_expedition_quote, parcel_volume_cbm
from .ownership import parcels_for_user_q, user_owns_parcel
from users.permissions import IsAdminUser
from users.roles import is_app_admin
from users.models import CustomUser
from notifications.utils import notify_admins, send_fcm_notification
from .pagination import OptionalPageNumberPagination

class OrderListCreateView(generics.ListCreateAPIView):
    queryset = Order.objects.all()
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ['id', 'status', 'parcels__tracking_number']

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return OrderCreateSerializer
        return OrderSerializer

    def get_queryset(self):
        queryset = (
            Order.objects.select_related('user')
            .prefetch_related('parcels', 'images', 'payments')
            .order_by('-order_date')
        )
        if self.request.user.is_authenticated and is_app_admin(self.request.user):
            return queryset
        return queryset.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        # Photos produit : champ "images" + index colis optionnel "image_package_indexes"
        indexes_raw = request.data.get('image_package_indexes', '')
        index_list = []
        if isinstance(indexes_raw, str) and indexes_raw.strip():
            for part in indexes_raw.split(','):
                part = part.strip()
                if not part:
                    continue
                try:
                    index_list.append(max(0, int(part)))
                except ValueError:
                    index_list.append(0)
        elif isinstance(indexes_raw, list):
            for part in indexes_raw:
                try:
                    index_list.append(max(0, int(part)))
                except (TypeError, ValueError):
                    index_list.append(0)

        uploads = request.FILES.getlist('images')
        for i, uploaded in enumerate(uploads):
            pkg_index = index_list[i] if i < len(index_list) else 0
            OrderImage.objects.create(
                order=serializer.instance,
                image=uploaded,
                package_index=pkg_index,
            )

        headers = self.get_success_headers(serializer.data)
        full_serializer = OrderSerializer(serializer.instance, context={'request': request})
        return Response(full_serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class OrderDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]
    queryset = Order.objects.all()

    def get_object(self):
        obj = super().get_object()
        user = self.request.user
        is_owner = obj.user_id == user.id
        admin = is_app_admin(user)

        if self.request.method in ('GET', 'HEAD', 'OPTIONS'):
            if not is_owner and not admin:
                self.permission_denied(self.request)
            return obj

        # Mise à jour : admin, ou propriétaire avant paiement / sans colis.
        if admin:
            return obj
        if (
            is_owner
            and not obj.payments.filter(status='completed').exists()
            and not obj.parcels.exists()
            and obj.status != 'cancelled'
        ):
            return obj
        self.permission_denied(self.request)
        return obj

    def get_serializer_class(self):
        if self.request.method in ('PUT', 'PATCH'):
            data = self.request.data
            if is_app_admin(self.request.user) and (
                'product_items' in data
                or 'withdrawal_fee' in data
                or 'commission_fee' in data
            ):
                return OrderQuoteSerializer
            if not is_app_admin(self.request.user):
                return OrderClientUpdateSerializer
        return OrderSerializer

    def _sync_order_images(self, order, request):
        """Remplace / conserve les images selon keep_image_ids + nouveaux uploads."""
        uploads = request.FILES.getlist('images')
        keep_raw = request.data.get('keep_image_ids', None)
        if keep_raw is None and not uploads:
            return

        keep_ids = []
        if keep_raw is not None:
            if isinstance(keep_raw, str) and keep_raw.strip():
                for part in keep_raw.split(','):
                    part = part.strip()
                    if not part:
                        continue
                    try:
                        keep_ids.append(int(part))
                    except ValueError:
                        continue
            elif isinstance(keep_raw, list):
                for part in keep_raw:
                    try:
                        keep_ids.append(int(part))
                    except (TypeError, ValueError):
                        continue

        if keep_raw is not None:
            order.images.exclude(id__in=keep_ids).delete()
        elif uploads:
            order.images.all().delete()

        # Remap package_index des images conservées (édition multi-colis)
        remap_raw = request.data.get('keep_image_package_indexes', '')
        if isinstance(remap_raw, str) and remap_raw.strip():
            for part in remap_raw.split(','):
                part = part.strip()
                if not part or ':' not in part:
                    continue
                id_s, pkg_s = part.split(':', 1)
                try:
                    img_id = int(id_s.strip())
                    pkg_i = max(0, int(pkg_s.strip()))
                except ValueError:
                    continue
                order.images.filter(id=img_id).update(package_index=pkg_i)

        indexes_raw = request.data.get('image_package_indexes', '')
        index_list = []
        if isinstance(indexes_raw, str) and indexes_raw.strip():
            for part in indexes_raw.split(','):
                part = part.strip()
                if not part:
                    continue
                try:
                    index_list.append(max(0, int(part)))
                except ValueError:
                    index_list.append(0)
        elif isinstance(indexes_raw, list):
            for part in indexes_raw:
                try:
                    index_list.append(max(0, int(part)))
                except (TypeError, ValueError):
                    index_list.append(0)

        for i, uploaded in enumerate(uploads):
            pkg_index = index_list[i] if i < len(index_list) else 0
            OrderImage.objects.create(
                order=order,
                image=uploaded,
                package_index=pkg_index,
            )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer_class = self.get_serializer_class()

        if serializer_class is OrderQuoteSerializer:
            serializer = OrderQuoteSerializer(
                instance, data=request.data, partial=partial
            )
            serializer.is_valid(raise_exception=True)
            order = serializer.save()
            return Response(
                OrderSerializer(order, context={'request': request}).data
            )

        if serializer_class is OrderClientUpdateSerializer:
            serializer = OrderClientUpdateSerializer(
                instance, data=request.data, partial=partial
            )
            serializer.is_valid(raise_exception=True)
            order = serializer.save()
            self._sync_order_images(order, request)
            order.refresh_from_db()
            return Response(
                OrderSerializer(order, context={'request': request}).data
            )

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        if (
            serializer_class is OrderSerializer
            and 'status' in request.data
            and request.data.get('status') != 'cancelled'
            and instance.parcels.exists()
        ):
            return Response(
                {
                    'detail': (
                        'Le statut de la commande est calculé automatiquement '
                        'à partir des colis. Mettez à jour le statut de chaque colis.'
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        self.perform_update(serializer)
        if serializer_class is OrderSerializer and instance.parcels.exists():
            instance.refresh_from_db()
        return Response(OrderSerializer(instance, context={'request': request}).data)

    def perform_update(self, serializer):
        serializer.save()

class ParcelListCreateView(generics.ListCreateAPIView):
    serializer_class = ParcelSerializer
    permission_classes = [IsAuthenticated] # IsAdminUser checks method, but we filter queryset
    parser_classes = [JSONParser, FormParser, MultiPartParser]
    filter_backends = [filters.SearchFilter]
    search_fields = [
        'tracking_number',
        'supplier_tracking_number',
        'description',
        'current_location',
    ]
    pagination_class = OptionalPageNumberPagination

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return Parcel.objects.none()
        queryset = Parcel.objects.select_related('order__user').prefetch_related(
            'consolidations',
            'shipment_batches',
            'extra_images',
        )
        if is_app_admin(self.request.user):
            return queryset
        return queryset.filter(parcels_for_user_q(self.request.user)).distinct()

    def perform_create(self, serializer):
        # Still check for admin for POST via IsAdminUser if we use it,
        # or handle it here if we use IsAuthenticated.
        if (not is_app_admin(self.request.user)):
            self.permission_denied(self.request)
        serializer.save()

    def create(self, request, *args, **kwargs):
        """Enregistrement manuel d'un colis depuis l'app (sans Excel)."""
        from datetime import date as date_cls
        from decimal import Decimal, InvalidOperation

        from .weight_utils import parse_weight_kg, parse_china_date
        from .tracking_utils import generate_tracking_number

        if not is_app_admin(request.user):
            return Response(
                {"detail": "Accès refusé."},
                status=status.HTTP_403_FORBIDDEN,
            )

        data = request.data

        def _text(key, default=''):
            raw = data.get(key, default)
            if raw is None:
                return default
            if isinstance(raw, (list, tuple)):
                raw = raw[0] if raw else default
            return str(raw).strip()

        tracking = _text('tracking_number')
        supplier_tracking = _text('supplier_tracking_number')
        user_email = _text('user_email')
        client_phone = _text('client_phone')
        # Tracking Bujito auto : BUJ + 4 derniers chiffres du téléphone client.
        if client_phone:
            tracking = generate_tracking_number(client_phone=client_phone)
        elif not tracking:
            tracking = generate_tracking_number()
        if not tracking and not supplier_tracking:
            return Response(
                {"detail": "tracking_number ou supplier_tracking_number requis."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = None
        if user_email:
            user = CustomUser.objects.filter(email__iexact=user_email).first()
        elif client_phone:
            clean_phone = client_phone.replace(' ', '')
            user = CustomUser.objects.filter(
                phone_number__icontains=clean_phone
            ).first()

        order_id = data.get('order') or data.get('order_id')
        if isinstance(order_id, str) and not order_id.strip():
            order_id = None
        order_sequence = data.get('order_sequence')
        try:
            order_sequence = int(order_sequence) if order_sequence not in (None, '') else None
        except (TypeError, ValueError):
            order_sequence = None
        order = None
        if order_id:
            order = Order.objects.filter(id=order_id).first()
        elif user:
            order = (
                Order.objects.filter(
                    user=user,
                    status__in=['pending', 'processing'],
                )
                .order_by('-order_date')
                .first()
            )

        weight_volume = _text('weight_volume') or None
        weight_kg = parse_weight_kg(
            data.get('weight_kg')
            if data.get('weight_kg') not in (None, '')
            else weight_volume
        )
        volume_cbm = None
        raw_cbm = data.get('volume_cbm')
        if raw_cbm not in (None, ''):
            try:
                volume_cbm = Decimal(str(raw_cbm).replace(',', '.'))
            except (InvalidOperation, TypeError, ValueError):
                volume_cbm = None

        status_val = (_text('status') or 'pending').lower()
        allowed = {c[0] for c in Parcel.PARCEL_STATUS_CHOICES}
        if status_val not in allowed:
            status_val = 'pending'

        china_date = parse_china_date(data.get('china_arrival_date'))
        if china_date is None and status_val == 'pending':
            china_date = date_cls.today()

        existing = None
        if tracking:
            existing = Parcel.objects.filter(tracking_number=tracking).first()
        if existing is None and supplier_tracking:
            existing = Parcel.objects.filter(
                supplier_tracking_number=supplier_tracking
            ).first()
        if existing is not None:
            return Response(
                {
                    "detail": (
                        f"Un colis existe déjà "
                        f"({existing.tracking_number or existing.pk})."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        parcel = Parcel(
            tracking_number=tracking or supplier_tracking,
            supplier_tracking_number=supplier_tracking or None,
            order=order,
            order_sequence=order_sequence,
            status=status_val,
            current_location=_text('current_location') or None,
            description=_text('description') or None,
            client_name=_text('client_name') or None,
            client_phone=client_phone or None,
            weight_volume=weight_volume,
            warehouse_number=_text('warehouse_number') or None,
            china_arrival_date=china_date,
        )
        if weight_kg is not None:
            parcel.weight_kg = weight_kg
        if volume_cbm is not None and volume_cbm >= 0:
            parcel.volume_cbm = volume_cbm

        image_file = request.FILES.get('image') or request.FILES.get('package_photo')
        if image_file is not None:
            parcel.image = image_file
        else:
            image_data = data.get('package_photo') or data.get('image')
            if (
                image_data
                and isinstance(image_data, str)
                and image_data.startswith('data:image')
            ):
                try:
                    header, imgstr = image_data.split(';base64,')
                    ext = header.split('/')[-1]
                    parcel.image = ContentFile(
                        base64.b64decode(imgstr),
                        name=f"parcel_{parcel.tracking_number}.{ext}",
                    )
                except Exception:
                    pass

        try:
            parcel.save()
        except Exception as exc:
            from django.db import IntegrityError

            if isinstance(exc, IntegrityError):
                return Response(
                    {
                        "detail": (
                            "Impossible d'enregistrer : numéro de suivi "
                            "ou séquence déjà utilisés."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            return Response(
                {"detail": f"Erreur d'enregistrement : {exc}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            ParcelSerializer(parcel, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )


class ParcelDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ParcelSerializer
    permission_classes = [IsAuthenticated]
    queryset = Parcel.objects.select_related('order__user').prefetch_related(
        'consolidations',
        'shipment_batches',
        'extra_images',
    )
    lookup_field = 'tracking_number' # Important pour matcher l'URL

    def get_object(self):
        obj = super().get_object()
        if is_app_admin(self.request.user):
            return obj
        if user_owns_parcel(self.request.user, obj):
            return obj
        self.permission_denied(self.request)

    def perform_update(self, serializer):
        if (not is_app_admin(self.request.user)):
            self.permission_denied(self.request)
        from datetime import date
        old_status = serializer.instance.status
        parcel = serializer.save()
        # Marquage arrivée entrepôt → date Chine si absente
        if (
            old_status != 'pending'
            and parcel.status == 'pending'
            and parcel.china_arrival_date is None
        ):
            parcel.china_arrival_date = date.today()
            parcel.save(update_fields=['china_arrival_date', 'last_updated'])
        from .grouping import sync_completed_group_parcel_status

        sync_completed_group_parcel_status(parcel)

class ParcelTrackView(generics.RetrieveAPIView):
    serializer_class = ParcelSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'tracking_number'
    queryset = Parcel.objects.all()

    def get_object(self):
        tracking_number = self.kwargs.get(self.lookup_field)
        try:
            parcel = Parcel.objects.get(tracking_number=tracking_number)
            return parcel
        except Parcel.DoesNotExist:
            raise Http404("Colis non trouvé.")

class ParcelGroupView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        serializer = ConsolidationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tracking_numbers = serializer.validated_data['tracking_numbers']
        client_note = serializer.validated_data.get('client_note') or ''

        user = request.user
        eligible_statuses = ['pending']  # Arrivé à l'entrepôt

        with transaction.atomic():
            parcels_to_group = []
            for tn in tracking_numbers:
                try:
                    parcel = Parcel.objects.select_related('order__user').get(
                        tracking_number=tn
                    )
                except Parcel.DoesNotExist:
                    return Response(
                        {"detail": f"Le colis avec le numéro de suivi {tn} n'existe pas."},
                        status=status.HTTP_404_NOT_FOUND
                    )
                if not user_owns_parcel(user, parcel):
                    return Response(
                        {"detail": f"Le colis {tn} n'appartient pas à l'utilisateur."},
                        status=status.HTTP_403_FORBIDDEN
                    )
                if parcel.status not in eligible_statuses:
                    return Response(
                        {
                            "detail": (
                                f"Le colis {tn} n'est pas éligible au groupage "
                                "(doit être « Arrivé à l'entrepôt »)."
                            )
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )
                already_grouped = Consolidation.objects.filter(
                    status__in=['pending', 'processing'],
                    parcels=parcel,
                ).exists()
                if already_grouped:
                    return Response(
                        {"detail": f"Le colis {tn} fait déjà partie d'une demande de groupage en cours."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                parcels_to_group.append(parcel)

            consolidation = Consolidation.objects.create(
                user=user,
                status='pending',
                client_note=client_note,
            )
            consolidation.parcels.set(parcels_to_group)

        # Notifications hors transaction : un échec FCM ne doit pas annuler la demande.
        parcel_count = len(parcels_to_group)
        admin_body = (
            f"{user.email} demande le groupage de {parcel_count} colis "
            f"(#{consolidation.pk})."
        )
        if client_note:
            admin_body = f"{admin_body} Description: {client_note}"
        try:
            notify_admins(
                "Nouvelle demande de groupage",
                admin_body,
                type="consolidation",
                reference_id=consolidation.pk,
                data={"type": "consolidation", "reference_id": consolidation.pk},
            )
            send_fcm_notification(
                user,
                "Demande de groupage envoyee",
                f"Votre demande de groupage #{consolidation.pk} ({parcel_count} colis) est en attente de validation.",
                type="consolidation",
                reference_id=consolidation.pk,
                data={"type": "consolidation", "reference_id": consolidation.pk},
            )
        except Exception:
            pass

        response_serializer = ConsolidationSerializer(
            consolidation, context={'request': request}
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class ConsolidationListView(generics.ListAPIView):
    serializer_class = ConsolidationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = OptionalPageNumberPagination

    def get_queryset(self):
        qs = Consolidation.objects.prefetch_related(
            'parcels',
            'parcel_decisions',
            'note_images',
            'user',
        )
        if self.request.user.is_authenticated and is_app_admin(self.request.user):
            return qs.all()
        return qs.filter(user=self.request.user)


class ConsolidationBulkStatusView(APIView):
    """Changer le statut de plusieurs groupages en une requête (admin)."""

    permission_classes = [IsAuthenticated, IsAdminUser]

    def post(self, request):
        ids = request.data.get('ids') or request.data.get('group_ids') or []
        new_status = request.data.get('status')
        if not isinstance(ids, list) or not ids:
            return Response(
                {"detail": "ids requis (liste non vide)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        valid = {c[0] for c in Consolidation.CONSOLIDATION_STATUS_CHOICES}
        if new_status not in valid:
            return Response(
                {"detail": f"Statut invalide. Valeurs: {sorted(valid)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        updated = []
        missing = []
        with transaction.atomic():
            for raw_id in ids:
                try:
                    pk = int(raw_id)
                except (TypeError, ValueError):
                    missing.append(raw_id)
                    continue
                group = Consolidation.objects.filter(pk=pk).first()
                if group is None:
                    missing.append(pk)
                    continue
                group.status = new_status
                group.save(update_fields=['status'])
                updated.append(pk)

        return Response({
            "updated": updated,
            "updated_count": len(updated),
            "missing": missing,
            "status": new_status,
        }, status=status.HTTP_200_OK)


class ConsolidationDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = ConsolidationSerializer
    permission_classes = [IsAuthenticated]
    queryset = Consolidation.objects.prefetch_related(
        'parcels',
        'parcel_decisions',
        'note_images',
        'user',
    )

    def get_serializer_class(self):
        if self.request.method in ('PUT', 'PATCH'):
            if not is_app_admin(self.request.user):
                return ConsolidationClientUpdateSerializer
            return ConsolidationUpdateSerializer
        return ConsolidationSerializer

    def get_object(self):
        obj = super().get_object()
        user = self.request.user
        is_owner = obj.user_id == user.id
        admin = is_app_admin(user)

        if self.request.method in ('GET', 'HEAD', 'OPTIONS'):
            if not is_owner and not admin:
                self.permission_denied(self.request)
            return obj

        if admin:
            return obj
        # Client propriétaire : peut modifier tant que non annulé
        # (avant confirmation, après devis, ou après acceptation).
        if is_owner and obj.status != 'cancelled':
            return obj
        self.permission_denied(self.request)
        return obj

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer_class = self.get_serializer_class()

        if serializer_class is ConsolidationClientUpdateSerializer:
            serializer = ConsolidationClientUpdateSerializer(
                instance,
                data=request.data,
                partial=partial,
                context={'request': request},
            )
            serializer.is_valid(raise_exception=True)
            group = serializer.save()
            group.refresh_from_db()
            return Response(
                ConsolidationSerializer(
                    group, context={'request': request}
                ).data
            )

        return super().update(request, *args, **kwargs)

class ParcelBulkImportView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def post(self, request):
        import json
        import os

        parcels_data = request.data.get('parcels', [])
        if isinstance(parcels_data, str):
            try:
                parcels_data = json.loads(parcels_data)
            except json.JSONDecodeError:
                return Response(
                    {"message": "parcels JSON invalide"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        created_count = 0
        updated_count = 0
        errors = []

        with transaction.atomic():
            for data in parcels_data:
                tracking = str(data.get('tracking_number') or '').strip()
                supplier_tracking = str(
                    data.get('supplier_tracking_number') or ''
                ).strip()
                if not tracking and not supplier_tracking:
                    continue

                # Tenter de lier à un utilisateur via Email ou Téléphone
                user_email = data.pop('user_email', None)
                client_phone = data.get('client_phone')
                user = None

                if user_email:
                    user = CustomUser.objects.filter(email=user_email).first()
                elif client_phone:
                    # On nettoie le numéro pour la recherche (enlever les espaces)
                    clean_phone = client_phone.replace(' ', '')
                    user = CustomUser.objects.filter(phone_number__icontains=clean_phone).first()

                # Optionnel : Associer à une commande existante
                order_id = data.pop('order', None)
                order_sequence = data.get('order_sequence')
                try:
                    order_sequence = int(order_sequence) if order_sequence else None
                except (TypeError, ValueError):
                    order_sequence = None
                order = None
                if order_id:
                    order = Order.objects.filter(id=order_id).first()
                elif user:
                    # Si on a trouvé un utilisateur, on cherche sa dernière commande en attente
                    order = (
                        Order.objects.filter(
                            user=user,
                            status__in=['pending', 'processing'],
                        )
                        .order_by('-order_date')
                        .first()
                    )

                try:
                    from datetime import date as date_cls
                    from .weight_utils import parse_weight_kg, parse_china_date

                    # Préparation des données de base
                    weight_volume = data.get('weight_volume')
                    weight_kg = parse_weight_kg(
                        data.get('weight_kg') if data.get('weight_kg') not in (None, '') else weight_volume
                    )
                    volume_cbm = None
                    raw_cbm = data.get('volume_cbm')
                    if raw_cbm not in (None, ''):
                        try:
                            from decimal import Decimal, InvalidOperation
                            volume_cbm = Decimal(str(raw_cbm).replace(',', '.'))
                        except (InvalidOperation, TypeError, ValueError):
                            volume_cbm = None
                    china_date = parse_china_date(
                        data.get('china_arrival_date') or data.get('arrival_date')
                    )
                    status_val = data.get('status', 'pending')
                    defaults = {
                        'status': status_val,
                        'current_location': data.get('current_location'),
                        'description': data.get('description'),
                        'client_name': data.get('client_name'),
                        'client_phone': data.get('client_phone'),
                        'weight_volume': weight_volume,
                        'warehouse_number': data.get('warehouse_number'),
                    }
                    if weight_kg is not None:
                        defaults['weight_kg'] = weight_kg
                    if volume_cbm is not None and volume_cbm >= 0:
                        defaults['volume_cbm'] = volume_cbm
                    if china_date is not None:
                        defaults['china_arrival_date'] = china_date
                    elif status_val == 'pending':
                        defaults['china_arrival_date'] = date_cls.today()


                    # Gestion de l'image en Base64
                    image_data = data.get('package_photo') or data.get('image')
                    if image_data and isinstance(image_data, str) and image_data.startswith('data:image'):
                        try:
                            format, imgstr = image_data.split(';base64,')
                            ext = format.split('/')[-1]
                            filename = f"parcel_{tracking}.{ext}"
                            defaults['image'] = ContentFile(base64.b64decode(imgstr), name=filename)
                        except Exception as e:
                            errors.append(f"Image corrompue pour {tracking}: {str(e)}")

                    parcel = None
                    if tracking:
                        parcel = Parcel.objects.filter(
                            tracking_number=tracking,
                        ).first()
                    if parcel is None and supplier_tracking:
                        parcel = Parcel.objects.filter(
                            supplier_tracking_number=supplier_tracking,
                        ).first()
                    if parcel is None and order and order_sequence:
                        parcel = Parcel.objects.filter(
                            order=order,
                            order_sequence=order_sequence,
                        ).first()

                    created = parcel is None
                    if created:
                        parcel = Parcel(
                            tracking_number=tracking or supplier_tracking,
                            order=order,
                            order_sequence=order_sequence,
                        )
                    elif (
                        tracking
                        and tracking != parcel.tracking_number
                        and not supplier_tracking
                    ):
                        # Le numéro Bujito reste stable ; le numéro reçu devient
                        # le suivi du fournisseur.
                        supplier_tracking = tracking

                    for field, value in defaults.items():
                        setattr(parcel, field, value)
                    if supplier_tracking:
                        parcel.supplier_tracking_number = supplier_tracking
                    if order and parcel.order_id != order.id:
                        parcel.order = order
                    if order_sequence and parcel.order_sequence != order_sequence:
                        parcel.order_sequence = order_sequence
                    parcel.save()

                    if created:
                        created_count += 1
                    else:
                        updated_count += 1
                except Exception as e:
                    errors.append(f"Erreur pour {tracking}: {str(e)}")

        uploaded = request.FILES.get('file')
        file_name = (request.data.get('file_name') or '').strip()
        if not file_name and uploaded is not None:
            file_name = uploaded.name
        if not file_name:
            file_name = 'import'

        ext = os.path.splitext(file_name)[1].lstrip('.').lower()
        batch = ImportBatch.objects.create(
            user=request.user,
            file_name=file_name,
            file_type=ext,
            created_count=created_count,
            updated_count=updated_count,
            failed_count=len(errors),
            message="Import bulk terminé",
        )
        if uploaded is not None:
            batch.file.save(uploaded.name, uploaded, save=True)

        return Response({
            "created": created_count,
            "updated": updated_count,
            "failed": len(errors),
            "errors": errors,
            "message": "Import bulk terminé",
            "import_id": batch.id,
        }, status=status.HTTP_200_OK)


class ImportBatchListView(APIView):
    """Liste des imports, filtrable par jour (?date=YYYY-MM-DD)."""
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        from datetime import datetime

        qs = ImportBatch.objects.select_related('user').all()
        date_str = (request.query_params.get('date') or '').strip()
        if date_str:
            try:
                day = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                return Response(
                    {"message": "Format de date invalide (YYYY-MM-DD)."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            qs = qs.filter(created_at__date=day)

        results = []
        for batch in qs[:200]:
            file_url = None
            if batch.file:
                file_url = request.build_absolute_uri(batch.file.url)
            results.append({
                "id": batch.id,
                "file_name": batch.file_name,
                "file_type": batch.file_type,
                "file_url": file_url,
                "created": batch.created_count,
                "updated": batch.updated_count,
                "failed": batch.failed_count,
                "matched": batch.matched_count,
                "message": batch.message,
                "created_at": batch.created_at.isoformat().replace('+00:00', 'Z'),
                "user_email": getattr(batch.user, 'email', None),
            })

        return Response({"results": results, "date": date_str or None}, status=status.HTTP_200_OK)

class ParcelImagesZipImportView(APIView):
    """Importe un ZIP d'images et les associe aux colis par nom de fichier.

    Convention :
    - TRACK.jpg / TRACK_1.jpg → photo principale
    - TRACK_2.jpg, TRACK_3.jpg → photos supplémentaires
    Variantes : TRACK-2.jpg, TRACK (2).jpg
    """
    permission_classes = [IsAuthenticated, IsAdminUser]

    _IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
    _SUFFIX_RE = re.compile(
        r'^(?P<base>.+?)(?:[_\-\s]+(?P<n>\d+)| \((?P<n2>\d+)\))$'
    )

    def _parse_stem(self, stem: str):
        raw = (stem or '').strip()
        if not raw:
            return '', 0
        match = self._SUFFIX_RE.match(raw)
        if not match:
            return raw, 0
        base = (match.group('base') or '').strip()
        n = match.group('n') or match.group('n2') or '0'
        try:
            index = int(n)
        except ValueError:
            index = 0
        # TRACK_1 = principale (comme TRACK sans suffixe)
        if index <= 1:
            return base or raw, 0
        return base or raw, index

    def _find_parcel(self, stem: str, basename: str):
        stem_clean = (stem or '').strip()
        base_clean = (basename or '').strip()
        candidates = [stem_clean, base_clean]
        for value in list(candidates):
            if not value:
                continue
            candidates.append(value.replace(' ', ''))
            candidates.append(value.replace('_', ''))
            candidates.append(value.replace('-', ''))

        seen = set()
        for key in candidates:
            if not key or key in seen:
                continue
            seen.add(key)
            parcel = (
                Parcel.objects.filter(tracking_number__iexact=key).first()
                or Parcel.objects.filter(supplier_tracking_number__iexact=key).first()
            )
            if parcel is not None:
                return parcel

        if stem_clean:
            parcel = (
                Parcel.objects.filter(tracking_number__icontains=stem_clean).first()
                or Parcel.objects.filter(
                    supplier_tracking_number__icontains=stem_clean
                ).first()
            )
            if parcel is not None:
                return parcel
        return None

    def post(self, request):
        from .models import ParcelImage

        zip_file = request.FILES.get('file')
        if not zip_file:
            return Response(
                {"detail": "Aucun fichier ZIP fourni."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not zip_file.name.lower().endswith('.zip'):
            return Response(
                {"detail": "Le fichier doit être une archive ZIP."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        matched = 0
        skipped = 0
        errors = []

        try:
            with zipfile.ZipFile(zip_file) as archive:
                entries = []
                for entry in archive.namelist():
                    if entry.endswith('/') or entry.startswith('__MACOSX/'):
                        continue

                    basename = os.path.basename(entry)
                    if not basename or basename.startswith('.'):
                        skipped += 1
                        continue

                    _, ext = os.path.splitext(basename)
                    if ext.lower() not in self._IMAGE_EXTENSIONS:
                        skipped += 1
                        continue

                    stem = os.path.splitext(basename)[0]
                    base_key, sort_order = self._parse_stem(stem)
                    entries.append((entry, basename, base_key, sort_order))

                entries.sort(key=lambda item: (item[2].lower(), item[3], item[1]))

                for entry, basename, base_key, sort_order in entries:
                    parcel = self._find_parcel(base_key, basename)
                    if parcel is None:
                        errors.append(f"Aucun colis trouvé pour l'image {basename}")
                        continue

                    try:
                        content = archive.read(entry)
                        file_content = ContentFile(content, name=basename)
                        if sort_order <= 0:
                            parcel.image.save(basename, file_content, save=True)
                        else:
                            existing = parcel.extra_images.filter(
                                sort_order=sort_order
                            ).first()
                            if existing:
                                existing.image.save(basename, file_content, save=True)
                            else:
                                ParcelImage.objects.create(
                                    parcel=parcel,
                                    image=file_content,
                                    sort_order=sort_order,
                                )
                        matched += 1
                    except Exception as exc:
                        errors.append(f"Erreur pour {basename}: {exc}")
        except zipfile.BadZipFile:
            return Response(
                {"detail": "Archive ZIP invalide."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        batch = ImportBatch.objects.create(
            user=request.user,
            file_name=zip_file.name,
            file_type='zip',
            matched_count=matched,
            failed_count=len(errors),
            message=f"{matched} image(s) associée(s) aux colis.",
        )
        try:
            zip_file.seek(0)
            batch.file.save(zip_file.name, zip_file, save=True)
        except Exception:
            pass

        return Response({
            "matched": matched,
            "skipped": skipped,
            "failed": len(errors),
            "errors": errors,
            "message": f"{matched} image(s) associée(s) aux colis.",
            "import_id": batch.id,
        }, status=status.HTTP_200_OK)


class ParcelBulkStatusView(APIView):
    """Changer le statut de plusieurs colis en une requête (admin)."""

    permission_classes = [IsAuthenticated, IsAdminUser]

    def post(self, request):
        from datetime import date as date_cls
        from .grouping import sync_completed_group_parcel_status

        tracking_numbers = request.data.get('tracking_numbers') or []
        new_status = request.data.get('status')
        if not isinstance(tracking_numbers, list) or not tracking_numbers:
            return Response(
                {"detail": "tracking_numbers requis (liste non vide)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        valid_statuses = {c[0] for c in Parcel.PARCEL_STATUS_CHOICES}
        if new_status not in valid_statuses:
            return Response(
                {"detail": f"Statut invalide. Valeurs: {sorted(valid_statuses)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        updated = []
        missing = []
        with transaction.atomic():
            for tn in tracking_numbers:
                tn = str(tn).strip()
                if not tn:
                    continue
                parcel = Parcel.objects.filter(tracking_number=tn).first()
                if parcel is None:
                    missing.append(tn)
                    continue
                old_status = parcel.status
                parcel.status = new_status
                if (
                    old_status != 'pending'
                    and new_status == 'pending'
                    and parcel.china_arrival_date is None
                ):
                    parcel.china_arrival_date = date_cls.today()
                parcel.save()
                sync_completed_group_parcel_status(parcel)
                updated.append(tn)

        return Response({
            "updated": updated,
            "updated_count": len(updated),
            "missing": missing,
            "status": new_status,
        }, status=status.HTTP_200_OK)


def _parcel_weight_for_mco(parcel) -> float:
    """Poids utilisable pour le packing MCO."""
    from .weight_utils import parse_weight_kg

    if parcel.weight_kg is not None:
        return float(parcel.weight_kg)
    parsed = parse_weight_kg(parcel.weight_volume)
    if parsed is not None:
        return float(parsed)
    # Fallback: répartition du poids consolidation completed
    cons = (
        parcel.consolidations.filter(status='completed', weight_kg__isnull=False)
        .order_by('-request_date')
        .first()
    )
    if cons and cons.weight_kg is not None:
        count = max(cons.parcels.count(), 1)
        return float(cons.weight_kg) / count
    return 0.0


def _parcel_cbm_for_mco(parcel) -> float:
    return float(parcel_volume_cbm(parcel))


def _batch_totals(parcels):
    from decimal import Decimal

    total_w = sum(_parcel_weight_for_mco(p) for p in parcels)
    total_v = sum(_parcel_cbm_for_mco(p) for p in parcels)
    return (
        Decimal(str(round(total_w, 3))),
        Decimal(str(round(total_v, 4))),
    )


def _next_mco_code() -> str:
    import re

    last = ShipmentBatch.objects.order_by('-id').first()
    n = 1
    if last and last.code:
        match = re.search(r'(\d+)', last.code)
        if match:
            n = int(match.group(1)) + 1
    return f'Expédition #{n}'


def _eligible_mco_parcels():
    """Colis avec expédition Bujito Digital payée, pas encore dans un MCO."""
    assigned_ids = (
        ShipmentBatch.objects.filter(parcels__isnull=False)
        .values_list('parcels__id', flat=True)
        .distinct()
    )
    return (
        Parcel.objects.filter(
            expeditions__mode='bujito_digital',
            expeditions__status='paid',
        )
        .exclude(id__in=assigned_ids)
        .distinct()
        .prefetch_related('expeditions', 'consolidations')
    )


def _resolve_parcel_owner(parcel):
    if parcel.order_id and parcel.order and parcel.order.user_id:
        return parcel.order.user
    cons = parcel.consolidations.order_by('-request_date').first()
    if cons and cons.user_id:
        return cons.user
    phone = "".join(ch for ch in (parcel.client_phone or "") if ch.isdigit())
    if phone and len(phone) >= 8:
        tail = phone[-9:] if len(phone) > 9 else phone
        match = (
            CustomUser.objects.filter(phone_number__icontains=tail)
            .order_by('id')
            .first()
        )
        if match is not None:
            return match
    return None


def _expedition_quote_or_create(request, *, create: bool):
    from decimal import Decimal

    tracking_numbers = request.data.get('tracking_numbers') or []
    parcel_ids = request.data.get('parcel_ids') or []
    mode = (request.data.get('mode') or '').strip().lower()
    transport_mode = request.data.get('transport_mode')
    category = request.data.get('shipping_category')
    forwarder_fee = request.data.get('forwarder_delivery_fee')
    forwarder_address = request.data.get('forwarder_address')
    volume_override = request.data.get('volume_cbm')
    weight_override = request.data.get('weight_kg')
    admin = is_app_admin(request.user)

    # Seul l'admin peut forcer poids / CBM ; le client ne fixe pas les frais transfert.
    if not admin:
        volume_override = None
        weight_override = None
        if mode == 'other_forwarder':
            forwarder_fee = None

    parcels = []
    if tracking_numbers:
        parcels = list(
            Parcel.objects.select_related('order__user').filter(
                tracking_number__in=tracking_numbers
            )
        )
    elif parcel_ids:
        parcels = list(
            Parcel.objects.select_related('order__user').filter(id__in=parcel_ids)
        )
    if not parcels:
        return Response(
            {"detail": "tracking_numbers ou parcel_ids requis."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not admin:
        for parcel in parcels:
            if not user_owns_parcel(request.user, parcel):
                return Response(
                    {
                        "detail": (
                            f"Le colis {parcel.tracking_number} "
                            "ne vous appartient pas."
                        )
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

    if create:
        busy = (
            ExpeditionRequest.objects.filter(
                parcels__in=parcels,
                status__in=['quoted', 'awaiting_payment', 'paid'],
            )
            .distinct()
            .exists()
        )
        if busy:
            return Response(
                {"detail": "Une demande d'expédition est déjà active pour ces colis."},
                status=status.HTTP_409_CONFLICT,
            )

    # Étoiles du client (bénéficiaire) pour la réduction aérienne 5★.
    if admin:
        owner_preview = _resolve_parcel_owner(parcels[0])
        client_stars = (
            int(getattr(owner_preview, 'stars', 0) or 0) if owner_preview else 0
        )
    else:
        client_stars = getattr(request.user, 'stars', 0) or 0

    try:
        quote = build_expedition_quote(
            parcels=parcels,
            mode=mode,
            transport_mode=transport_mode,
            shipping_category=category,
            forwarder_delivery_fee=forwarder_fee,
            forwarder_address=forwarder_address,
            volume_cbm_override=volume_override,
            weight_kg_override=weight_override,
            client_stars=client_stars,
        )
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    if not create:
        return Response(quote)

    if admin:
        owner = _resolve_parcel_owner(parcels[0])
        if owner is None:
            return Response(
                {"detail": "Impossible de déterminer le client du colis."},
                status=status.HTTP_400_BAD_REQUEST,
            )
    else:
        owner = request.user

    with transaction.atomic():
        exp = ExpeditionRequest.objects.create(
            user=owner,
            mode=quote['mode'],
            transport_mode=quote.get('transport_mode'),
            shipping_category=quote.get('shipping_category'),
            forwarder_address=quote.get('forwarder_address') or '',
            weight_kg=Decimal(str(quote['weight_kg'])),
            volume_cbm=Decimal(str(quote['volume_cbm'])),
            grouping_fee=Decimal(str(quote['grouping_fee'])),
            shipping_fee=Decimal(str(quote['shipping_fee'])),
            forwarder_delivery_fee=Decimal(str(quote['forwarder_delivery_fee'])),
            cbm_fee=Decimal(str(quote['cbm_fee'])),
            cbm_fee_advance=Decimal(str(quote['cbm_fee_advance'])),
            loyalty_discount_usd=Decimal(str(quote.get('loyalty_discount_usd') or 0)),
            total_due_now=Decimal(str(quote['total_due_now'])),
            was_grouped=quote['was_grouped'],
            status=quote.get('status') or 'awaiting_payment',
            created_by=request.user,
        )
        exp.parcels.set(parcels)
        if admin and volume_override is not None and len(parcels) == 1:
            parcels[0].volume_cbm = Decimal(str(quote['volume_cbm']))
            parcels[0].save(update_fields=['volume_cbm', 'last_updated'])

    try:
        if quote['mode'] == 'other_forwarder':
            notify_admins(
                "Transfert vers un autre transitaire",
                f"{owner.email} demande le transfert du/des colis "
                f"{', '.join(quote.get('tracking_numbers') or [])} "
                f"vers : {quote.get('forwarder_address') or '—'}. "
                f"Réf. #{exp.pk} — indiquez les frais de transfert.",
                type="expedition",
                reference_id=exp.pk,
                data={"type": "expedition", "expedition_id": str(exp.pk)},
            )
            send_fcm_notification(
                owner,
                "Demande envoyée",
                "Votre demande de transfert vers un autre transitaire a été "
                "transmise. Vous recevrez les frais de transfert à payer.",
                type="expedition",
                reference_id=exp.pk,
                data={"type": "expedition", "expedition_id": str(exp.pk)},
                translate=False,
            )
        elif admin:
            send_fcm_notification(
                owner,
                "Expédition à payer",
                f"Montant à payer : ${quote['total_due_now']:.2f}. "
                f"Réf. expédition #{exp.pk}.",
                type="payment",
                reference_id=exp.pk,
                data={"type": "expedition", "expedition_id": str(exp.pk)},
                translate=False,
            )
        else:
            notify_admins(
                "Expédition Bujito",
                f"{owner.email} a choisi l'expédition #{exp.pk} "
                f"({quote.get('transport_mode')}, ${quote['total_due_now']:.2f}).",
                type="expedition",
                reference_id=exp.pk,
                data={"type": "expedition", "expedition_id": str(exp.pk)},
            )
    except Exception:
        pass

    return Response(
        ExpeditionRequestSerializer(exp).data,
        status=status.HTTP_201_CREATED,
    )


class ExpeditionQuoteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        return _expedition_quote_or_create(request, create=False)


class ExpeditionListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = ExpeditionRequest.objects.prefetch_related('parcels').all()
        if not is_app_admin(request.user):
            qs = qs.filter(user=request.user)
        status_filter = (request.query_params.get('status') or '').strip()
        if status_filter:
            qs = qs.filter(status=status_filter)
        return Response(ExpeditionRequestSerializer(qs, many=True).data)

    def post(self, request):
        return _expedition_quote_or_create(request, create=True)


class ExpeditionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk, user):
        try:
            exp = ExpeditionRequest.objects.prefetch_related('parcels').get(pk=pk)
        except ExpeditionRequest.DoesNotExist:
            return None
        if not is_app_admin(user) and exp.user_id != user.id:
            return None
        return exp

    def get(self, request, pk):
        exp = self.get_object(pk, request.user)
        if exp is None:
            return Response({"detail": "Introuvable."}, status=status.HTTP_404_NOT_FOUND)
        return Response(ExpeditionRequestSerializer(exp).data)

    def patch(self, request, pk):
        """Admin : frais de transfert OU confirmation d'envoi (n° tracking)."""
        from decimal import Decimal, InvalidOperation
        from django.utils import timezone

        if not is_app_admin(request.user):
            return Response({"detail": "Accès refusé."}, status=status.HTTP_403_FORBIDDEN)
        exp = self.get_object(pk, request.user)
        if exp is None:
            return Response({"detail": "Introuvable."}, status=status.HTTP_404_NOT_FOUND)
        if exp.mode != 'other_forwarder':
            return Response(
                {"detail": "Seules les demandes « autre transitaire » acceptent ce PATCH."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if exp.status in ('shipped', 'cancelled'):
            return Response(
                {"detail": "Cette demande ne peut plus être modifiée."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Confirmation d'envoi vers le transitaire (après paiement).
        outbound = request.data.get('outbound_tracking_number')
        if outbound is not None:
            if exp.status != 'paid':
                return Response(
                    {
                        "detail": (
                            "La demande doit être payée avant de confirmer "
                            "l'envoi avec un n° de tracking."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            tracking = str(outbound).strip()
            if len(tracking) < 4:
                return Response(
                    {"detail": "Indiquez un numéro de tracking valide."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            with transaction.atomic():
                exp.outbound_tracking_number = tracking
                exp.status = 'shipped'
                exp.shipped_at = timezone.now()
                exp.save(
                    update_fields=[
                        'outbound_tracking_number',
                        'status',
                        'shipped_at',
                    ]
                )
                addr = (exp.forwarder_address or '').strip()
                for parcel in exp.parcels.select_for_update():
                    parcel.status = 'in_transit'
                    if addr:
                        parcel.current_location = addr[:255]
                    parcel.save(
                        update_fields=['status', 'current_location', 'last_updated']
                    )
            try:
                send_fcm_notification(
                    exp.user,
                    "Colis envoyé vers votre transitaire",
                    f"N° de suivi : {tracking}. Réf. expédition #{exp.pk}.",
                    type="expedition",
                    reference_id=exp.pk,
                    data={
                        "type": "expedition",
                        "expedition_id": str(exp.pk),
                        "outbound_tracking_number": tracking,
                    },
                    translate=False,
                )
            except Exception:
                pass
            return Response(ExpeditionRequestSerializer(exp).data)

        # Fixer les frais de transfert → paiement client.
        if exp.status == 'paid':
            return Response(
                {"detail": "Cette demande est déjà payée."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        raw = request.data.get('forwarder_delivery_fee')
        try:
            fee = Decimal(str(raw).replace(',', '.'))
        except (InvalidOperation, TypeError, ValueError):
            return Response(
                {"detail": "forwarder_delivery_fee invalide."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if fee <= 0:
            return Response(
                {"detail": "Les frais de transfert doivent être > 0."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        exp.forwarder_delivery_fee = fee.quantize(Decimal('0.01'))
        grouping = exp.grouping_fee or Decimal('0.00')
        exp.total_due_now = (grouping + exp.forwarder_delivery_fee).quantize(
            Decimal('0.01')
        )
        exp.status = 'awaiting_payment'
        exp.save(
            update_fields=[
                'forwarder_delivery_fee',
                'total_due_now',
                'status',
            ]
        )
        try:
            send_fcm_notification(
                exp.user,
                "Frais de groupage + transfert à payer",
                f"Montant : ${float(exp.total_due_now):.2f} "
                f"(groupage ${float(grouping):.2f} + transfert "
                f"${float(exp.forwarder_delivery_fee):.2f}). "
                f"Réf. expédition #{exp.pk}.",
                type="payment",
                reference_id=exp.pk,
                data={"type": "expedition", "expedition_id": str(exp.pk)},
                translate=False,
            )
        except Exception:
            pass
        return Response(ExpeditionRequestSerializer(exp).data)


class ShipmentBatchListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        batches = ShipmentBatch.objects.prefetch_related('parcels').all()
        return Response(
            ShipmentBatchSerializer(batches, many=True, context={'request': request}).data
        )

    def post(self, request):
        """Créer un lot manuel avec une liste de tracking_numbers."""
        tracking_numbers = request.data.get('tracking_numbers') or []
        notes = request.data.get('notes') or ''
        admin_description = request.data.get('admin_description') or ''
        if not tracking_numbers:
            return Response(
                {"detail": "tracking_numbers requis."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        parcels = list(
            Parcel.objects.filter(tracking_number__in=tracking_numbers)
        )
        if not parcels:
            return Response(
                {"detail": "Aucun colis trouvé."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        total_w, total_v = _batch_totals(parcels)
        batch = ShipmentBatch.objects.create(
            code=_next_mco_code(),
            total_weight_kg=total_w,
            total_volume_cbm=total_v,
            notes=notes,
            admin_description=admin_description,
        )
        if request.FILES.get('admin_photo'):
            batch.admin_photo = request.FILES['admin_photo']
            batch.save(update_fields=['admin_photo'])
        batch.parcels.set(parcels)
        return Response(
            ShipmentBatchSerializer(batch, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )


class ShipmentBatchGenerateView(APIView):
    """Génère des lots MCO 22–46 kg (greedy) à partir des colis éligibles."""

    permission_classes = [IsAuthenticated, IsAdminUser]
    MIN_KG = 22.0
    MAX_KG = 46.0

    def post(self, request):
        parcels = list(_eligible_mco_parcels())
        items = []
        for p in parcels:
            w = _parcel_weight_for_mco(p)
            if w > 0:
                items.append((p, w))
        items.sort(key=lambda x: x[1], reverse=True)

        batches_created = []
        current = []
        current_w = 0.0

        def flush(force=False):
            nonlocal current, current_w
            if not current:
                return
            if current_w < self.MIN_KG and not force:
                return
            ps = [p for p, _ in current]
            total_w, total_v = _batch_totals(ps)
            batch = ShipmentBatch.objects.create(
                code=_next_mco_code(),
                total_weight_kg=total_w,
                total_volume_cbm=total_v,
            )
            batch.parcels.set(ps)
            batches_created.append(batch)
            current = []
            current_w = 0.0

        for parcel, w in items:
            if w > self.MAX_KG:
                total_w, total_v = _batch_totals([parcel])
                batch = ShipmentBatch.objects.create(
                    code=_next_mco_code(),
                    total_weight_kg=total_w,
                    total_volume_cbm=total_v,
                    notes='Lot hors plage (colis > 46 kg)',
                )
                batch.parcels.set([parcel])
                batches_created.append(batch)
                continue
            if current_w + w > self.MAX_KG:
                flush(force=True)
            current.append((parcel, w))
            current_w += w

        flush(force=True)

        return Response({
            "created_count": len(batches_created),
            "batches": ShipmentBatchSerializer(
                batches_created, many=True, context={'request': request}
            ).data,
            "eligible_remaining": _eligible_mco_parcels().count(),
        }, status=status.HTTP_201_CREATED if batches_created else status.HTTP_200_OK)


class ShipmentBatchDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def get_object(self, pk):
        try:
            return ShipmentBatch.objects.prefetch_related('parcels').get(pk=pk)
        except ShipmentBatch.DoesNotExist:
            return None

    def get(self, request, pk):
        batch = self.get_object(pk)
        if batch is None:
            return Response({"detail": "Introuvable."}, status=status.HTTP_404_NOT_FOUND)
        return Response(
            ShipmentBatchSerializer(batch, context={'request': request}).data
        )

    def patch(self, request, pk):
        from django.utils import timezone
        from .grouping import sync_completed_group_parcel_status

        batch = self.get_object(pk)
        if batch is None:
            return Response({"detail": "Introuvable."}, status=status.HTTP_404_NOT_FOUND)

        update_fields = []
        new_status = request.data.get('status')
        if new_status:
            if new_status not in {c[0] for c in ShipmentBatch.STATUS_CHOICES}:
                return Response({"detail": "Statut MCO invalide."}, status=status.HTTP_400_BAD_REQUEST)
            batch.status = new_status
            update_fields.append('status')
            if new_status == 'shipped':
                batch.shipped_at = timezone.now()
                update_fields.append('shipped_at')
                for parcel in batch.parcels.all():
                    parcel.status = 'in_transit'
                    parcel.save(update_fields=['status', 'last_updated'])
                    sync_completed_group_parcel_status(parcel)

        if 'notes' in request.data:
            batch.notes = request.data.get('notes') or ''
            update_fields.append('notes')

        if 'admin_description' in request.data:
            batch.admin_description = request.data.get('admin_description') or ''
            update_fields.append('admin_description')

        if request.FILES.get('admin_photo'):
            batch.admin_photo = request.FILES['admin_photo']
            update_fields.append('admin_photo')

        if update_fields:
            batch.save(update_fields=list(dict.fromkeys(update_fields)))

        return Response(
            ShipmentBatchSerializer(batch, context={'request': request}).data
        )

