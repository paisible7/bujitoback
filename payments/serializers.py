from rest_framework import serializers
from parcels.media_urls import absolute_media_url
from .models import PaymentMethod, Payment, SavedPaymentMethod

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
