from django.urls import path
from .views import (
    OrderListCreateView,
    OrderDetailView,
    ParcelListCreateView,
    ParcelDetailView,
    ParcelTrackView,
    ParcelGroupView,
    ConsolidationListView,
    ConsolidationDetailView,
    # ConsolidationListCreateView, # Commenté car la vue n'existe pas encore
    # ConsolidationDetailView,     # Commenté car la vue n'existe pas encore
)

urlpatterns = [
    # URLs pour les commandes (maintenant directement sous /api/orders/ après inclusion)
    path('orders/', OrderListCreateView.as_view(), name='order-list-create'),
    path('orders/<int:pk>/', OrderDetailView.as_view(), name='order-detail'),

    # URL pour le groupage de colis
    path('parcels/group/', ParcelGroupView.as_view(), name='parcel-group'),
    path('parcels/groups/', ConsolidationListView.as_view(), name='consolidation-list'),
    path('parcels/groups/<int:pk>/', ConsolidationDetailView.as_view(), name='consolidation-detail'),

    # URLs pour les colis (maintenant directement sous /api/parcels/ après inclusion)
    path('parcels/', ParcelListCreateView.as_view(), name='parcel-list-create'),
    path('parcels/<str:tracking_number>/', ParcelDetailView.as_view(), name='parcel-detail'),
    path('parcels/<str:tracking_number>/track/', ParcelTrackView.as_view(), name='parcel-track'),

    # URLs pour les groupages (Consolidation) - Commentées car les vues n'existent pas encore
    # path('groups/', ConsolidationListCreateView.as_view(), name='consolidation-list-create'),
    # path('groups/<int:pk>/', ConsolidationDetailView.as_view(), name='consolidation-detail'),
]
