from rest_framework import serializers
from parcels.media_urls import absolute_media_url
from .models import PaymentMethod, Payment, SavedPaymentMethod


def _payment_meta(obj):
    raw = obj.provider_raw_response
    return raw if isinstance(raw, dict) else {}


class SavedPaymentMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedPaymentMethod
        fields = ['id', 'type', 'label', 'last_four', 'phone_number', 'is_default']
        read_only_fields = ['id']


class PaymentMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentMethod
        fields = ['id', 'name', 'code', 'is_active', 'icon_url']


class PaymentSerializer(serializers.ModelSerializer):
    method = serializers.SerializerMethodField()
    redirect_url = serializers.ReadOnlyField(source='payment_url')
    user_email = serializers.SerializerMethodField()
    client_name = serializers.SerializerMethodField()
    proof_image_url = serializers.SerializerMethodField()
    is_transfer = serializers.SerializerMethodField()
    beneficiary_name = serializers.SerializerMethodField()
    beneficiary_phone = serializers.SerializerMethodField()
    note = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = [
            'id',
            'order',
            'amount',
            'currency',
            'method',
            'status',
            'created_at',
            'reference',
            'redirect_url',
            'user_email',
            'client_name',
            'proof_image_url',
            'is_transfer',
            'beneficiary_name',
            'beneficiary_phone',
            'note',
        ]
        read_only_fields = ['reference', 'status', 'created_at', 'proof_image_url']

    def get_method(self, obj):
        # Flutter expects a string value like 'orange_money', not the FK id.
        return getattr(obj.method, 'code', None) or ''

    def get_user_email(self, obj):
        return getattr(obj.user, 'email', None)

    def get_client_name(self, obj):
        name = (getattr(obj.user, 'full_name', '') or '').strip()
        return name or getattr(obj.user, 'email', '')

    def get_proof_image_url(self, obj):
        return absolute_media_url(
            obj.proof_image,
            self.context.get('request'),
            label=f'Payment #{obj.pk} proof',
        )

    def get_is_transfer(self, obj):
        meta = _payment_meta(obj)
        if meta.get('type') == 'money_transfer':
            return True
        ref = (obj.reference or '')
        return obj.order_id is None and ref.startswith('TRF')

    def get_beneficiary_name(self, obj):
        return (_payment_meta(obj).get('beneficiary_name') or '').strip() or None

    def get_beneficiary_phone(self, obj):
        return (_payment_meta(obj).get('beneficiary_phone') or '').strip() or None

    def get_note(self, obj):
        return (_payment_meta(obj).get('note') or '').strip() or None
