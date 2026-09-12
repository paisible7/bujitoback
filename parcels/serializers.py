from rest_framework import serializers
from .models import Order, Parcel, Consolidation, ConsolidationParcelDecision, OrderImage, ConsolidationNoteImage, ShipmentBatch
from users.serializers import UserSerializer # Pour inclure les détails de l'utilisateur si nécessaire
from .media_urls import absolute_media_url
from .quote_utils import (
    parse_product_items,
    dump_product_items,
    normalize_incoming_links,
    compute_quote_total,
    total_items_quantity,
    flatten_packages,
)

class ParcelSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()
    package_photo = serializers.SerializerMethodField()
    package_photos = serializers.SerializerMethodField()
    user_email = serializers.SerializerMethodField()
    was_grouped = serializers.SerializerMethodField()
    group_id = serializers.SerializerMethodField()
    mco_code = serializers.SerializerMethodField()

    class Meta:
        model = Parcel
        fields = [
            'id', 'tracking_number', 'supplier_tracking_number',
            'order_sequence', 'status', 'current_location',
            'client_name', 'client_phone', 'weight_volume', 'weight_kg',
            'warehouse_number', 'china_arrival_date', 'description',
            'image', 'package_photo', 'package_photos', 'last_updated', 'order',
            'user_email', 'was_grouped', 'group_id', 'mco_code',
        ]
        read_only_fields = ('last_updated', 'mco_code')

    def get_was_grouped(self, obj):
        return obj.consolidations.filter(status='completed').exists()

    def get_group_id(self, obj):
        group = obj.consolidations.filter(status='completed').order_by('-request_date').first()
        return group.pk if group else None

    def get_mco_code(self, obj):
        batches = list(obj.shipment_batches.all())
        if not batches:
            return None
        batches.sort(key=lambda b: b.created_at or b.pk, reverse=True)
        return batches[0].code

    def get_image(self, obj):
        urls = self._all_image_urls(obj)
        return urls[0] if urls else None

    def get_package_photo(self, obj):
        urls = self._all_image_urls(obj)
        return urls[0] if urls else None

    def get_package_photos(self, obj):
        return self._all_image_urls(obj)

    def get_user_email(self, obj):
        if obj.order_id and obj.order:
            return obj.order.user.email
        return None

    def _all_image_urls(self, obj):
        request = self.context.get('request')
        urls = []
        main = absolute_media_url(
            obj.image,
            request,
            label=f'Parcel #{obj.pk} ({obj.tracking_number})',
        )
        if main:
            urls.append(main)
        extras = getattr(obj, '_prefetched_objects_cache', {}).get('extra_images')
        extra_qs = extras if extras is not None else obj.extra_images.all()
        for extra in extra_qs:
            url = absolute_media_url(
                extra.image,
                request,
                label=f'ParcelImage #{extra.pk}',
            )
            if url and url not in urls:
                urls.append(url)
        return urls

    def _absolute_image_url(self, obj):
        urls = self._all_image_urls(obj)
        return urls[0] if urls else None


class ShipmentBatchSerializer(serializers.ModelSerializer):
    parcel_count = serializers.SerializerMethodField()
    tracking_numbers = serializers.SerializerMethodField()

    class Meta:
        model = ShipmentBatch
        fields = [
            'id', 'code', 'status', 'total_weight_kg', 'parcel_count',
            'tracking_numbers', 'created_at', 'shipped_at', 'notes',
        ]
        read_only_fields = ('code', 'total_weight_kg', 'created_at', 'shipped_at')

    def get_parcel_count(self, obj):
        return obj.parcels.count()

    def get_tracking_numbers(self, obj):
        return list(obj.parcels.values_list('tracking_number', flat=True))

class OrderImageSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = OrderImage
        fields = ('id', 'image', 'package_index', 'uploaded_at')

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
            'total_amount', 'withdrawal_fee', 'commission_fee', 'quote_ready',
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
            entry = {
                'url': item.get('url', ''),
                'description': item.get('description', ''),
                'price': float(price) if price is not None else None,
                'quantity': qty if qty > 0 else 1,
            }
            if 'package_index' in item:
                entry['package_index'] = item['package_index']
            result.append(entry)
        return result

    def get_product_links_list(self, obj):
        return [
            item.get('url', '')
            for item in parse_product_items(obj.product_links)
            if item.get('url')
        ]

    def get_payment_completed(self, obj):
        cache = getattr(obj, "_prefetched_objects_cache", None)
        if cache is not None and "payments" in cache:
            return any(payment.status == "completed" for payment in obj.payments.all())
        return obj.payments.filter(status="completed").exists()


class OrderCreateSerializer(serializers.ModelSerializer):
    product_links = serializers.JSONField(required=False, allow_null=True)
    packages = serializers.JSONField(required=False, allow_null=True)
    client_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    client_phone = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    country = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    city = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    quantity = serializers.IntegerField(required=False, min_value=1)
    comment = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    expected_parcel_count = serializers.IntegerField(
        required=False, min_value=1, max_value=100
    )

    class Meta:
        model = Order
        fields = [
            'total_amount', 'status', 'client_name', 'client_phone',
            'country', 'city', 'product_links', 'packages', 'quantity',
            'comment', 'expected_parcel_count',
        ]
        extra_kwargs = {
            'status': {'required': False},
            'total_amount': {'required': False},
        }

    def create(self, validated_data):
        packages = validated_data.pop('packages', None)
        if isinstance(packages, str):
            import json
            try:
                packages = json.loads(packages)
            except Exception:
                packages = None
        links = validated_data.pop('product_links', None)
        expected = validated_data.pop('expected_parcel_count', None)

        items = []
        aggregated_comment = None
        package_count = 0
        if packages:
            items, package_count, aggregated_comment = flatten_packages(packages)
        if not items:
            items = normalize_incoming_links(links)

        validated_data['product_links'] = dump_product_items(items)
        validated_data['quantity'] = total_items_quantity(items)
        validated_data['total_amount'] = 0
        validated_data['withdrawal_fee'] = 0
        validated_data['commission_fee'] = 0
        validated_data['quote_ready'] = False

        if expected is not None:
            validated_data['expected_parcel_count'] = expected
        elif package_count > 0:
            validated_data['expected_parcel_count'] = package_count
        else:
            # Une commande = au moins 1 colis prévu
            validated_data['expected_parcel_count'] = 1

        if aggregated_comment and not validated_data.get('comment'):
            validated_data['comment'] = aggregated_comment

        if 'status' not in validated_data:
            validated_data['status'] = 'pending'
        return super().create(validated_data)


class OrderClientUpdateSerializer(serializers.ModelSerializer):
    """Client : modifier le contenu avant paiement → invalide le devis."""

    product_links = serializers.JSONField(required=False, allow_null=True)
    packages = serializers.JSONField(required=False, allow_null=True)
    client_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    client_phone = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    country = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    city = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    quantity = serializers.IntegerField(required=False, min_value=1)
    comment = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    expected_parcel_count = serializers.IntegerField(
        required=False, min_value=1, max_value=100
    )

    class Meta:
        model = Order
        fields = [
            'client_name', 'client_phone', 'country', 'city',
            'product_links', 'packages', 'quantity', 'comment',
            'expected_parcel_count',
        ]

    def validate(self, attrs):
        instance = self.instance
        if instance is None:
            return attrs
        if instance.payments.filter(status='completed').exists():
            raise serializers.ValidationError(
                "Cette commande ne peut plus être modifiée après confirmation du paiement."
            )
        if instance.parcels.exists():
            raise serializers.ValidationError(
                "Cette commande ne peut plus être modifiée : des colis existent déjà."
            )
        if instance.status == 'cancelled':
            raise serializers.ValidationError(
                "Une commande annulée ne peut pas être modifiée."
            )
        return attrs

    def update(self, instance, validated_data):
        import json

        packages = validated_data.pop('packages', None)
        if isinstance(packages, str):
            try:
                packages = json.loads(packages)
            except Exception:
                packages = None
        links = validated_data.pop('product_links', serializers.empty)
        expected = validated_data.pop('expected_parcel_count', None)

        items = []
        aggregated_comment = None
        package_count = 0
        if packages:
            items, package_count, aggregated_comment = flatten_packages(packages)
        elif links is not serializers.empty:
            items = normalize_incoming_links(links)
        else:
            items = parse_product_items(instance.product_links)

        # Pas de prix côté client — le devis admin les recalculera.
        cleaned_items = []
        for entry in items:
            cleaned = {
                'url': str(entry.get('url') or '').strip(),
                'description': str(entry.get('description') or '').strip(),
                'quantity': max(1, int(entry.get('quantity') or 1)),
            }
            pkg = entry.get('package_index')
            if pkg is not None and pkg != '':
                try:
                    cleaned['package_index'] = max(0, int(pkg))
                except (TypeError, ValueError):
                    pass
            if cleaned['url'] or cleaned['description']:
                cleaned_items.append(cleaned)

        if not cleaned_items and not packages:
            raise serializers.ValidationError(
                "Ajoutez au moins un lien produit ou une description."
            )

        for field, value in validated_data.items():
            setattr(instance, field, value)

        instance.product_links = dump_product_items(cleaned_items)
        instance.quantity = total_items_quantity(cleaned_items) or 1
        instance.total_amount = 0
        instance.withdrawal_fee = 0
        instance.commission_fee = 0
        instance.quote_ready = False
        if expected is not None:
            instance.expected_parcel_count = expected
        elif package_count > 0:
            instance.expected_parcel_count = package_count

        if aggregated_comment and not (instance.comment or '').strip():
            instance.comment = aggregated_comment

        # Annuler les paiements encore en attente (devis invalidé).
        instance.payments.filter(status='pending').update(status='cancelled')

        instance._client_edited = True
        instance.save()
        return instance


class OrderQuoteSerializer(serializers.Serializer):
    """Admin : lignes du devis + frais (retrait, commission) → total recalculé."""
    product_items = serializers.ListField(
        child=serializers.DictField(),
        allow_empty=False,
    )
    withdrawal_fee = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    commission_fee = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=0,
        required=False,
        default=0,
    )
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
            pkg = entry.get('package_index')
            if pkg is not None and pkg != '':
                try:
                    cleaned[-1]['package_index'] = max(0, int(pkg))
                except (TypeError, ValueError):
                    pass
        return cleaned

    def validate(self, attrs):
        total = compute_quote_total(
            attrs.get('product_items', []),
            attrs.get('withdrawal_fee', 0),
            attrs.get('commission_fee', 0),
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
        withdrawal_fee = validated_data['withdrawal_fee']
        commission_fee = validated_data.get('commission_fee', 0)
        instance.expected_parcel_count = validated_data['expected_parcel_count']
        instance.product_links = dump_product_items(items)
        instance.withdrawal_fee = withdrawal_fee
        instance.commission_fee = commission_fee
        instance.total_amount = compute_quote_total(
            items,
            withdrawal_fee,
            commission_fee,
        )
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
    admin_note_image = serializers.SerializerMethodField()
    admin_note_images = serializers.SerializerMethodField()

    class Meta:
        model = Consolidation
        fields = (
            'id',
            'group_name',
            'user',
            'parcels',
            'request_date',
            'created_at',
            'status',
            'admin_note',
            'client_note',
            'weight_kg',
            'billable_weight_kg',
            'grouping_fee',
            'admin_note_image',
            'admin_note_images',
        )
        read_only_fields = (
            'user',
            'request_date',
            'status',
            'client_note',
            'billable_weight_kg',
        )

    def get_group_name(self, obj):
        return f"{_('Groupage')} #{obj.id}"

    def _note_image_urls(self, obj):
        request = self.context.get('request')
        urls = []
        for note_img in obj.note_images.all():
            url = absolute_media_url(
                note_img.image,
                request,
                label='consolidation.note_image',
            )
            if url:
                urls.append(url)
        if not urls and obj.admin_note_image:
            url = absolute_media_url(
                obj.admin_note_image,
                request,
                label='consolidation.admin_note_image',
            )
            if url:
                urls.append(url)
        return urls

    def get_admin_note_images(self, obj):
        return self._note_image_urls(obj)

    def get_admin_note_image(self, obj):
        urls = self._note_image_urls(obj)
        return urls[0] if urls else None

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
    client_note = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=2000,
        help_text="Description / instructions du client pour la demande.",
    )

    def validate_tracking_numbers(self, value):
        if len(value) > 500: # Limite de 500 colis comme spécifié
            raise serializers.ValidationError("Vous ne pouvez pas grouper plus de 500 colis à la fois.")
        return value

    def validate_client_note(self, value):
        return (value or '').strip()


class ConsolidationClientUpdateSerializer(serializers.Serializer):
    """Client : modifier colis / note → invalide le devis (poids + frais)."""

    tracking_numbers = serializers.ListField(
        child=serializers.CharField(max_length=100),
        min_length=2,
        required=False,
    )
    client_note = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=2000,
    )

    def validate_tracking_numbers(self, value):
        if len(value) > 500:
            raise serializers.ValidationError(
                "Vous ne pouvez pas grouper plus de 500 colis à la fois."
            )
        # Dédupliquer en conservant l'ordre
        seen = set()
        cleaned = []
        for tn in value:
            key = str(tn).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            cleaned.append(key)
        if len(cleaned) < 2:
            raise serializers.ValidationError(
                "Sélectionnez au moins 2 colis pour le groupage."
            )
        return cleaned

    def validate_client_note(self, value):
        return (value or '').strip()

    def validate(self, attrs):
        instance = self.instance
        if instance is None:
            return attrs
        if instance.status == 'cancelled':
            raise serializers.ValidationError(
                "Une demande de groupage annulée ne peut pas être modifiée."
            )
        if 'tracking_numbers' not in attrs and 'client_note' not in attrs:
            raise serializers.ValidationError(
                "Indiquez les colis et/ou une description à mettre à jour."
            )
        return attrs

    def _resolve_parcels(self, tracking_numbers, user, consolidation):
        from .models import Parcel, Consolidation

        parcels = []
        current_ids = set(consolidation.parcels.values_list('id', flat=True))
        for tn in tracking_numbers:
            try:
                parcel = Parcel.objects.select_related('order').get(
                    tracking_number=tn
                )
            except Parcel.DoesNotExist:
                raise serializers.ValidationError(
                    {"tracking_numbers": f"Le colis {tn} n'existe pas."}
                )
            if not parcel.order or parcel.order.user_id != user.id:
                raise serializers.ValidationError(
                    {
                        "tracking_numbers": (
                            f"Le colis {tn} n'appartient pas à l'utilisateur."
                        )
                    }
                )
            in_this = parcel.id in current_ids
            status_ok = parcel.status == 'pending' or (
                parcel.status == 'consolidated' and in_this
            )
            if not status_ok:
                raise serializers.ValidationError(
                    {
                        "tracking_numbers": (
                            f"Le colis {tn} n'est pas éligible au groupage."
                        )
                    }
                )
            other = Consolidation.objects.filter(
                status__in=['pending', 'processing'],
                parcels=parcel,
            ).exclude(pk=consolidation.pk).exists()
            if other:
                raise serializers.ValidationError(
                    {
                        "tracking_numbers": (
                            f"Le colis {tn} fait déjà partie d'une autre "
                            "demande de groupage en cours."
                        )
                    }
                )
            parcels.append(parcel)
        return parcels

    def update(self, instance, validated_data):
        from django.db import transaction

        from .models import Consolidation, ConsolidationParcelDecision

        request = self.context.get('request')
        user = request.user if request is not None else instance.user
        tracking_numbers = validated_data.get('tracking_numbers', serializers.empty)
        has_note = 'client_note' in validated_data
        client_note = validated_data.get('client_note') if has_note else None

        with transaction.atomic():
            old_parcels = list(instance.parcels.all())
            was_completed = instance.status == 'completed'

            if tracking_numbers is not serializers.empty:
                new_parcels = self._resolve_parcels(
                    tracking_numbers, user, instance
                )
                instance.parcels.set(new_parcels)
            else:
                new_parcels = list(instance.parcels.all())

            if has_note:
                instance.client_note = client_note or ''

            # Invalider le devis poids / frais
            instance.weight_kg = None
            instance.billable_weight_kg = None
            instance.grouping_fee = None
            ConsolidationParcelDecision.objects.filter(
                consolidation=instance
            ).delete()

            # Après confirmation (ou en cours) → rouvre en attente
            if instance.status in ('completed', 'processing'):
                instance.status = 'pending'

            # Remettre les colis consolidés de ce groupage en « pending »
            affected = {p.id: p for p in old_parcels}
            for p in new_parcels:
                affected[p.id] = p
            for parcel in affected.values():
                if parcel.status != 'consolidated':
                    continue
                still_elsewhere = Consolidation.objects.filter(
                    status='completed',
                    parcels=parcel,
                ).exclude(pk=instance.pk).exists()
                if still_elsewhere:
                    continue
                parcel.status = 'pending'
                parcel.save(update_fields=['status', 'last_updated'])

            instance._client_edited = True
            instance.save()

            # Si on rouvre un groupage déjà terminé, le changement de
            # statut doit être visible même si seuls les frais changent.
            if was_completed and instance.status == 'pending':
                pass

        return instance


class ConsolidationUpdateSerializer(serializers.ModelSerializer):
    parcel_id = serializers.IntegerField(required=False)
    decision = serializers.ChoiceField(
        choices=['pending', 'accepted', 'rejected'],
        required=False,
    )
    admin_note = serializers.CharField(required=False, allow_blank=True)
    admin_note_image = serializers.ImageField(required=False, allow_null=True)
    weight_kg = serializers.DecimalField(
        max_digits=10,
        decimal_places=3,
        required=False,
        allow_null=True,
        min_value=0,
    )
    grouping_fee = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        allow_null=True,
        min_value=0,
    )

    class Meta:
        model = Consolidation
        fields = (
            'status',
            'parcel_id',
            'decision',
            'admin_note',
            'admin_note_image',
            'weight_kg',
            'grouping_fee',
        )

    def validate_status(self, value):
        allowed = {'pending', 'processing', 'completed', 'cancelled'}
        if value not in allowed:
            raise serializers.ValidationError(
                "Statut invalide. Valeurs autorisées : pending, processing, completed, cancelled."
            )
        return value

    def _uploaded_note_images(self):
        request = self.context.get('request')
        if request is None:
            return []
        files = list(request.FILES.getlist('admin_note_images'))
        if not files and request.FILES.get('admin_note_image'):
            files = [request.FILES['admin_note_image']]
        return files

    def validate(self, attrs):
        from pricing.utils import billable_weight_kg, grouping_cost

        has_status = 'status' in attrs
        has_parcel = 'parcel_id' in attrs
        has_decision = 'decision' in attrs
        has_image = 'admin_note_image' in attrs or bool(self._uploaded_note_images())
        has_weight = 'weight_kg' in attrs
        has_fee = 'grouping_fee' in attrs

        if has_parcel != has_decision:
            raise serializers.ValidationError(
                "Indiquez parcel_id et decision ensemble pour valider un colis."
            )
        if not any([has_status, has_parcel, has_image, has_weight, has_fee, 'admin_note' in attrs]):
            raise serializers.ValidationError(
                "Indiquez un status, un poids/frais, une note ou une décision de colis."
            )

        if has_parcel and self.instance is not None:
            if not self.instance.parcels.filter(pk=attrs['parcel_id']).exists():
                raise serializers.ValidationError(
                    "Ce colis ne fait pas partie de ce groupage."
                )

        target_status = attrs.get('status')
        if target_status == 'completed':
            note = (attrs.get('admin_note') or '').strip()
            if not note and self.instance is not None:
                note = (self.instance.admin_note or '').strip()
            if not note:
                raise serializers.ValidationError(
                    {"admin_note": "Ajoutez une note descriptive pour notifier le client."}
                )
            weight = attrs.get('weight_kg')
            if weight is None and self.instance is not None:
                weight = self.instance.weight_kg
            if weight is None or weight <= 0:
                raise serializers.ValidationError(
                    {"weight_kg": "Indiquez le poids du groupage (kg)."}
                )

        if has_weight and attrs.get('weight_kg') is not None:
            weight = attrs['weight_kg']
            billable = billable_weight_kg(weight)
            attrs['_billable_weight_kg'] = billable
            if not has_fee or attrs.get('grouping_fee') is None:
                from decimal import Decimal
                calc = grouping_cost(weight_kg=weight)
                attrs['grouping_fee'] = Decimal(str(calc['amount_usd']))

        return attrs

    def update(self, instance, validated_data):
        from django.db import transaction

        parcel_id = validated_data.pop('parcel_id', None)
        decision = validated_data.pop('decision', None)
        new_status = validated_data.get('status')
        admin_note = validated_data.get('admin_note')
        uploaded_images = self._uploaded_note_images()
        has_legacy_image = 'admin_note_image' in validated_data
        legacy_image = validated_data.get('admin_note_image') if has_legacy_image else None
        billable = validated_data.pop('_billable_weight_kg', None)
        has_weight = 'weight_kg' in validated_data
        has_fee = 'grouping_fee' in validated_data
        weight_kg = validated_data.get('weight_kg') if has_weight else None
        grouping_fee = validated_data.get('grouping_fee') if has_fee else None

        with transaction.atomic():
            if parcel_id is not None and decision is not None:
                ConsolidationParcelDecision.objects.update_or_create(
                    consolidation=instance,
                    parcel_id=parcel_id,
                    defaults={'decision': decision},
                )

            if admin_note is not None:
                instance.admin_note = admin_note.strip()

            if has_weight:
                instance.weight_kg = weight_kg
                if billable is not None:
                    instance.billable_weight_kg = billable
                elif weight_kg is None:
                    instance.billable_weight_kg = None
            if has_fee:
                instance.grouping_fee = grouping_fee

            if uploaded_images:
                instance.note_images.all().delete()
                for uploaded in uploaded_images:
                    ConsolidationNoteImage.objects.create(
                        consolidation=instance,
                        image=uploaded,
                    )
                instance.admin_note_image = uploaded_images[0]
            elif has_legacy_image:
                instance.admin_note_image = legacy_image
                if legacy_image is not None:
                    ConsolidationNoteImage.objects.create(
                        consolidation=instance,
                        image=legacy_image,
                    )

            update_fields = set()
            if admin_note is not None:
                update_fields.add('admin_note')
            if has_weight:
                update_fields.update({'weight_kg', 'billable_weight_kg'})
            if has_fee:
                update_fields.add('grouping_fee')
            if uploaded_images or has_legacy_image:
                update_fields.add('admin_note_image')

            if new_status is not None:
                instance.status = new_status
                update_fields.add('status')
                instance.save(update_fields=list(update_fields) or None)
                if new_status == 'completed':
                    decisions = {
                        d.parcel_id: d.decision
                        for d in instance.parcel_decisions.all()
                    }
                    for parcel in list(instance.parcels.all()):
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
            elif update_fields:
                instance.save(update_fields=list(update_fields))

        return instance
