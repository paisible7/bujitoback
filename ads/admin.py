from django.contrib import admin

from .models import Advertisement


@admin.register(Advertisement)
class AdvertisementAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'sort_order', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('title',)
    ordering = ('sort_order', '-created_at')
