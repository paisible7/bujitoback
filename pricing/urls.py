from django.urls import path

from .views import BusinessSettingsView, PricingEstimateView

urlpatterns = [
    path("settings/", BusinessSettingsView.as_view(), name="pricing-settings"),
    path("estimate/", PricingEstimateView.as_view(), name="pricing-estimate"),
]
