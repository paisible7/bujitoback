from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import PublicUUIDModel


class Expense(PublicUUIDModel):
    name = models.CharField(max_length=200, verbose_name=_('Bénéficiaire'))
    category = models.CharField(max_length=100, verbose_name=_('Catégorie'))
    description = models.TextField(blank=True, default='', verbose_name=_('Description'))
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_('Montant'),
    )
    currency = models.CharField(max_length=10, default='USD', verbose_name=_('Devise'))
    expense_date = models.DateField(default=timezone.localdate, verbose_name=_('Date'))
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='accounting_expenses',
        verbose_name=_('Client concerné'),
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recorded_expenses',
        verbose_name=_('Enregistrée par'),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-expense_date', '-created_at']
        verbose_name = _('Dépense')
        verbose_name_plural = _('Dépenses')

    def __str__(self):
        return f'{self.name} - {self.amount} {self.currency}'