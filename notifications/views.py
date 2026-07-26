from rest_framework import viewsets, status, decorators
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Notification, FCMDevice
from .serializers import NotificationSerializer

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
