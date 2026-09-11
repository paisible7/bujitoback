import base64
import os
import re
import zipfile
from django.core.files.base import ContentFile
from rest_framework import generics, status, filters
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.db import transaction # Pour les opérations atomiques
from django.http import Http404
from .models import Order, Parcel, Consolidation, OrderImage, ImportBatch, ShipmentBatch # Importez Consolidation
from .serializers import (
    OrderSerializer,
    ParcelSerializer,
    OrderCreateSerializer,
    OrderQuoteSerializer,
    ConsolidationSerializer,
    ConsolidationCreateSerializer,
    ConsolidationUpdateSerializer,
    ShipmentBatchSerializer,
)
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
        if self.request.method in ('GET', 'HEAD', 'OPTIONS'):
            if obj.user != self.request.user and (not is_app_admin(self.request.user)):
                self.permission_denied(self.request)
            return obj
        if (not is_app_admin(self.request.user)):
            self.permission_denied(self.request)
        return obj

    def get_serializer_class(self):
        if self.request.method in ('PUT', 'PATCH'):
            data = self.request.data
            # Devis admin : product_items + frais
            if (
                'product_items' in data
                or 'withdrawal_fee' in data
                or 'commission_fee' in data
            ):
                return OrderQuoteSerializer
        return OrderSerializer

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer_class = self.get_serializer_class()

        if serializer_class is OrderQuoteSerializer:
            serializer = OrderQuoteSerializer(instance, data=request.data, partial=partial)
            serializer.is_valid(raise_exception=True)
            order = serializer.save()
            return Response(OrderSerializer(order, context={'request': request}).data)

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
        return queryset.filter(order__user=self.request.user)

    def perform_create(self, serializer):
        # Still check for admin for POST via IsAdminUser if we use it,
        # or handle it here if we use IsAuthenticated.
        if (not is_app_admin(self.request.user)):
            self.permission_denied(self.request)
        serializer.save()

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
        if obj.order and obj.order.user == self.request.user:
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
    http_method_names = ['post'] # Ajout explicite de la méthode POST

    def post(self, request, *args, **kwargs):
        serializer = ConsolidationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tracking_numbers = serializer.validated_data['tracking_numbers']
        client_note = serializer.validated_data.get('client_note') or ''

        user = request.user
        eligible_statuses = ['pending']  # Uniquement « en attente » avant groupage

        with transaction.atomic():
            parcels_to_group = []
            for tn in tracking_numbers:
                try:
                    parcel = Parcel.objects.get(tracking_number=tn)
                    if not parcel.order or parcel.order.user != user:
                        return Response(
                            {"detail": f"Le colis {tn} n'appartient pas à l'utilisateur."},
                            status=status.HTTP_403_FORBIDDEN
                        )
                    if parcel.status not in eligible_statuses:
                        return Response(
                            {"detail": f"Le colis {tn} n'est pas éligible au groupage (doit être « En attente »)."},
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
                except Parcel.DoesNotExist:
                    return Response(
                        {"detail": f"Le colis avec le numéro de suivi {tn} n'existe pas."},
                        status=status.HTTP_404_NOT_FOUND
                    )

            consolidation = Consolidation.objects.create(
                user=user,
                status='pending',
                client_note=client_note,
            )
            consolidation.parcels.set(parcels_to_group)

            # Notifier après liaison M2M (post_save à la création voit 0 colis).
            parcel_count = len(parcels_to_group)
            admin_body = (
                f"{user.email} demande le groupage de {parcel_count} colis "
                f"(#{consolidation.pk})."
            )
            if client_note:
                admin_body = f"{admin_body} Description: {client_note}"
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

            response_serializer = ConsolidationSerializer(consolidation)
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
            return ConsolidationUpdateSerializer
        return ConsolidationSerializer

    def get_object(self):
        obj = super().get_object()
        if self.request.method == 'GET':
            if obj.user != self.request.user and (not is_app_admin(self.request.user)):
                self.permission_denied(self.request)
            return obj
        if (not is_app_admin(self.request.user)):
            self.permission_denied(self.request)
        return obj

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


def _next_mco_code() -> str:
    import re

    last = ShipmentBatch.objects.order_by('-id').first()
    n = 1
    if last and last.code:
        match = re.search(r'(\d+)', last.code)
        if match:
            n = int(match.group(1)) + 1
    return f'MCO {n}'


def _eligible_mco_parcels():
    """Colis groupés, consolidation completed avec fee, pas encore dans un MCO."""
    assigned_ids = (
        ShipmentBatch.objects.filter(parcels__isnull=False)
        .values_list('parcels__id', flat=True)
        .distinct()
    )
    return (
        Parcel.objects.filter(status='consolidated')
        .filter(
            consolidations__status='completed',
            consolidations__grouping_fee__isnull=False,
        )
        .exclude(id__in=assigned_ids)
        .distinct()
        .prefetch_related('consolidations')
    )


class ShipmentBatchListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        batches = ShipmentBatch.objects.prefetch_related('parcels').all()
        return Response(ShipmentBatchSerializer(batches, many=True).data)

    def post(self, request):
        """Créer un lot manuel avec une liste de tracking_numbers."""
        from decimal import Decimal

        tracking_numbers = request.data.get('tracking_numbers') or []
        notes = request.data.get('notes') or ''
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
        total = sum(_parcel_weight_for_mco(p) for p in parcels)
        batch = ShipmentBatch.objects.create(
            code=_next_mco_code(),
            total_weight_kg=Decimal(str(round(total, 3))),
            notes=notes,
        )
        batch.parcels.set(parcels)
        return Response(
            ShipmentBatchSerializer(batch).data,
            status=status.HTTP_201_CREATED,
        )


class ShipmentBatchGenerateView(APIView):
    """Génère des lots MCO 22–46 kg (greedy) à partir des colis éligibles."""

    permission_classes = [IsAuthenticated, IsAdminUser]
    MIN_KG = 22.0
    MAX_KG = 46.0

    def post(self, request):
        from decimal import Decimal

        parcels = list(_eligible_mco_parcels())
        items = []
        for p in parcels:
            w = _parcel_weight_for_mco(p)
            if w > 0:
                items.append((p, w))
        # Plus lourds d'abord pour un packing plus stable
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
            batch = ShipmentBatch.objects.create(
                code=_next_mco_code(),
                total_weight_kg=Decimal(str(round(current_w, 3))),
            )
            batch.parcels.set([p for p, _ in current])
            batches_created.append(batch)
            current = []
            current_w = 0.0

        for parcel, w in items:
            if w > self.MAX_KG:
                # Colis trop lourd seul → lot dédié (admin pourra ajuster)
                batch = ShipmentBatch.objects.create(
                    code=_next_mco_code(),
                    total_weight_kg=Decimal(str(round(w, 3))),
                    notes='Lot hors plage (colis > 46 kg)',
                )
                batch.parcels.set([parcel])
                batches_created.append(batch)
                continue
            if current_w + w > self.MAX_KG:
                flush(force=True)
            current.append((parcel, w))
            current_w += w
            if current_w >= self.MIN_KG:
                # Continuer à remplir jusqu'à MAX, flush si prochain ne rentre pas
                pass

        flush(force=True)

        return Response({
            "created_count": len(batches_created),
            "batches": ShipmentBatchSerializer(batches_created, many=True).data,
            "eligible_remaining": _eligible_mco_parcels().count(),
        }, status=status.HTTP_201_CREATED if batches_created else status.HTTP_200_OK)


class ShipmentBatchDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get_object(self, pk):
        try:
            return ShipmentBatch.objects.prefetch_related('parcels').get(pk=pk)
        except ShipmentBatch.DoesNotExist:
            return None

    def get(self, request, pk):
        batch = self.get_object(pk)
        if batch is None:
            return Response({"detail": "Introuvable."}, status=status.HTTP_404_NOT_FOUND)
        return Response(ShipmentBatchSerializer(batch).data)

    def patch(self, request, pk):
        from django.utils import timezone
        from .grouping import sync_completed_group_parcel_status

        batch = self.get_object(pk)
        if batch is None:
            return Response({"detail": "Introuvable."}, status=status.HTTP_404_NOT_FOUND)

        new_status = request.data.get('status')
        if new_status:
            if new_status not in {c[0] for c in ShipmentBatch.STATUS_CHOICES}:
                return Response({"detail": "Statut MCO invalide."}, status=status.HTTP_400_BAD_REQUEST)
            batch.status = new_status
            if new_status == 'shipped':
                batch.shipped_at = timezone.now()
                for parcel in batch.parcels.all():
                    parcel.status = 'in_transit'
                    parcel.save(update_fields=['status', 'last_updated'])
                    sync_completed_group_parcel_status(parcel)
            batch.save()

        if 'notes' in request.data:
            batch.notes = request.data.get('notes') or ''
            batch.save(update_fields=['notes'])

        return Response(ShipmentBatchSerializer(batch).data)

