from django.contrib import admin, messages
from django.utils.html import format_html
from django.urls import path, reverse
from django.shortcuts import redirect
from django.utils.translation import gettext as _
from .models import FCMDevice, Notification
from .utils import send_fcm_notification

@admin.register(FCMDevice)
class FCMDeviceAdmin(admin.ModelAdmin):
    list_display = ('user', 'platform', 'created_at', 'actions_button')
    list_filter = ('platform',)
    search_fields = ('user__email', 'token')

    readonly_fields = ('send_test_now_button', 'created_at')
    fields = ('user', 'token', 'platform', 'send_test_now_button', 'created_at')

    def actions_button(self, obj):
        url = reverse('admin:fcmdevice-send-test', args=[obj.pk])
        return format_html(
            '<a class="button" href="{}" style="background-color: #007bff; color: white; padding: 5px 12px; border-radius: 4px; text-decoration: none; font-weight: bold;">Envoyer Test</a>',
            url
        )
    actions_button.short_description = _("Action")

    def send_test_now_button(self, obj):
        if obj.pk:
            url = reverse('admin:fcmdevice-send-test', args=[obj.pk])
            return format_html(
                '<a class="button" href="{}" style="background-color: #28a745; color: white; padding: 10px 20px; border-radius: 5px; text-decoration: none; font-weight: bold; display: inline-block;">Envoyer une notification maintenant</a>',
                url
            )
        return _("Enregistrez d'abord l'appareil")
    send_test_now_button.short_description = _("Test")

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('send-test/<int:device_id>/', self.admin_send_test, name='fcmdevice-send-test'),
        ]
        return custom_urls + urls

    def admin_send_test(self, request, device_id):
        device = self.get_object(request, device_id)

        # Utilisation de la traduction pour le message envoyé au téléphone
        title = _("Bujito Digital")
        message = _("Votre système de notification fonctionne parfaitement.")

        res = send_fcm_notification(device.user, title, message)

        if res["success"]:
            self.message_user(request, _("Succès : Notification envoyée à %(email)s") % {'email': device.user.email})
        else:
            self.message_user(request, _("Erreur lors de l'envoi"), level=messages.ERROR)

        return redirect('admin:notifications_fcmdevice_changelist')

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'type', 'is_read', 'created_at')
    list_filter = ('is_read', 'type', 'created_at')
    search_fields = ('user__email', 'title', 'message')
    readonly_fields = ('created_at',)
