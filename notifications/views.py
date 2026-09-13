from rest_framework import viewsets, status, decorators
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Notification, FCMDevice
from .serializers import NotificationSerializer, AdminSendNotificationSerializer
from .utils import send_fcm_notification
from django.contrib.auth import get_user_model

User = get_user_model()


def _as_plain_dict(data):
    """Normalise QueryDict / multipart en dict Python simple."""
    if data is None:
        return {}
    if hasattr(data, 'lists'):
        out = {}
        for key, values in data.lists():
            if not values:
                continue
            out[key] = values[0] if len(values) == 1 else list(values)
        return out
    if hasattr(data, 'copy'):
        try:
            return dict(data.copy())
        except Exception:
            pass
    return dict(data) if not isinstance(data, dict) else dict(data)


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
        from users.roles import CLIENT_ROLES, is_app_admin

        if not is_app_admin(request.user):
            return Response(
                {"detail": "Action réservée aux administrateurs."},
                status=status.HTTP_403_FORBIDDEN,
            )

        payload = _as_plain_dict(request.data)

        # Multipart: send_to_all arrive souvent en string "true"/"false"
        if 'send_to_all' in payload:
            val = payload.get('send_to_all')
            if isinstance(val, str):
                payload['send_to_all'] = val.lower() in ('1', 'true', 'yes', 'on')

        # Multipart: user_ids peut arriver en JSON string
        if 'user_ids' in payload:
            import json
            raw_ids = payload.get('user_ids')
            if isinstance(raw_ids, str):
                try:
                    payload['user_ids'] = json.loads(raw_ids)
                except json.JSONDecodeError:
                    payload['user_ids'] = [
                        int(x.strip()) for x in raw_ids.split(',') if x.strip().isdigit()
                    ]

        # Image : lire une seule fois depuis FILES (évite double-read vide)
        image_bytes = None
        image_name = None
        image_file = request.FILES.get('image')
        if image_file is not None:
            try:
                if hasattr(image_file, 'seek'):
                    image_file.seek(0)
                image_bytes = image_file.read()
                image_name = getattr(image_file, 'name', 'annonce.jpg') or 'annonce.jpg'
            except Exception:
                image_bytes = None
                image_name = None
            # Ne pas revalider le fichier déjà consommé via ImageField
            payload.pop('image', None)

        serializer = AdminSendNotificationSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if data.get('send_to_all'):
            recipients = list(
                User.objects.filter(role__in=CLIENT_ROLES, is_active=True)
            )
        else:
            recipients = list(
                User.objects.filter(pk__in=data.get('user_ids') or [], is_active=True)
            )

        if not recipients:
            return Response(
                {
                    "sent_count": 0,
                    "push_count": 0,
                    "failed": [],
                    "total_recipients": 0,
                    "message": "Aucun destinataire trouvé.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        sent_count = 0
        push_count = 0
        failed = []
        for user in recipients:
            try:
                result = send_fcm_notification(
                    user,
                    data['title'],
                    data['message'],
                    type=data.get('type', 'general'),
                    data={'type': data.get('type', 'general')},
                    image_bytes=image_bytes if image_bytes else None,
                    image_name=image_name,
                    request=request,
                    translate=False,
                )
                sent_count += 1
                if result.get('success'):
                    push_count += 1
                else:
                    failed.append(user.pk)
            except Exception:
                failed.append(user.pk)

        return Response({
            "sent_count": sent_count,
            "push_count": push_count,
            "failed": failed,
            "total_recipients": len(recipients),
            "message": f"Notification envoyée à {sent_count} client(s).",
        }, status=status.HTTP_200_OK)
