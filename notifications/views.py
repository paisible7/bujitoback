from rest_framework import viewsets, status, decorators
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Notification, FCMDevice
from .serializers import NotificationSerializer, AdminSendNotificationSerializer
from .utils import send_fcm_notification
from django.contrib.auth import get_user_model

User = get_user_model()

class NotificationViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)

    @decorators.action(detail=False, methods=['post'], url_path='register-device')
    def register_device(self, request):
        token = request.data.get('token')
        platform = request.data.get('platform', 'android')
        if not token:
            return Response({"error": "Token missing"}, status=status.HTTP_400_BAD_REQUEST)

        FCMDevice.objects.update_or_create(
            token=token,
            defaults={
                'user': request.user,
                'platform': platform
            }
        )
        return Response({"status": "device registered"}, status=status.HTTP_200_OK)

    @decorators.action(detail=False, methods=['post'], url_path='unregister-device')
    def unregister_device(self, request):
        token = request.data.get('token')
        if token:
            FCMDevice.objects.filter(token=token, user=request.user).delete()
        return Response({"status": "device unregistered"}, status=status.HTTP_200_OK)

    @decorators.action(detail=True, methods=['post'])
    def read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.save()
        return Response({"status": "notification marked as read"})

    @decorators.action(detail=False, methods=['post'], url_path='read-all')
    def read_all(self, request):
        self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({"status": "all notifications marked as read"})

    @decorators.action(detail=False, methods=['post'], url_path='send')
    def send_notification(self, request):
        if request.user.role != 'admin':
            return Response({"detail": "Action réservée aux administrateurs."}, status=status.HTTP_403_FORBIDDEN)

        serializer = AdminSendNotificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if data.get('send_to_all'):
            recipients = User.objects.filter(role='user', is_active=True)
        else:
            recipients = User.objects.filter(pk=data['user_id'])

        sent_count = 0
        push_count = 0
        for user in recipients:
            result = send_fcm_notification(
                user,
                data['title'],
                data['message'],
                type=data.get('type', 'general'),
                data={'type': data.get('type', 'general')},
            )
            sent_count += 1
            if result.get('success'):
                push_count += 1

        return Response({
            "sent_count": sent_count,
            "push_count": push_count,
            "total_recipients": recipients.count(),
            "message": f"Notification envoyée à {sent_count} client(s).",
        }, status=status.HTTP_200_OK)
