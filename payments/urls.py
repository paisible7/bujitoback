from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PaymentViewSet, SavedPaymentMethodViewSet

router = DefaultRouter()
router.register(r'methods', SavedPaymentMethodViewSet, basename='payment-methods')
router.register(r'', PaymentViewSet, basename='payment')

urlpatterns = [
    path('', include(router.urls)),
]
