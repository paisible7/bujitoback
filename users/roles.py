"""Rôles applicatifs Bujito Digital."""
from __future__ import annotations

ROLE_CLIENT = 'client'
ROLE_ADMIN = 'admin'
ROLE_SUPERUSER = 'superuser'
# Ancien libellé conservé en lecture pour compatibilité
ROLE_USER_LEGACY = 'user'

ROLE_CHOICES = [
    (ROLE_CLIENT, 'Client'),
    (ROLE_ADMIN, 'Admin'),
    (ROLE_SUPERUSER, 'Superuser'),
]

APP_ADMIN_ROLES = frozenset({ROLE_ADMIN, ROLE_SUPERUSER})
CLIENT_ROLES = frozenset({ROLE_CLIENT, ROLE_USER_LEGACY})


def normalize_role(role: str | None) -> str:
    value = (role or ROLE_CLIENT).strip().lower()
    if value == ROLE_USER_LEGACY:
        return ROLE_CLIENT
    if value in {ROLE_CLIENT, ROLE_ADMIN, ROLE_SUPERUSER}:
        return value
    return ROLE_CLIENT


def is_app_admin(user) -> bool:
    """Admin app ou superuser (accès features admin Flutter)."""
    if user is None or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    return normalize_role(getattr(user, 'role', None)) in APP_ADMIN_ROLES


def is_platform_superuser(user) -> bool:
    """Seul le superuser a Django admin + création d'admins."""
    if user is None or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    return normalize_role(getattr(user, 'role', None)) == ROLE_SUPERUSER


def is_client_user(user) -> bool:
    if user is None:
        return False
    return normalize_role(getattr(user, 'role', None)) in CLIENT_ROLES


def apply_role_flags(user) -> None:
    """Synchronise is_staff / is_superuser avec le rôle métier."""
    role = normalize_role(getattr(user, 'role', None))
    user.role = role
    if role == ROLE_SUPERUSER:
        user.is_staff = True
        user.is_superuser = True
    else:
        # Admin app et clients : pas d'accès Django admin
        user.is_staff = False
        user.is_superuser = False
