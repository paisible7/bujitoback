from rest_framework import serializers

from django.contrib.auth import get_user_model

from .models import Notification
from .text_sanitizer import strip_emojis

User = get_user_model()


class NotificationSerializer(serializers.ModelSerializer):
    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["title"] = strip_emojis(data.get("title"))
        data["message"] = strip_emojis(data.get("message"))
        return data

    class Meta:
        model = Notification
        fields = ['id', 'title', 'message', 'type', 'reference_id', 'is_read', 'created_at']
        read_only_fields = ['id', 'created_at']


class AdminSendNotificationSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    message = serializers.CharField()
    user_id = serializers.IntegerField(required=False)
    send_to_all = serializers.BooleanField(default=False)
    type = serializers.CharField(max_length=50, default='general', required=False)

    def validate(self, attrs):
        send_to_all = attrs.get('send_to_all', False)
        user_id = attrs.get('user_id')
        if send_to_all and user_id is not None:
            raise serializers.ValidationError(
                "Choisissez un destinataire ou l'envoi à tous les clients, pas les deux."
            )
        if not send_to_all and user_id is None:
            raise serializers.ValidationError(
                "Indiquez user_id ou activez send_to_all."
            )
        return attrs

    def validate_user_id(self, value):
        if not User.objects.filter(pk=value, role='user').exists():
            raise serializers.ValidationError("Utilisateur client introuvable.")
        return value
