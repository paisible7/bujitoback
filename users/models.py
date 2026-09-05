from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _

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
    email = models.EmailField(_('email address'), unique=True)
    phone_number = models.CharField(max_length=20, unique=True, blank=True, null=True)
    full_name = models.CharField(max_length=255, blank=True, default='')
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
