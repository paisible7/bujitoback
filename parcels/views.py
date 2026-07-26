import base64
from django.core.files.base import ContentFile
from rest_framework import generics, status, filters
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.db import transaction # Pour les opérations atomiques
from django.http import Http404
from .models import Order, Parcel, Consolidation # Importez Consolidation
from .serializers import (
    OrderSerializer,
    ParcelSerializer,
    OrderCreateSerializer,
    ConsolidationSerializer, # Importez le sérialiseur de Consolidation
    ConsolidationCreateSerializer # Importez le sérialiseur de création de Consolidation
)
from users.permissions import IsAdminUser
from users.models import CustomUser

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
        if self.request.user.is_authenticated and self.request.user.role == 'admin':
            return Order.objects.all()
        return Order.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        
        headers = self.get_success_headers(serializer.data)
        full_serializer = OrderSerializer(serializer.instance)
        return Response(full_serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class OrderDetailView(generics.RetrieveAPIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]
    queryset = Order.objects.all()

    def get_object(self):
        obj = super().get_object()
        if obj.user != self.request.user and self.request.user.role != 'admin':
            self.permission_denied(self.request)
        return obj

class ParcelListCreateView(generics.ListCreateAPIView):
    serializer_class = ParcelSerializer
    permission_classes = [IsAuthenticated] # IsAdminUser checks method, but we filter queryset
    filter_backends = [filters.SearchFilter]
    search_fields = ['tracking_number', 'description', 'current_location']

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return Parcel.objects.none()
        if self.request.user.role == 'admin':
            return Parcel.objects.all()
        return Parcel.objects.filter(order__user=self.request.user)

    def perform_create(self, serializer):
        # Still check for admin for POST via IsAdminUser if we use it,
        # or handle it here if we use IsAuthenticated.
        if self.request.user.role != 'admin':
            self.permission_denied(self.request)
        serializer.save()

class ParcelDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ParcelSerializer
    permission_classes = [IsAuthenticated]
    queryset = Parcel.objects.all()
    lookup_field = 'tracking_number' # Important pour matcher l'URL

    def get_object(self):
        obj = super().get_object()
        if self.request.user.role == 'admin':
            return obj
        if obj.order and obj.order.user == self.request.user:
            return obj
        self.permission_denied(self.request)

    def perform_update(self, serializer):
        if self.request.user.role != 'admin':
            self.permission_denied(self.request)
        serializer.save()

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

        user = request.user
        eligible_statuses = ['pending', 'in_transit'] # Statuts éligibles au groupage

        with transaction.atomic():
            # 1. Récupérer les colis et vérifier l'appartenance et l'éligibilité
            parcels_to_group = []
            for tn in tracking_numbers:
                try:
                    parcel = Parcel.objects.get(tracking_number=tn)
                    # Vérifier que le colis appartient à l'utilisateur ou est sans commande (si votre logique le permet)
                    # Pour l'instant, on suppose qu'il doit être lié à une commande de l'utilisateur
                    if parcel.order and parcel.order.user != user:
                        return Response(
                            {"detail": f"Le colis {tn} n'appartient pas à l'utilisateur."},
                            status=status.HTTP_403_FORBIDDEN
                        )
                    if parcel.status not in eligible_statuses:
                        return Response(
                            {"detail": f"Le colis {tn} n'est pas dans un statut éligible au groupage (doit être 'En attente' ou 'En transit')."},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    parcels_to_group.append(parcel)
                except Parcel.DoesNotExist:
                    return Response(
                        {"detail": f"Le colis avec le numéro de suivi {tn} n'existe pas."},
                        status=status.HTTP_404_NOT_FOUND
                    )
            
            # 2. Créer la demande de groupage (Consolidation)
            consolidation = Consolidation.objects.create(user=user, status='processing')
            consolidation.parcels.set(parcels_to_group) # Ajoute tous les colis au groupage

            # 3. Mettre à jour le statut des colis groupés
            for parcel in parcels_to_group:
                parcel.status = 'consolidated' # Nouveau statut pour les colis groupés
                parcel.save()

            # 4. Retourner la consolidation créée
            response_serializer = ConsolidationSerializer(consolidation)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class ConsolidationListView(generics.ListAPIView):
    serializer_class = ConsolidationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_authenticated and self.request.user.role == 'admin':
            return Consolidation.objects.all()
        return Consolidation.objects.filter(user=self.request.user)


class ConsolidationDetailView(generics.RetrieveAPIView):
    serializer_class = ConsolidationSerializer
    permission_classes = [IsAuthenticated]
    queryset = Consolidation.objects.all()

    def get_object(self):
        obj = super().get_object()
        if obj.user != self.request.user and self.request.user.role != 'admin':
            self.permission_denied(self.request)
        return obj

class ParcelBulkImportView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def post(self, request):
        parcels_data = request.data.get('parcels', [])
        created_count = 0
        updated_count = 0
        errors = []

        with transaction.atomic():
            for data in parcels_data:
                tracking = data.get('tracking_number')
                if not tracking:
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
                order = None
                if order_id:
                    order = Order.objects.filter(id=order_id).first()
                elif user:
                    # Si on a trouvé un utilisateur, on cherche sa dernière commande en attente
                    order = Order.objects.filter(user=user, status='pending').first()

                try:
                    # Préparation des données de base
                    defaults = {
                        'status': data.get('status', 'pending'),
                        'current_location': data.get('current_location'),
                        'description': data.get('description'),
                        'client_name': data.get('client_name'),
                        'client_phone': data.get('client_phone'),
                        'weight_volume': data.get('weight_volume'),
                        'warehouse_number': data.get('warehouse_number'),
                    }

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

                    parcel, created = Parcel.objects.update_or_create(
                        tracking_number=tracking,
                        defaults=defaults
                    )

                    # Mise à jour de l'ordre si trouvé (uniquement si pas déjà lié ou si admin force)
                    if order and (parcel.order is None or parcel.order != order):
                        parcel.order = order
                        parcel.save()
                    elif user and parcel.order is None:
                        # Si on a un user mais pas d'order, on pourrait créer une commande fantôme ou juste stocker l'info
                        pass

                    if created:
                        created_count += 1
                    else:
                        updated_count += 1
                except Exception as e:
                    errors.append(f"Erreur pour {tracking}: {str(e)}")

        return Response({
            "created": created_count,
            "updated": updated_count,
            "failed": len(errors),
            "errors": errors,
            "message": "Import bulk terminé"
        }, status=status.HTTP_200_OK)
