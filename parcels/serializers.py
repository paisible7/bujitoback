from rest_framework import serializers
from .models import Order, Parcel, Consolidation # Importez Consolidation
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

class ConsolidationSerializer(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(source='request_date', read_only=True)
    group_name = serializers.SerializerMethodField()
    user = UserSerializer(read_only=True) # Affiche les détails de l'utilisateur
    parcels = ParcelSerializer(many=True, read_only=True) # Affiche les colis groupés

    class Meta:
        model = Consolidation
        fields = ('id', 'group_name', 'user', 'parcels', 'request_date', 'created_at', 'status')
        read_only_fields = ('user', 'request_date', 'status')

    def get_group_name(self, obj):
        return f"Groupage #{obj.id}"

class ConsolidationCreateSerializer(serializers.Serializer):
    tracking_numbers = serializers.ListField(
        child=serializers.CharField(max_length=100),
        min_length=2, # Un groupage nécessite au moins 2 colis
        help_text="Liste des numéros de suivi des colis à grouper."
    )

    def validate_tracking_numbers(self, value):
        if len(value) > 500: # Limite de 500 colis comme spécifié
            raise serializers.ValidationError("Vous ne pouvez pas grouper plus de 500 colis à la fois.")
        return value

    def create(self, validated_data):
        # Cette méthode sera implémentée dans la vue pour gérer la logique de création de Consolidation
        # et la mise à jour des colis.
        pass

    def update(self, instance, validated_data):
        pass
