from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import PublicUUIDModel


class Expense(PublicUUIDModel):
    ENTRY_EXPENSE = 'expense'
    ENTRY_LOSS = 'loss'
    ENTRY_TYPE_CHOICES = [
        (ENTRY_EXPENSE, _('Dépense')),
        (ENTRY_LOSS, _('Perte')),
    ]

    name = models.CharField(max_length=200, verbose_name=_('Bénéficiaire'))
    category = models.CharField(max_length=100, verbose_name=_('Catégorie'))
    entry_type = models.CharField(
        max_length=20,
        choices=ENTRY_TYPE_CHOICES,
        default=ENTRY_EXPENSE,
        verbose_name=_('Type'),
        db_index=True,
    )
    description = models.TextField(blank=True, default='', verbose_name=_('Description'))
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_('Montant'),
    )
    currency = models.CharField(max_length=10, default='USD', verbose_name=_('Devise'))
    expense_date = models.DateField(default=timezone.localdate, verbose_name=_('Date'))
    clients = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='accounting_expenses',
        verbose_name=_('Clients concernés'),
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recorded_expenses',
        verbose_name=_('Enregistrée par'),
    )
    proof_image = models.ImageField(
        upload_to='expenses/proofs/%Y/%m/',
        blank=True,
        null=True,
        verbose_name=_('Preuve (reçu / capture)'),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-expense_date', '-created_at']
        verbose_name = _('Dépense')
        verbose_name_plural = _('Dépenses')

    def __str__(self):
        return f'{self.name} - {self.amount} {self.currency}'


class SupportMessage(PublicUUIDModel):
    """Message de chat Service client (admin ↔ client)."""

    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='support_threads',
        verbose_name=_('Client'),
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='support_messages_sent',
        verbose_name=_('Expéditeur'),
    )
    body = models.TextField(blank=True, default='', verbose_name=_('Message'))
    attachment = models.ImageField(
        upload_to='support_chat/%Y/%m/',
        blank=True,
        null=True,
        verbose_name=_('Pièce jointe'),
    )
    is_read = models.BooleanField(default=False, db_index=True, verbose_name=_('Lu'))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = _('Message support')
        verbose_name_plural = _('Messages support')

    def __str__(self):
        return f'{self.sender_id} → {self.client_id}: {self.body[:40]}'
