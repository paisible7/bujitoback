from django.db import models
from users.models import CustomUser

class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'En attente'),
        ('processing', 'En traitement'),
        ('shipped', 'Expédiée'),
        ('delivered', 'Livrée'),
        ('cancelled', 'Annulée'),
    ]

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='orders')
    order_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    class Meta:
        ordering = ['-order_date']
        verbose_name = "Commande"
        verbose_name_plural = "Commandes"

    def __str__(self):
        return f"Commande {self.id} par {self.user.email}"

class Parcel(models.Model):
    PARCEL_STATUS_CHOICES = [
        ('pending', 'En attente'),
        ('in_transit', 'En transit'),
        ('out_for_delivery', 'En cours de livraison'),
        ('delivered', 'Livré'),
        ('exception', 'Exception'),
        ('consolidated', 'Consolidé'), # Ajout d'un statut pour les colis groupés
    ]

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='parcels', null=True, blank=True)
    tracking_number = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=20, choices=PARCEL_STATUS_CHOICES, default='pending')
    current_location = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-last_updated']
        verbose_name = "Colis"
        verbose_name_plural = "Colis"

    def __str__(self):
        return self.tracking_number

class Consolidation(models.Model):
    CONSOLIDATION_STATUS_CHOICES = [
        ('pending', 'En attente'),
        ('processing', 'En traitement'),
        ('completed', 'Terminé'),
        ('cancelled', 'Annulé'),
    ]

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='consolidations')
    parcels = models.ManyToManyField(Parcel, related_name='consolidations')
    request_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=CONSOLIDATION_STATUS_CHOICES, default='pending')
    # Vous pouvez ajouter d'autres champs comme le coût du groupage, l'adresse de livraison finale, etc.

    class Meta:
        ordering = ['-request_date']
        verbose_name = "Groupage"
        verbose_name_plural = "Groupages"

    def __str__(self):
        return f"Groupage {self.id} par {self.user.email}"