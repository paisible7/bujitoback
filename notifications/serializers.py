from rest_framework import serializers

from django.contrib.auth import get_user_model

from .models import Notification
from .text_sanitizer import strip_emojis
from parcels.media_urls import absolute_media_url

User = get_user_model()


class NotificationSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    def get_image(self, obj):
        return absolute_media_url(
            obj.image,
            self.context.get('request'),
            label=f'Notification #{obj.pk}',
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["title"] = strip_emojis(data.get("title"))
        data["message"] = strip_emojis(data.get("message"))
        return data

    class Meta:
        model = Notification
        fields = ['id', 'title', 'message', 'type', 'reference_id', 'image', 'is_read', 'created_at']
        read_only_fields = ['id', 'created_at', 'image']


class AdminSendNotificationSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    message = serializers.CharField()
    user_id = serializers.IntegerField(required=False)
    user_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=False,
    )
    send_to_all = serializers.BooleanField(default=False)
    type = serializers.CharField(max_length=50, default='general', required=False)
    image = serializers.ImageField(required=False, allow_null=True)

    def validate(self, attrs):
        send_to_all = attrs.get('send_to_all', False)
        user_id = attrs.get('user_id')
        user_ids = attrs.get('user_ids')

        if send_to_all and (user_id is not None or user_ids):
            raise serializers.ValidationError(
                "Choisissez des destinataires ou l'envoi à tous les clients, pas les deux."
            )

        # Normaliser en user_ids
        resolved = list(user_ids or [])
        if user_id is not None and user_id not in resolved:
            resolved.append(user_id)
        attrs['user_ids'] = resolved

        if not send_to_all and not resolved:
            raise serializers.ValidationError(
                "Indiquez user_ids (ou user_id) ou activez send_to_all."
            )
        return attrs

    def validate_user_id(self, value):
        from users.roles import CLIENT_ROLES
        if not User.objects.filter(pk=value, role__in=CLIENT_ROLES, is_active=True).exists():
            raise serializers.ValidationError("Utilisateur client introuvable.")
        return value

    def validate_user_ids(self, value):
        from users.roles import CLIENT_ROLES
        unique = list(dict.fromkeys(value))
        found = set(
            User.objects.filter(pk__in=unique, role__in=CLIENT_ROLES, is_active=True)
            .values_list('pk', flat=True)
        )
        missing = [uid for uid in unique if uid not in found]
        if missing:
            raise serializers.ValidationError(
                f"Clients introuvables ou inactifs: {missing}"
            )
        return unique
