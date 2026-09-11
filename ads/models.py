from django.db import models
from django.utils.translation import gettext_lazy as _


# Écrans client où une affiche peut apparaître.
AD_SCREEN_CHOICES = (
    ('home', _('Accueil')),
    ('orders', _('Commandes')),
    ('grouping', _('Groupage')),
    ('tracking', _('Suivi')),
    ('profile', _('Profil')),
)
AD_SCREEN_KEYS = {key for key, _ in AD_SCREEN_CHOICES}


class Advertisement(models.Model):
    """Affiche publicitaire affichée en modal sur les écrans choisis."""

    title = models.CharField(max_length=200, blank=True, default='', verbose_name=_('Titre'))
    image = models.ImageField(upload_to='ads/%Y/%m/', verbose_name=_('Image'))
    sort_order = models.PositiveIntegerField(default=0, verbose_name=_('Ordre'))
    is_active = models.BooleanField(default=True, verbose_name=_('Active'))
    # Ex. ["home", "tracking"]
    screens = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_('Écrans'),
        help_text=_('Liste des clés d\'écran : home, orders, grouping, tracking, profile'),
    )
    starts_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Début d\'affichage'),
        help_text=_('Vide = immédiat'),
    )
    ends_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Fin d\'affichage'),
        help_text=_('Vide = pas de limite'),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Créée le'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Mise à jour'))

    class Meta:
        ordering = ['sort_order', '-created_at']
        verbose_name = _('Affiche publicitaire')
        verbose_name_plural = _('Affiches publicitaires')

    def __str__(self):
        return self.title or f'Affiche #{self.pk}'

    def is_currently_scheduled(self, when=None):
        from django.utils import timezone
        now = when or timezone.now()
        if self.starts_at and now < self.starts_at:
            return False
        if self.ends_at and now > self.ends_at:
            return False
        return True

    def clean_screens(self):
        raw = self.screens or []
        if isinstance(raw, str):
            raw = [s.strip() for s in raw.split(',') if s.strip()]
        cleaned = []
        for item in raw:
            key = str(item).strip().lower()
            if key in AD_SCREEN_KEYS and key not in cleaned:
                cleaned.append(key)
        self.screens = cleaned or ['home']
