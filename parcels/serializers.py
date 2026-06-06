from rest_framework import serializers
from .models import Order, Parcel
from users.serializers import UserSerializer # Pour inclure les détails de l'utilisateur si nécessaire

class ParcelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Parcel
        fields = '__all__' # Inclut tous les champs du modèle Parcel

class OrderSerializer(serializers.ModelSerializer):
    parcels = ParcelSerializer(many=True, read_only=True) # Pour afficher les colis liés à la commande

    class Meta:
        model = Order
        fields = '__all__' # Inclut tous les champs du modèle Order
        read_only_fields = ('user', 'order_date') # L'utilisateur et la date sont définis automatiquement

class OrderCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ['total_amount', 'status'] # Champs que l'on peut définir à la création
        extra_kwargs = {'status': {'required': False}} # Le statut n'est pas obligatoire, il a une valeur par défaut
