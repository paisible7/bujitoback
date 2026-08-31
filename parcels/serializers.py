from rest_framework import serializers
from .models import Order, Parcel, Consolidation, ConsolidationParcelDecision, OrderImage
from users.serializers import UserSerializer # Pour inclure les détails de l'utilisateur si nécessaire
from .media_urls import absolute_media_url
from .quote_utils import (
    parse_product_items,
    dump_product_items,
    normalize_incoming_links,
    compute_quote_total,
    total_items_quantity,
)

class ParcelSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()
    package_photo = serializers.SerializerMethodField()
    user_email = serializers.SerializerMethodField()

    class Meta:
        model = Parcel
        fields = [
            'id', 'tracking_number', 'supplier_tracking_number',
            'order_sequence', 'status', 'current_location',
            'client_name', 'client_phone', 'weight_volume',
            'warehouse_number', 'description', 'image', 'package_photo',
            'last_updated', 'order', 'user_email',
        ]
        read_only_fields = ('last_updated',)

    def get_image(self, obj):
        return self._absolute_image_url(obj)

    def get_package_photo(self, obj):
        return self._absolute_image_url(obj)

    def get_user_email(self, obj):
        if obj.order_id and obj.order:
            return obj.order.user.email
        return None

    def _absolute_image_url(self, obj):
        return absolute_media_url(
            obj.image,
            self.context.get('request'),
            label=f'Parcel #{obj.pk} ({obj.tracking_number})',
        )


class OrderImageSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = OrderImage
        fields = ('id', 'image', 'uploaded_at')

    def get_image(self, obj):
        return absolute_media_url(
            obj.image,
            self.context.get('request'),
            label=f'OrderImage #{obj.pk}',
        )

class OrderSerializer(serializers.ModelSerializer):
    parcels = ParcelSerializer(many=True, read_only=True)
    images = OrderImageSerializer(many=True, read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_full_name = serializers.CharField(source='user.full_name', read_only=True)
    product_links_list = serializers.SerializerMethodField()
    product_items = serializers.SerializerMethodField()
    payment_completed = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            'id', 'user', 'user_email', 'user_full_name', 'order_date', 'status',
            'total_amount', 'withdrawal_fee', 'quote_ready',
            'expected_parcel_count', 'payment_completed',
            'client_name', 'client_phone', 'country', 'city',
            'product_links', 'product_links_list', 'product_items',
            'quantity', 'comment',
            'parcels', 'images',
        )
        read_only_fields = (
            'user',
            'order_date',
            'total_amount',
            'quote_ready',
            'expected_parcel_count',
        )

    def get_product_items(self, obj):
        items = parse_product_items(obj.product_links)
        result = []
        for item in items:
            price = item.get('price')
            qty = int(item.get('quantity') or 1)
            result.append({
                'url': item.get('url', ''),
                'description': item.get('description', ''),
                'price': float(price) if price is not None else None,
                'quantity': qty if qty > 0 else 1,
            })
        return result

    def get_product_links_list(self, obj):
        return [
            item.get('url', '')
            for item in parse_product_items(obj.product_links)
            if item.get('url')
        ]

    def get_payment_completed(self, obj):
        return obj.payments.filter(status='completed').exists()


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
        extra_kwargs = {
            'status': {'required': False},
            'total_amount': {'required': False},
        }

    def create(self, validated_data):
        links = validated_data.pop('product_links', None)
        items = normalize_incoming_links(links)
        validated_data['product_links'] = dump_product_items(items)
        validated_data['quantity'] = total_items_quantity(items)
        validated_data['total_amount'] = 0
        validated_data['withdrawal_fee'] = 0
        validated_data['quote_ready'] = False
        if 'status' not in validated_data:
            validated_data['status'] = 'pending'
        return super().create(validated_data)


class OrderQuoteSerializer(serializers.Serializer):
    """Admin : lignes du devis + frais de retrait → total recalculé."""
    product_items = serializers.ListField(
        child=serializers.DictField(),
        allow_empty=False,
    )
    withdrawal_fee = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    expected_parcel_count = serializers.IntegerField(min_value=1, max_value=100)
    status = serializers.ChoiceField(
        choices=['pending', 'processing', 'shipped', 'delivered', 'cancelled'],
        required=False,
    )

    def validate_product_items(self, value):
        cleaned = []
        for entry in value:
            url = str(entry.get('url') or '').strip()
            description = str(entry.get('description') or '').strip()
            if not url and not description:
                raise serializers.ValidationError(
                    "Chaque ligne doit avoir un lien ou une description."
                )
            price = entry.get('price')
            if price is None or price == '':
                raise serializers.ValidationError(
                    f"Indiquez un prix pour la ligne : {description or url}"
                )
            try:
                from decimal import Decimal
                price_dec = Decimal(str(price))
            except Exception as exc:
                raise serializers.ValidationError(f"Prix invalide pour {url}") from exc
            if price_dec < 0:
                raise serializers.ValidationError(f"Prix négatif interdit pour {url}")
            try:
                qty = int(entry.get('quantity', 1))
            except (TypeError, ValueError):
                qty = 1
            if qty < 1:
                qty = 1
            cleaned.append({
                'url': url,
                'description': description,
                'price': price_dec,
                'quantity': qty,
            })
        return cleaned

    def validate(self, attrs):
        total = compute_quote_total(
            attrs.get('product_items', []),
            attrs.get('withdrawal_fee', 0),
        )
        if total <= 0:
            raise serializers.ValidationError(
                "Le montant total du devis doit être supérieur à zéro."
            )
        if self.instance is not None:
            if self.instance.payments.filter(status='completed').exists():
                raise serializers.ValidationError(
                    "Ce devis ne peut plus être modifié après confirmation du paiement."
                )
            if self.instance.parcels.filter(order_sequence__isnull=False).exists():
                raise serializers.ValidationError(
                    "Les colis ont déjà été générés pour cette commande."
                )
        return attrs

    def update(self, instance, validated_data):
        items = validated_data['product_items']
        fee = validated_data['withdrawal_fee']
        instance.expected_parcel_count = validated_data['expected_parcel_count']
        instance.product_links = dump_product_items(items)
        instance.withdrawal_fee = fee
        instance.total_amount = compute_quote_total(items, fee)
        instance.quantity = total_items_quantity(items)
        instance.quote_ready = True
        if 'status' in validated_data:
            instance.status = validated_data['status']
        instance.save()
        return instance


from django.utils.translation import gettext as _

class ConsolidationSerializer(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(source='request_date', read_only=True)
    group_name = serializers.SerializerMethodField()
    user = UserSerializer(read_only=True)
    parcels = serializers.SerializerMethodField()

    class Meta:
        model = Consolidation
        fields = ('id', 'group_name', 'user', 'parcels', 'request_date', 'created_at', 'status', 'admin_note')
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
    admin_note = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Consolidation
        fields = ('status', 'parcel_id', 'decision', 'admin_note')

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

        if attrs.get('status') == 'completed':
            note = (attrs.get('admin_note') or '').strip()
            if not note:
                raise serializers.ValidationError(
                    {"admin_note": "Ajoutez une note descriptive pour notifier le client."}
                )

        return attrs

    def update(self, instance, validated_data):
        from django.db import transaction

        parcel_id = validated_data.pop('parcel_id', None)
        decision = validated_data.pop('decision', None)
        new_status = validated_data.get('status')
        admin_note = validated_data.get('admin_note')

        with transaction.atomic():
            if parcel_id is not None and decision is not None:
                ConsolidationParcelDecision.objects.update_or_create(
                    consolidation=instance,
                    parcel_id=parcel_id,
                    defaults={'decision': decision},
                )

            if admin_note is not None:
                instance.admin_note = admin_note.strip()

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
            elif admin_note is not None:
                instance.save(update_fields=['admin_note'])

        return instance
