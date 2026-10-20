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
    attachment = models.FileField(
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


class ClientFollowUp(PublicUUIDModel):
    """Suivi client : liste à rappeler / à relancer (Service client)."""

    client = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='support_followup',
        verbose_name=_('Client'),
    )
    needs_followup = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name=_('À rappeler / relancer'),
    )
    note = models.CharField(
        max_length=500,
        blank=True,
        default='',
        verbose_name=_('Note de relance'),
    )
    last_reminded_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Dernière relance'),
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='client_followups_updated',
        verbose_name=_('Mis à jour par'),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name = _('Client à relancer')
        verbose_name_plural = _('Clients à relancer')

    def __str__(self):
        return f'FollowUp(client={self.client_id}, active={self.needs_followup})'


class SupportQuickReply(PublicUUIDModel):
    """Réponse rapide (chip) configurable dans le chat Service client."""

    label = models.CharField(max_length=48, verbose_name=_('Libellé'))
    body = models.TextField(verbose_name=_('Message'))
    language = models.CharField(
        max_length=8,
        default='all',
        db_index=True,
        verbose_name=_('Langue'),
        help_text=_('fr, en ou all'),
    )
    sort_order = models.PositiveIntegerField(default=0, verbose_name=_('Ordre'))
    is_active = models.BooleanField(default=True, db_index=True, verbose_name=_('Actif'))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'id']
        verbose_name = _('Réponse rapide support')
        verbose_name_plural = _('Réponses rapides support')

    def __str__(self):
        return self.label


class SupportAutoMessage(PublicUUIDModel):
    """Message automatique : premier contact client ou envoi programmé quotidien."""

    TRIGGER_FIRST_MESSAGE = 'first_client_message'
    TRIGGER_SCHEDULED = 'scheduled_daily'
    TRIGGER_CHOICES = [
        (TRIGGER_FIRST_MESSAGE, _('Après le 1er message client')),
        (TRIGGER_SCHEDULED, _('Envoi programmé (quotidien)')),
    ]

    TARGET_FOLLOWUP = 'followup'
    TARGET_UNREAD = 'unread'
    TARGET_ACTIVE = 'active_threads'
    TARGET_CHOICES = [
        (TARGET_FOLLOWUP, _('Clients à rappeler')),
        (TARGET_UNREAD, _('Conversations non lues')),
        (TARGET_ACTIVE, _('Discussions actives (30 jours)')),
    ]

    name = models.CharField(max_length=100, verbose_name=_('Nom'))
    body = models.TextField(verbose_name=_('Message'))
    language = models.CharField(
        max_length=8,
        default='all',
        db_index=True,
        verbose_name=_('Langue'),
    )
    trigger = models.CharField(
        max_length=32,
        choices=TRIGGER_CHOICES,
        default=TRIGGER_FIRST_MESSAGE,
        db_index=True,
        verbose_name=_('Déclencheur'),
    )
    scheduled_time = models.TimeField(
        null=True,
        blank=True,
        verbose_name=_('Heure d’envoi'),
        help_text=_('Pour un envoi programmé quotidien (fuseau du serveur).'),
    )
    target = models.CharField(
        max_length=32,
        choices=TARGET_CHOICES,
        default=TARGET_FOLLOWUP,
        verbose_name=_('Cibles (programmé)'),
    )
    is_active = models.BooleanField(default=True, db_index=True, verbose_name=_('Actif'))
    last_run_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_('Dernier envoi (jour)'),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name', 'id']
        verbose_name = _('Message auto support')
        verbose_name_plural = _('Messages auto support')

    def __str__(self):
        return self.name
