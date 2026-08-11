from django.db import models
from django.utils.translation import gettext_lazy as _
from users.models import CustomUser

class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', _('En attente')),
        ('processing', _('En traitement')),
        ('shipped', _('Expédiée')),
        ('delivered', _('Livrée')),
        ('cancelled', _('Annulée')),
    ]

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='orders', verbose_name=_("Utilisateur"))
    order_date = models.DateTimeField(auto_now_add=True, verbose_name=_("Date de commande"))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name=_("Statut"))
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name=_("Montant total"))

    # Détails de la demande produit (côté client)
    client_name = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("Nom client"))
    client_phone = models.CharField(max_length=50, blank=True, null=True, verbose_name=_("Téléphone"))
    country = models.CharField(max_length=100, blank=True, null=True, verbose_name=_("Pays"))
    city = models.CharField(max_length=100, blank=True, null=True, verbose_name=_("Ville"))
    product_links = models.TextField(blank=True, null=True, verbose_name=_("Liens produits"))
    quantity = models.PositiveIntegerField(default=1, verbose_name=_("Quantité"))
    comment = models.TextField(blank=True, null=True, verbose_name=_("Commentaire"))

    class Meta:
        ordering = ['-order_date']
        verbose_name = _("Commande")
        verbose_name_plural = _("Commandes")

    def __str__(self):
        return f"Order {self.id} - {self.user.email}"


class OrderImage(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='images', verbose_name=_("Commande"))
    image = models.ImageField(upload_to='orders/', verbose_name=_("Image"))
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Date d'upload"))

    class Meta:
        verbose_name = _("Image de commande")
        verbose_name_plural = _("Images de commande")

    def __str__(self):
        return f"OrderImage {self.id} - Order {self.order_id}"


class Parcel(models.Model):
    PARCEL_STATUS_CHOICES = [
        ('pending', _('En attente')),
        ('in_transit', _('En transit')),
        ('out_for_delivery', _('En cours de livraison')),
        ('delivered', _('Livré')),
        ('exception', _('Exception')),
        ('consolidated', _('Consolidé')),
    ]

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='parcels', null=True, blank=True, verbose_name=_("Commande"))
    tracking_number = models.CharField(max_length=100, unique=True, null=True, blank=True, verbose_name=_("Numéro de suivi"))
    status = models.CharField(max_length=20, choices=PARCEL_STATUS_CHOICES, default='pending', verbose_name=_("Statut"))
    current_location = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("Emplacement actuel"))

    # Champs additionnels pour l'import Excel
    client_name = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("Nom du client"))
    client_phone = models.CharField(max_length=50, blank=True, null=True, verbose_name=_("Téléphone client"))
    weight_volume = models.CharField(max_length=100, blank=True, null=True, verbose_name=_("Poids/Volume"))
    warehouse_number = models.CharField(max_length=100, blank=True, null=True, verbose_name=_("N° Entrepôt"))

    description = models.TextField(blank=True, null=True, verbose_name=_("Description"))
    image = models.ImageField(upload_to='parcels/', blank=True, null=True, verbose_name=_("Image"))
    last_updated = models.DateTimeField(auto_now=True, verbose_name=_("Dernière mise à jour"))

    class Meta:
        ordering = ['-last_updated']
        verbose_name = _("Colis")
        verbose_name_plural = _("Colis")

    def __str__(self):
        return self.tracking_number

class Consolidation(models.Model):
    CONSOLIDATION_STATUS_CHOICES = [
        ('pending', _('En attente')),
        ('processing', _('En traitement')),
        ('completed', _('Terminé')),
        ('cancelled', _('Annulé')),
    ]

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='consolidations', verbose_name=_("Utilisateur"))
    parcels = models.ManyToManyField(Parcel, related_name='consolidations', verbose_name=_("Colis"))
    request_date = models.DateTimeField(auto_now_add=True, verbose_name=_("Date de demande"))
    status = models.CharField(max_length=20, choices=CONSOLIDATION_STATUS_CHOICES, default='pending', verbose_name=_("Statut"))

    class Meta:
        ordering = ['-request_date']
        verbose_name = _("Groupage")
        verbose_name_plural = _("Groupages")

    def __str__(self):
        return f"Consolidation {self.id} - {self.user.email}"


class ConsolidationParcelDecision(models.Model):
    """Décision admin par colis au sein d'une demande de groupage."""

    DECISION_CHOICES = [
        ('pending', _('En attente')),
        ('accepted', _('Validé')),
        ('rejected', _('Refusé')),
    ]

    consolidation = models.ForeignKey(
        Consolidation,
        on_delete=models.CASCADE,
        related_name='parcel_decisions',
        verbose_name=_("Groupage"),
    )
    parcel = models.ForeignKey(
        Parcel,
        on_delete=models.CASCADE,
        related_name='consolidation_decisions',
        verbose_name=_("Colis"),
    )
    decision = models.CharField(
        max_length=20,
        choices=DECISION_CHOICES,
        default='pending',
        verbose_name=_("Décision"),
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Mis à jour"))

    class Meta:
        unique_together = ('consolidation', 'parcel')
        verbose_name = _("Décision colis (groupage)")
        verbose_name_plural = _("Décisions colis (groupage)")

    def __str__(self):
        return f"Groupage #{self.consolidation_id} / colis #{self.parcel_id}: {self.decision}"


class ImportBatch(models.Model):
    """Historique d'un fichier importé (xlsx / csv / zip)."""

    user = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='import_batches',
        verbose_name=_("Importé par"),
    )
    file_name = models.CharField(max_length=255, verbose_name=_("Nom du fichier"))
    file_type = models.CharField(max_length=20, blank=True, default='', verbose_name=_("Type"))
    file = models.FileField(
        upload_to='imports/%Y/%m/%d/',
        blank=True,
        null=True,
        verbose_name=_("Fichier"),
    )
    created_count = models.PositiveIntegerField(default=0, verbose_name=_("Créés"))
    updated_count = models.PositiveIntegerField(default=0, verbose_name=_("Mis à jour"))
    failed_count = models.PositiveIntegerField(default=0, verbose_name=_("Échecs"))
    matched_count = models.PositiveIntegerField(default=0, verbose_name=_("Associés"))
    message = models.TextField(blank=True, default='', verbose_name=_("Message"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Date d'import"))

    class Meta:
        ordering = ['-created_at']
        verbose_name = _("Import")
        verbose_name_plural = _("Imports")

    def __str__(self):
        return f"{self.file_name} ({self.created_at:%Y-%m-%d %H:%M})"
