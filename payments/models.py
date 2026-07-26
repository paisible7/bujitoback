from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

class SavedPaymentMethod(models.Model):
    """
    User-saved payment method metadata.
    Never store card PAN/CVV here. For cards, store only provider token/last4.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='saved_payment_methods',
        verbose_name=_("Utilisateur"),
    )
    type = models.CharField(max_length=50, verbose_name=_("Type"))  # e.g. 'orange_money', 'wave', 'card'
    label = models.CharField(max_length=100, verbose_name=_("LibellÃ©"))
    last_four = models.CharField(max_length=4, blank=True, null=True, verbose_name=_("4 derniers chiffres"))
    phone_number = models.CharField(max_length=50, blank=True, null=True, verbose_name=_("TÃ©lÃ©phone"))
    is_default = models.BooleanField(default=False, verbose_name=_("Par dÃ©faut"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Date de crÃ©ation"))

    class Meta:
        ordering = ['-created_at']
        verbose_name = _("Moyen de paiement enregistrÃ©")
        verbose_name_plural = _("Moyens de paiement enregistrÃ©s")

    def __str__(self):
        return f"{self.user} - {self.type} - {self.label}"

class PaymentMethod(models.Model):
    name = models.CharField(max_length=100, verbose_name=_("Nom"))
    code = models.CharField(max_length=50, unique=True, verbose_name=_("Code")) # e.g., 'orange_money', 'wave', 'card'
    is_active = models.BooleanField(default=True, verbose_name=_("Actif"))
    icon_url = models.URLField(blank=True, null=True, verbose_name=_("URL de l'icÃ´ne"))

    class Meta:
        verbose_name = _("MÃ©thode de paiement")
        verbose_name_plural = _("MÃ©thodes de paiement")

    def __str__(self):
        return self.name

class Payment(models.Model):
    STATUS_CHOICES = (
        ('pending', _('En attente')),
        ('completed', _('TerminÃ©')),
        ('failed', _('Ã‰chouÃ©')),
        ('cancelled', _('AnnulÃ©')),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name=_("Utilisateur"))
    order = models.ForeignKey('parcels.Order', on_delete=models.SET_NULL, null=True, blank=True, related_name='payments', verbose_name=_("Commande"))
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_("Montant"))
    currency = models.CharField(max_length=10, default='XOF', verbose_name=_("Devise"))
    reference = models.CharField(max_length=100, unique=True, verbose_name=_("RÃ©fÃ©rence"))
    external_id = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("ID externe"))
    method = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT, verbose_name=_("MÃ©thode"))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name=_("Statut"))
    payment_url = models.URLField(max_length=500, blank=True, null=True, verbose_name=_("URL de paiement"))
    phone_number = models.CharField(max_length=50, blank=True, null=True, verbose_name=_("TÃ©lÃ©phone"))
    provider_raw_response = models.JSONField(blank=True, null=True, verbose_name=_("RÃ©ponse brute du fournisseur"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Date de crÃ©ation"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("DerniÃ¨re mise Ã  jour"))

    class Meta:
        verbose_name = _("Paiement")
        verbose_name_plural = _("Paiements")

    def __str__(self):
        return f"{self.reference} - {self.amount} ({self.status})"
