from django.urls import path

from .views import (
    AdvertisementListView,
    AdvertisementCreateView,
    AdvertisementDetailView,
)

urlpatterns = [
    path('', AdvertisementListView.as_view(), name='ads-list'),
    path('create/', AdvertisementCreateView.as_view(), name='ads-create'),
    path('<int:pk>/', AdvertisementDetailView.as_view(), name='ads-detail'),
]
