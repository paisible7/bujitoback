from rest_framework import serializers

from .models import Notification
from .text_sanitizer import strip_emojis

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
