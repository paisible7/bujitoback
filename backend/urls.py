from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenRefreshView,
)
from users.views import CustomTokenObtainPairView
from notifications.views import NotificationViewSet

router = DefaultRouter()
router.register(r'notifications', NotificationViewSet, basename='notification')

urlpatterns = [
    path('admin/', admin.site.urls),

    # Authentification JWT
    path('api/auth/login/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Utilisateurs
    path('api/auth/', include('users.urls')),

    # Notifications, Commandes et Colis (inclus sous /api/)
    path('api/', include(router.urls)),
    path('api/', include('parcels.urls')),
    path('api/payments/', include('payments.urls')),
    path('api/orders/', include('orders.urls')),
]

# Media : django.conf.urls.static.static() ne fait RIEN si DEBUG=False.
# En prod les images 404 si Nginx ne sert pas /media/. On ajoute un fallback
# Django contrôlé par SERVE_MEDIA (défaut True).
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
elif getattr(settings, 'SERVE_MEDIA', True):
    urlpatterns += [
        re_path(
            r'^media/(?P<path>.*)$',
            serve,
            {'document_root': settings.MEDIA_ROOT},
        ),
    ]
