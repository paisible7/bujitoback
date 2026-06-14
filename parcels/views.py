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
