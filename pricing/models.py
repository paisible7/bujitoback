from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _


class BusinessSettings(models.Model):
    """
    Singleton : tarifs d'expédition / groupage + taux de change.
    Toujours accéder via BusinessSettings.load().
    """

    # --- Expédition ---
    ordinary_rate_per_kg = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("17.00"),
        verbose_name=_("Colis ordinaire — $/kg"),
    )
    ordinary_days = models.PositiveSmallIntegerField(
        default=21,
        verbose_name=_("Colis ordinaire — délai (jours)"),
    )

    express_available = models.BooleanField(
        default=False,
        verbose_name=_("Express disponible"),
    )
    express_rate_per_kg = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("Express — $/kg"),
    )
    express_days = models.PositiveSmallIntegerField(
        default=8,
        verbose_name=_("Express — délai (jours)"),
    )

    sensitive_rate_per_kg = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("25.00"),
        verbose_name=_("Colis sensibles — $/kg"),
    )
    sensitive_days = models.PositiveSmallIntegerField(
        default=21,
        verbose_name=_("Colis sensibles — délai (jours)"),
    )
    sensitive_note = models.CharField(
        max_length=255,
        default="batterie, liquide, médicaments, perruque, montres, cosmétique",
        verbose_name=_("Colis sensibles — exemples"),
    )

    phone_flat_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("36.00"),
        verbose_name=_("Téléphone — forfait $"),
    )
    phone_days = models.PositiveSmallIntegerField(
        default=21,
        verbose_name=_("Téléphone — délai (jours)"),
    )

    # --- Groupage ---
    grouping_flat_max_kg = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("4.00"),
        verbose_name=_("Groupage forfait — poids max (kg)"),
    )
    grouping_flat_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("5.00"),
        verbose_name=_("Groupage forfait — $ (1–4 kg)"),
    )
    grouping_rate_per_kg = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("2.50"),
        verbose_name=_("Groupage — $/kg (≥ 5 kg)"),
    )

    # --- Taux de change (1 USD = …) ---
    usd_to_cdf = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=Decimal("2270.0000"),
        verbose_name=_("1 USD → CDF (Fc)"),
    )
    usd_to_gbp = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        default=Decimal("0.790000"),
        verbose_name=_("1 USD → GBP (£)"),
    )
    usd_to_xof = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=Decimal("600.0000"),
        verbose_name=_("1 USD → FCFA (XOF)"),
    )

    # --- Adresse entrepôt Chine (globale, affiché sur tous les profils clients) ---
    china_warehouse_phone = models.CharField(
        max_length=50,
        default="18575740344",
        verbose_name=_("Entrepôt Chine — téléphone"),
    )
    china_warehouse_street = models.CharField(
        max_length=500,
        default="佛山市南海区狮山镇塘头村一队新一巷3号bujito",
        verbose_name=_("Entrepôt Chine — adresse"),
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Paramètres tarifs")
        verbose_name_plural = _("Paramètres tarifs")

    def __str__(self):
        return "Tarifs & taux de change"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def load(cls) -> "BusinessSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
