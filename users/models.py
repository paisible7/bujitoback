import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import PublicUUIDModel
from .roles import (
    ROLE_CHOICES,
    ROLE_CLIENT,
    ROLE_SUPERUSER,
    apply_role_flags,
    normalize_role,
)


class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        role = normalize_role(extra_fields.pop('role', ROLE_CLIENT))
        user = self.model(email=email, role=role, **extra_fields)
        apply_role_flags(user)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields['role'] = ROLE_SUPERUSER
        extra_fields['is_staff'] = True
        extra_fields['is_superuser'] = True
        return self.create_user(email, password, **extra_fields)


class CustomUser(AbstractUser):
    username = None
    uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
        verbose_name=_('UUID public'),
    )
    email = models.EmailField(_('email address'), unique=True)
    phone_number = models.CharField(max_length=20, unique=True, blank=True, null=True)
    full_name = models.CharField(max_length=255, blank=True, default='')
    city = models.CharField(max_length=100, blank=True, default='', verbose_name=_('Ville'))
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default=ROLE_CLIENT,
    )
    language = models.CharField(
        max_length=5,
        choices=[('fr', 'Français'), ('en', 'English')],
        default='fr',
    )
    stars = models.PositiveSmallIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
        verbose_name=_('Étoiles client (0–5)'),
        help_text=_('Notation admin : 0 = non noté, 1 à 5 = niveau client.'),
    )
    # Fondation permissions admin : liste vide = accès total (compatibilité).
    # Attribution UI : Super Admin only.
    admin_permissions = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_('Permissions admin'),
        help_text=_(
            'Clés de modules admin (orders, parcels, …). '
            'Liste vide = tous les droits (comportement actuel).'
        ),
    )
    profile_photo = models.ImageField(
        upload_to='users/avatars/%Y/%m/',
        blank=True,
        null=True,
        verbose_name=_('Photo de profil'),
    )
    # Pourcentages de commission par service (travailleurs / agents).
    service_percentages = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_('Pourcentages par service'),
        help_text=_('Ex: {"orders": 5, "grouping": 7, "client_service": 5}'),
    )
    WORKER_STATUS_PENDING = 'pending'
    WORKER_STATUS_ACTIVE = 'active'
    WORKER_STATUS_DISABLED = 'disabled'
    WORKER_STATUS_CHOICES = [
        (WORKER_STATUS_PENDING, _('En attente')),
        (WORKER_STATUS_ACTIVE, _('Actif')),
        (WORKER_STATUS_DISABLED, _('Désactivé')),
    ]
    worker_status = models.CharField(
        max_length=20,
        choices=WORKER_STATUS_CHOICES,
        default=WORKER_STATUS_ACTIVE,
        db_index=True,
        verbose_name=_('Statut travailleur'),
        help_text=_('active / pending / disabled — pour les agents (rôle admin).'),
    )
    # True = liste vide de permissions = aucun module (travailleurs).
    # False = liste vide = accès total (admins historiques).
    permissions_restricted = models.BooleanField(
        default=False,
        verbose_name=_('Permissions restreintes'),
        help_text=_(
            'Si activé, une liste de permissions vide n\'accorde aucun module admin.'
        ),
    )

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    def save(self, *args, **kwargs):
        self.role = normalize_role(self.role)
        apply_role_flags(self)
        super().save(*args, **kwargs)

    @property
    def is_app_admin(self) -> bool:
        from .roles import is_app_admin as _is_app_admin
        return _is_app_admin(self)

    def __str__(self):
        return self.email


WORKER_SERVICE_KEYS = (
    'orders',
    'grouping',
    'transfers',
    'shipments',
    'client_service',
)

# Service travailleur → permission admin correspondante.
WORKER_SERVICE_TO_PERM = {
    'orders': 'orders',
    'grouping': 'grouping',
    'transfers': 'payments',
    'shipments': 'shipments',
    'client_service': 'client_service',
}

WORKER_STATUS_VALUES = frozenset({
    CustomUser.WORKER_STATUS_PENDING,
    CustomUser.WORKER_STATUS_ACTIVE,
    CustomUser.WORKER_STATUS_DISABLED,
})


def normalize_service_percentages(raw) -> dict:
    """Ne conserve que les clés de service connues, pourcentages 0–100."""
    if not isinstance(raw, dict):
        return {}
    out = {}
    for key in WORKER_SERVICE_KEYS:
        if key not in raw:
            continue
        try:
            val = float(raw[key])
        except (TypeError, ValueError):
            continue
        if val < 0:
            val = 0.0
        if val > 100:
            val = 100.0
        out[key] = round(val, 2)
    return out


def normalize_worker_status(raw, default=CustomUser.WORKER_STATUS_ACTIVE) -> str:
    value = str(raw or '').strip().lower()
    if value in WORKER_STATUS_VALUES:
        return value
    return default


def apply_worker_status(user, status: str) -> None:
    """Aligne worker_status et is_active."""
    status = normalize_worker_status(status)
    user.worker_status = status
    user.is_active = status == CustomUser.WORKER_STATUS_ACTIVE


class AgentSalaryPayment(PublicUUIDModel):
    """Paiement de salaire / commission envoyé à un travailleur."""

    STATUS_PENDING = 'pending'
    STATUS_PAID = 'paid'
    STATUS_CHOICES = [
        (STATUS_PENDING, _('En attente')),
        (STATUS_PAID, _('Payé')),
    ]

    worker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='salary_payments',
        verbose_name=_('Travailleur'),
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('Montant'))
    currency = models.CharField(max_length=10, default='USD', verbose_name=_('Devise'))
    service = models.CharField(
        max_length=40,
        blank=True,
        default='',
        verbose_name=_('Service'),
        help_text=_('orders, grouping, transfers, shipments, client_service'),
    )
    paid_at = models.DateTimeField(default=timezone.now, verbose_name=_('Date de paiement'))
    note = models.CharField(max_length=400, blank=True, default='', verbose_name=_('Note'))
    proof_image = models.ImageField(
        upload_to='workers/salary/%Y/%m/',
        blank=True,
        null=True,
        verbose_name=_('Preuve de paiement'),
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PAID,
        db_index=True,
        verbose_name=_('Statut'),
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recorded_salary_payments',
        verbose_name=_('Enregistré par'),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-paid_at', '-created_at']
        verbose_name = _('Paiement salaire agent')
        verbose_name_plural = _('Paiements salaires agents')

    def __str__(self):
        return f'{self.worker_id} {self.amount} {self.currency}'
