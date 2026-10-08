from rest_framework import serializers

from core.serializers import PublicUUIDSerializerMixin
from .models import Expense


class ExpenseSerializer(PublicUUIDSerializerMixin, serializers.ModelSerializer):
    client_name = serializers.CharField(
        source='client.full_name',
        read_only=True,
        allow_null=True,
    )
    client_email = serializers.EmailField(
        source='client.email',
        read_only=True,
        allow_null=True,
    )
    recorded_by = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Expense
        fields = (
            'id', 'name', 'category', 'description', 'amount', 'currency',
            'expense_date', 'client', 'client_name', 'client_email',
            'recorded_by', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'recorded_by', 'created_at', 'updated_at')

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError('Le montant doit être supérieur à zéro.')
        return value

    def validate_currency(self, value):
        return (value or 'USD').strip().upper()

    def create(self, validated_data):
        request = self.context.get('request')
        if request is not None:
            validated_data['recorded_by'] = request.user
        return super().create(validated_data)