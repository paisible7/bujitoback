from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView # Import de APIView
from rest_framework.permissions import IsAuthenticated
from .models import Order, Parcel
from .serializers import OrderSerializer, ParcelSerializer, OrderCreateSerializer
from users.permissions import IsAdminUser # Import de la permission personnalisée

class OrderListCreateView(generics.ListCreateAPIView):
    queryset = Order.objects.all()
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return OrderCreateSerializer
        return OrderSerializer

    def get_queryset(self):
        # Si l'utilisateur est admin, il voit toutes les commandes
        if self.request.user.is_authenticated and self.request.user.role == 'admin':
            return Order.objects.all()
        # Sinon, il ne voit que ses propres commandes
        return Order.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        # L'utilisateur de la commande est automatiquement défini comme l'utilisateur connecté
        serializer.save(user=self.request.user)
    
    # Surcharge de la méthode create pour utiliser OrderSerializer pour la réponse
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        
        # Utilise OrderSerializer pour la réponse afin d'inclure tous les champs
        headers = self.get_success_headers(serializer.data)
        full_serializer = OrderSerializer(serializer.instance) # Sérialise l'instance complète
        return Response(full_serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class OrderDetailView(generics.RetrieveAPIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]
    queryset = Order.objects.all() # Permet de récupérer l'objet par son ID

    def get_object(self):
        obj = super().get_object()
        # Seul le propriétaire de la commande ou un admin peut la voir
        if obj.user != self.request.user and self.request.user.role != 'admin':
            self.permission_denied(self.request)
        return obj

class ParcelListCreateView(generics.ListCreateAPIView):
    serializer_class = ParcelSerializer
    permission_classes = [IsAdminUser] # Utilise la permission IsAdminUser

    def get_queryset(self):
        # Si l'utilisateur est admin, il voit tous les colis
        if self.request.user.is_authenticated and self.request.user.role == 'admin':
            return Parcel.objects.all()
        # Sinon, il ne voit que les colis liés à ses commandes
        return Parcel.objects.filter(order__user=self.request.user)

    def perform_create(self, serializer):
        # La création de colis est gérée par IsAdminUser, donc pas besoin de vérifier ici
        serializer.save()

class ParcelDetailView(generics.RetrieveAPIView):
    serializer_class = ParcelSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'tracking_number' # Permet de rechercher par numéro de suivi
    queryset = Parcel.objects.all()

    def get_object(self):
        obj = super().get_object()
        # Seul le propriétaire du colis (via la commande) ou un admin peut le voir
        if obj.order and obj.order.user != self.request.user and self.request.user.role != 'admin':
            self.permission_denied(self.request)
        elif not obj.order and self.request.user.role != 'admin': # Si le colis n'est pas lié à une commande, seul l'admin peut le voir
            self.permission_denied(self.request)
        return obj

class ParcelTrackView(generics.RetrieveAPIView):
    serializer_class = ParcelSerializer
    permission_classes = [IsAuthenticated] # Ou IsAuthenticatedOrReadOnly si vous voulez que les non-connectés puissent suivre
    lookup_field = 'tracking_number'
    queryset = Parcel.objects.all()

    def get_object(self):
        tracking_number = self.kwargs.get(self.lookup_field)
        try:
            parcel = Parcel.objects.get(tracking_number=tracking_number)
            # Tout utilisateur authentifié peut suivre un colis s'il connaît le numéro de suivi
            # Si vous voulez restreindre l'accès aux colis non liés à l'utilisateur,
            # vous pouvez ajouter une logique ici. Pour l'instant, tout connecté peut suivre.
            return parcel
        except Parcel.DoesNotExist:
            raise status.HTTP_404_NOT_FOUND

class ParcelGroupView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        tracking_numbers = request.data.get('tracking_numbers')
        if not tracking_numbers or not isinstance(tracking_numbers, list):
            return Response(
                {"detail": "Une liste de numéros de suivi est requise."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Ici, vous implémenteriez la logique réelle de groupage.
        # Cela pourrait impliquer de :
        # 1. Vérifier l'existence des colis.
        # 2. Vérifier que l'utilisateur est propriétaire des colis (si applicable).
        # 3. Créer une nouvelle commande de groupage ou mettre à jour des colis existants.
        # Pour l'instant, nous simulons juste un succès.
        
        return Response(
            {"message": "Demande de groupage reçue avec succès.", "tracking_numbers": tracking_numbers},
            status=status.HTTP_200_OK
        )