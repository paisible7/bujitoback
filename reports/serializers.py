from django.contrib.auth import get_user_model
from rest_framework import serializers

from core.serializers import PublicUUIDSerializerMixin
from parcels.media_urls import absolute_media_url
from users.roles import CLIENT_ROLES
from .models import Expense

User = get_user_model()


def _parse_client_ids(raw):
    """Accepte liste JSON, liste multipart, ou '1,2,3'."""
    if raw is None or raw == '':
        return []
    if isinstance(raw, list):
        values = raw
    else:
        text = str(raw).strip()
        if not text:
            return []
        if text.startswith('['):
            import json
            try:
                decoded = json.loads(text)
                values = decoded if isinstance(decoded, list) else [decoded]
            except (TypeError, ValueError):
                values = [p.strip() for p in text.split(',') if p.strip()]
        else:
            values = [p.strip() for p in text.split(',') if p.strip()]
    ids = []
    for item in values:
        try:
            ids.append(int(item))
        except (TypeError, ValueError):
            continue
    return list(dict.fromkeys(ids))


class ExpenseSerializer(PublicUUIDSerializerMixin, serializers.ModelSerializer):
    clients = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=User.objects.filter(role__in=CLIENT_ROLES, is_active=True),
        required=False,
    )
    client_ids = serializers.SerializerMethodField()
    client_names = serializers.SerializerMethodField()
    client_name = serializers.SerializerMethodField()
    client_email = serializers.SerializerMethodField()
    recorded_by = serializers.PrimaryKeyRelatedField(read_only=True)
    proof_image = serializers.ImageField(required=False, allow_null=True, write_only=True)
    proof_image_url = serializers.SerializerMethodField()

    class Meta:
        model = Expense
        fields = (
            'id', 'name', 'category', 'description', 'amount', 'currency',
            'expense_date', 'clients', 'client_ids', 'client_names',
            'client_name', 'client_email',
            'recorded_by', 'proof_image', 'proof_image_url',
            'created_at', 'updated_at',
        )
        read_only_fields = (
            'id', 'client_ids', 'client_names', 'client_name', 'client_email',
            'recorded_by', 'proof_image_url', 'created_at', 'updated_at',
        )

    def get_proof_image_url(self, obj):
        return absolute_media_url(
            obj.proof_image,
            self.context.get('request'),
            label=f'Expense #{obj.pk} proof',
        )

    def get_client_ids(self, obj):
        return list(obj.clients.values_list('pk', flat=True))

    def get_client_names(self, obj):
        names = []
        for user in obj.clients.all():
            label = (getattr(user, 'full_name', '') or '').strip() or user.email
            if label:
                names.append(label)
        return names

    def get_client_name(self, obj):
        names = self.get_client_names(obj)
        return ', '.join(names) if names else None

    def get_client_email(self, obj):
        emails = [u.email for u in obj.clients.all() if u.email]
        return ', '.join(emails) if emails else None

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError('Le montant doit être supérieur à zéro.')
        return value

    def validate_currency(self, value):
        return (value or 'USD').strip().upper()

    def to_internal_value(self, data):
        raw_clients = None
        raw_legacy = None
        if hasattr(data, 'get'):
            raw_clients = data.get('clients')
            raw_legacy = data.get('client')
        if (raw_clients is None or raw_clients == '') and raw_legacy not in (None, ''):
            raw_clients = raw_legacy
        ids = _parse_client_ids(raw_clients)

        if hasattr(data, 'copy'):
            try:
                mutable = data.copy()
                mutable.setlist('clients', [str(i) for i in ids])
                data = mutable
            except Exception:
                pass
        elif isinstance(data, dict):
            data = dict(data)
            data['clients'] = ids

        return super().to_internal_value(data)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance is None and not attrs.get('proof_image'):
            raise serializers.ValidationError({
                'proof_image': (
                    'Ajoutez une preuve : photo du reçu ou capture '
                    'de la transaction.'
                ),
            })
        return attrs

    def create(self, validated_data):
        clients = validated_data.pop('clients', [])
        request = self.context.get('request')
        if request is not None:
            validated_data['recorded_by'] = request.user
        expense = super().create(validated_data)
        if clients:
            expense.clients.set(clients)
        return expense

    def update(self, instance, validated_data):
        clients = validated_data.pop('clients', None)
        expense = super().update(instance, validated_data)
        if clients is not None:
            expense.clients.set(clients)
        return expense
