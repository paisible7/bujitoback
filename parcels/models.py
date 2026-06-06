from django.db import models
from users.models import CustomUser # Assurez-vous que le chemin est correct

class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'En attente'),
        ('processing', 'En traitement'),
        ('shipped', 'Expédiée'), # Correction ici: suppression de la parenthèse ouvrante en trop
        ('delivered', 'Livrée'),
        ('cancelled', 'Annulée'),
    ]

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='orders')
    order_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    # Vous pouvez ajouter d'autres champs comme les articles commandés, l'adresse de livraison, etc.

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
    ]

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='parcels', null=True, blank=True)
    tracking_number = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=20, choices=PARCEL_STATUS_CHOICES, default='pending')
    current_location = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    last_updated = models.DateTimeField(auto_now=True)
    # Vous pouvez ajouter d'autres champs comme le poids, les dimensions, l'historique de suivi, etc.

    class Meta:
        ordering = ['-last_updated']
        verbose_name = "Colis"
        verbose_name_plural = "Colis"

    def __str__(self):
        return self.tracking_number
