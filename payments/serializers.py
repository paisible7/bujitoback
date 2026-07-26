from rest_framework import serializers
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
        ]
        read_only_fields = ['reference', 'status', 'created_at']

    def get_method(self, obj):
        # Flutter expects a string value like 'orange_money', not the FK id.
        return getattr(obj.method, 'code', None) or ''
