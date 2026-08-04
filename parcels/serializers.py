from rest_framework import serializers
from .models import Order, Parcel, Consolidation, OrderImage # Importez Consolidation
from users.serializers import UserSerializer # Pour inclure les détails de l'utilisateur si nécessaire

class ParcelSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()
    package_photo = serializers.SerializerMethodField()

    class Meta:
        model = Parcel
        fields = [
            'id', 'tracking_number', 'status', 'current_location',
            'client_name', 'client_phone', 'weight_volume',
            'warehouse_number', 'description', 'image', 'package_photo',
            'last_updated', 'order',
        ]
        read_only_fields = ('last_updated',)

    def get_image(self, obj):
        return self._absolute_image_url(obj)

    def get_package_photo(self, obj):
        return self._absolute_image_url(obj)

    def _absolute_image_url(self, obj):
        if not obj.image:
            return None
        request = self.context.get('request')
        url = obj.image.url
        if request is not None:
            return request.build_absolute_uri(url)
        return url

class OrderImageSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = OrderImage
        fields = ('id', 'image', 'uploaded_at')

    def get_image(self, obj):
        if not obj.image:
            return None
        request = self.context.get('request')
        url = obj.image.url
        if request is not None:
            return request.build_absolute_uri(url)
        return url


class OrderSerializer(serializers.ModelSerializer):
    parcels = ParcelSerializer(many=True, read_only=True)
    images = OrderImageSerializer(many=True, read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_full_name = serializers.CharField(source='user.full_name', read_only=True)
    product_links_list = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            'id', 'user', 'user_email', 'user_full_name', 'order_date', 'status',
            'total_amount', 'client_name', 'client_phone', 'country', 'city',
            'product_links', 'product_links_list', 'quantity', 'comment',
            'parcels', 'images',
        )
        read_only_fields = ('user', 'order_date')

    def get_product_links_list(self, obj):
        raw = obj.product_links
        if not raw:
            return []
        try:
            import json
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
        except Exception:
            pass
        return [line.strip() for line in str(raw).splitlines() if line.strip()]


class OrderCreateSerializer(serializers.ModelSerializer):
    product_links = serializers.JSONField(required=False, allow_null=True)
    client_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    client_phone = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    country = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    city = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    quantity = serializers.IntegerField(required=False, min_value=1)
    comment = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = Order
        fields = [
            'total_amount', 'status', 'client_name', 'client_phone',
            'country', 'city', 'product_links', 'quantity', 'comment',
        ]
        extra_kwargs = {'status': {'required': False}}

    def create(self, validated_data):
        import json
        links = validated_data.pop('product_links', None)
        if links is not None and not isinstance(links, str):
            validated_data['product_links'] = json.dumps(links, ensure_ascii=False)
        elif isinstance(links, str):
            # Multipart peut envoyer une string JSON
            try:
                parsed = json.loads(links)
                validated_data['product_links'] = json.dumps(parsed, ensure_ascii=False) if not isinstance(parsed, str) else links
            except Exception:
                validated_data['product_links'] = links
        return super().create(validated_data)

from django.utils.translation import gettext as _

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
        return f"{_('Groupage')} #{obj.id}"

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


class ConsolidationUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Consolidation
        fields = ('status',)

    def validate_status(self, value):
        allowed = {'processing', 'completed', 'cancelled'}
        if value not in allowed:
            raise serializers.ValidationError(
                "Statut invalide. Valeurs autorisées : processing, completed, cancelled."
            )
        if self.instance and self.instance.status in ('completed', 'cancelled'):
            raise serializers.ValidationError("Ce groupage est déjà finalisé.")
        return value

    def update(self, instance, validated_data):
        from django.db import transaction

        new_status = validated_data['status']
        with transaction.atomic():
            instance.status = new_status
            instance.save()
            if new_status == 'completed':
                for parcel in instance.parcels.all():
                    if parcel.status != 'consolidated':
                        parcel.status = 'consolidated'
                        parcel.save(update_fields=['status', 'last_updated'])
        return instance
