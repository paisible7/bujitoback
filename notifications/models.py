from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

class FCMDevice(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='devices', verbose_name=_("Utilisateur"))
    token = models.TextField(unique=True, verbose_name=_("Token"))
    platform = models.CharField(
        max_length=20,
        choices=[('android', 'Android'), ('ios', 'iOS')],
        default='android',
        verbose_name=_("Plateforme")
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Date de création"))

    class Meta:
        verbose_name = _("Appareil FCM")
        verbose_name_plural = _("Appareils FCM")

    def __str__(self):
        return f"{self.user.email} - {self.platform}"

class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications', verbose_name=_("Utilisateur"))
    title = models.CharField(max_length=255, verbose_name=_("Titre"))
    message = models.TextField(verbose_name=_("Message"))
    type = models.CharField(max_length=50, default='general', verbose_name=_("Type"))
    reference_id = models.IntegerField(null=True, blank=True, verbose_name=_("ID de référence"))
    image = models.ImageField(
        upload_to='notifications/',
        null=True,
        blank=True,
        verbose_name=_("Image / annonce"),
    )
    is_read = models.BooleanField(default=False, verbose_name=_("Lu"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Date de création"))

    class Meta:
        ordering = ['-created_at']
        verbose_name = _("Notification")
        verbose_name_plural = _("Notifications")

    def __str__(self):
        return f"{self.user.email} - {self.title}"
