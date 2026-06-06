from django.contrib import admin
from .models import Order, Parcel

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'order_date', 'status', 'total_amount')
    list_filter = ('status', 'order_date')
    search_fields = ('user__email', 'id')
    raw_id_fields = ('user',) # Permet une recherche plus efficace pour les utilisateurs

@admin.register(Parcel)
class ParcelAdmin(admin.ModelAdmin):
    list_display = ('tracking_number', 'order', 'status', 'current_location', 'last_updated')
    list_filter = ('status', 'last_updated')
    search_fields = ('tracking_number', 'order__user__email', 'description')
    raw_id_fields = ('order',) # Permet une recherche plus efficace pour les commandes
