from rest_framework import serializers
from .models import Order, Parcel, Consolidation, ConsolidationParcelDecision, OrderImage
from users.serializers import UserSerializer # Pour inclure les détails de l'utilisateur si nécessaire
import logging
import os

logger = logging.getLogger(__name__)

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
            logger.debug('Parcel #%s (%s): pas de champ image', obj.pk, obj.tracking_number)
            return None

        try:
            relative = obj.image.url
        except ValueError as exc:
            logger.warning(
                'Parcel #%s (%s): image.url inaccessible: %s',
                obj.pk, obj.tracking_number, exc,
            )
            return None

        try:
            disk_path = obj.image.path
            exists = os.path.exists(disk_path)
            if not exists:
                logger.warning(
                    'Parcel #%s (%s): fichier manquant sur disque path=%s url=%s',
                    obj.pk, obj.tracking_number, disk_path, relative,
                )
            else:
                logger.debug(
                    'Parcel #%s (%s): image OK path=%s url=%s',
                    obj.pk, obj.tracking_number, disk_path, relative,
                )
        except Exception as exc:
            logger.warning(
                'Parcel #%s (%s): impossible de résoudre image.path: %s (url=%s)',
                obj.pk, obj.tracking_number, exc, relative,
            )

        request = self.context.get('request')
        if request is not None:
            absolute = request.build_absolute_uri(relative)
            logger.info(
                'Parcel #%s image URL absolue=%s (Host=%s)',
                obj.pk, absolute, request.get_host(),
            )
            return absolute

        logger.warning(
            'Parcel #%s: pas de request dans le serializer, URL relative=%s',
            obj.pk, relative,
        )
        return relative


class OrderImageSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = OrderImage
        fields = ('id', 'image', 'uploaded_at')

    def get_image(self, obj):
        if not obj.image:
            logger.debug('OrderImage #%s: pas d\'image', obj.pk)
            return None
        try:
            relative = obj.image.url
        except ValueError as exc:
            logger.warning('OrderImage #%s: image.url inaccessible: %s', obj.pk, exc)
            return None
        try:
            if not os.path.exists(obj.image.path):
                logger.warning(
                    'OrderImage #%s: fichier manquant path=%s url=%s',
                    obj.pk, obj.image.path, relative,
                )
        except Exception as exc:
            logger.warning('OrderImage #%s: path error: %s', obj.pk, exc)

        request = self.context.get('request')
        if request is not None:
            absolute = request.build_absolute_uri(relative)
            logger.info('OrderImage #%s URL absolue=%s', obj.pk, absolute)
            return absolute
        return relative

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
    user = UserSerializer(read_only=True)
    parcels = serializers.SerializerMethodField()

    class Meta:
        model = Consolidation
        fields = ('id', 'group_name', 'user', 'parcels', 'request_date', 'created_at', 'status')
        read_only_fields = ('user', 'request_date', 'status')

    def get_group_name(self, obj):
        return f"{_('Groupage')} #{obj.id}"

    def get_parcels(self, obj):
        decisions = {
            d.parcel_id: d.decision
            for d in obj.parcel_decisions.all()
        }
        result = []
        for parcel in obj.parcels.all():
            data = ParcelSerializer(parcel, context=self.context).data
            data['decision'] = decisions.get(parcel.id, 'pending')
            result.append(data)
        return result


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
    parcel_id = serializers.IntegerField(required=False)
    decision = serializers.ChoiceField(
        choices=['pending', 'accepted', 'rejected'],
        required=False,
    )

    class Meta:
        model = Consolidation
        fields = ('status', 'parcel_id', 'decision')

    def validate_status(self, value):
        allowed = {'processing', 'completed', 'cancelled'}
        if value not in allowed:
            raise serializers.ValidationError(
                "Statut invalide. Valeurs autorisées : processing, completed, cancelled."
            )
        if self.instance and self.instance.status in ('completed', 'cancelled'):
            raise serializers.ValidationError("Ce groupage est déjà finalisé.")
        return value

    def validate(self, attrs):
        has_status = 'status' in attrs
        has_parcel = 'parcel_id' in attrs
        has_decision = 'decision' in attrs

        if has_parcel != has_decision:
            raise serializers.ValidationError(
                "Indiquez parcel_id et decision ensemble pour valider un colis."
            )
        if not has_status and not has_parcel:
            raise serializers.ValidationError(
                "Indiquez un status ou une décision de colis (parcel_id + decision)."
            )

        if has_parcel and self.instance is not None:
            if self.instance.status in ('completed', 'cancelled'):
                raise serializers.ValidationError("Ce groupage est déjà finalisé.")
            if not self.instance.parcels.filter(pk=attrs['parcel_id']).exists():
                raise serializers.ValidationError("Ce colis ne fait pas partie de ce groupage.")

        return attrs

    def update(self, instance, validated_data):
        from django.db import transaction

        parcel_id = validated_data.pop('parcel_id', None)
        decision = validated_data.pop('decision', None)
        new_status = validated_data.get('status')

        with transaction.atomic():
            if parcel_id is not None and decision is not None:
                ConsolidationParcelDecision.objects.update_or_create(
                    consolidation=instance,
                    parcel_id=parcel_id,
                    defaults={'decision': decision},
                )

            if new_status is not None:
                instance.status = new_status
                instance.save()
                if new_status == 'completed':
                    decisions = {
                        d.parcel_id: d.decision
                        for d in instance.parcel_decisions.all()
                    }
                    for parcel in list(instance.parcels.all()):
                        # Sans décision explicite → validé (rétrocompat)
                        parcel_decision = decisions.get(parcel.id, 'accepted')
                        if parcel_decision == 'accepted' and parcel.status != 'consolidated':
                            parcel.status = 'consolidated'
                            parcel.save(update_fields=['status', 'last_updated'])
                        elif parcel_decision == 'rejected':
                            instance.parcels.remove(parcel)
                            ConsolidationParcelDecision.objects.filter(
                                consolidation=instance,
                                parcel=parcel,
                            ).delete()

        return instance
