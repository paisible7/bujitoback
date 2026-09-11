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
    ParcelBulkImportView,
    ParcelImagesZipImportView,
    ImportBatchListView,
    ParcelBulkStatusView,
    ShipmentBatchListCreateView,
    ShipmentBatchGenerateView,
    ShipmentBatchDetailView,
    ConsolidationBulkStatusView,
)

urlpatterns = [
    # URLs pour les commandes (maintenant directement sous /api/orders/ après inclusion)
    path('orders/', OrderListCreateView.as_view(), name='order-list-create'),
    path('orders/<int:pk>/', OrderDetailView.as_view(), name='order-detail'),

    # URL pour l'import bulk
    path('parcels/bulk/', ParcelBulkImportView.as_view(), name='parcel-bulk-import'),
    path('parcels/bulk-status/', ParcelBulkStatusView.as_view(), name='parcel-bulk-status'),
    path('parcels/import-images/', ParcelImagesZipImportView.as_view(), name='parcel-images-zip-import'),
    path('parcels/imports/', ImportBatchListView.as_view(), name='parcel-imports-list'),

    # URL pour le groupage de colis
    path('parcels/group/', ParcelGroupView.as_view(), name='parcel-group'),
    path('parcels/groups/', ConsolidationListView.as_view(), name='consolidation-list'),
    path('parcels/groups/bulk-status/', ConsolidationBulkStatusView.as_view(), name='consolidation-bulk-status'),
    path('parcels/groups/<int:pk>/', ConsolidationDetailView.as_view(), name='consolidation-detail'),

    # Lots MCO
    path('shipments/', ShipmentBatchListCreateView.as_view(), name='shipment-list-create'),
    path('shipments/generate/', ShipmentBatchGenerateView.as_view(), name='shipment-generate'),
    path('shipments/<int:pk>/', ShipmentBatchDetailView.as_view(), name='shipment-detail'),

    # URLs pour les colis (maintenant directement sous /api/parcels/ après inclusion)
    path('parcels/', ParcelListCreateView.as_view(), name='parcel-list-create'),
    path('parcels/<str:tracking_number>/', ParcelDetailView.as_view(), name='parcel-detail'),
    path('parcels/<str:tracking_number>/track/', ParcelTrackView.as_view(), name='parcel-track'),
]
