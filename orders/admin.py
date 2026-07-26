from django.contrib import admin
from parcels.models import Order, Parcel

class ParcelInline(admin.TabularInline):
    model = Parcel
    extra = 0
    fields = ('tracking_number', 'status', 'current_location')

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'status', 'total_amount', 'order_date')
    list_filter = ('status', 'order_date')
    search_fields = ('user__email', 'id')
    inlines = [ParcelInline]
    readonly_fields = ('order_date',)
