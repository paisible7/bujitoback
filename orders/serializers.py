from rest_framework import serializers
from parcels.models import Order, Parcel

class OrderParcelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Parcel
        fields = ['id', 'tracking_number', 'status', 'current_location', 'description']

class OrderSerializer(serializers.ModelSerializer):
    parcels = OrderParcelSerializer(many=True, read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = Order
        fields = ['id', 'user', 'user_email', 'order_date', 'status', 'total_amount', 'parcels']
        read_only_fields = ['order_date']
