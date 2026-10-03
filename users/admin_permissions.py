"""Catalogue des permissions admin (fondation — pas encore appliqué à l'UI).

Règle de compatibilité (has_admin_permission) :
- Super Admin → toujours True
- Admin avec liste vide / absente → True (accès total, comme aujourd'hui)
- Admin avec liste non vide → True seulement si la clé est présente
- Client / non-admin → False
"""
from __future__ import annotations


PERM_ORDERS = 'orders'
PERM_PARCELS = 'parcels'
PERM_GROUPING = 'grouping'
PERM_SHIPMENTS = 'shipments'
PERM_PAYMENTS = 'payments'
PERM_USERS = 'users'
PERM_PRICING = 'pricing'
PERM_ADS = 'ads'
PERM_NOTIFICATIONS = 'notifications'
PERM_IMPORT = 'import'

ADMIN_PERMISSION_KEYS: tuple[str, ...] = (
    PERM_ORDERS,
    PERM_PARCELS,
    PERM_GROUPING,
    PERM_SHIPMENTS,
    PERM_PAYMENTS,
    PERM_USERS,
    PERM_PRICING,
    PERM_ADS,
    PERM_NOTIFICATIONS,
    PERM_IMPORT,
)

ADMIN_PERMISSION_SET = frozenset(ADMIN_PERMISSION_KEYS)

# Libellés FR (référence / admin Django) — Flutter a ses propres i18n.
ADMIN_PERMISSION_LABELS_FR: dict[str, str] = {
    PERM_ORDERS: 'Commandes',
    PERM_PARCELS: 'Colis',
    PERM_GROUPING: 'Groupage',
    PERM_SHIPMENTS: 'Expéditions MCO',
    PERM_PAYMENTS: 'Paiements',
    PERM_USERS: 'Utilisateurs',
    PERM_PRICING: 'Tarifs',
    PERM_ADS: 'Affiches',
    PERM_NOTIFICATIONS: 'Notifications',
    PERM_IMPORT: 'Import',
}


def normalize_admin_permissions(raw) -> list[str]:
    """Nettoie une liste de permissions ; ignore les clés inconnues ; déduplique."""
    if raw is None:
        return []
    if isinstance(raw, str):
        # "orders,parcels" ou JSON-like simple
        raw = [p.strip() for p in raw.split(',') if p.strip()]
    if not isinstance(raw, (list, tuple, set)):
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in raw:
        key = str(item or '').strip().lower()
        if not key or key not in ADMIN_PERMISSION_SET or key in seen:
            continue
        seen.add(key)
        cleaned.append(key)
    return cleaned


def get_user_admin_permissions(user) -> list[str]:
    """Permissions normalisées stockées sur l'utilisateur (peut être vide)."""
    if user is None:
        return []
    return normalize_admin_permissions(getattr(user, 'admin_permissions', None))


def has_admin_permission(user, key: str) -> bool:
    """
    Vérifie une permission admin.

    Ne remplace pas is_app_admin pour l'accès global : à brancher plus tard
    sur les menus / vues. Pour l'instant, liste vide = accès total (admins).
    """
    from .roles import is_app_admin, is_platform_superuser, normalize_role, ROLE_ADMIN

    if user is None or not getattr(user, 'is_authenticated', False):
        return False
    perm = (key or '').strip().lower()
    if perm not in ADMIN_PERMISSION_SET:
        return False
    if is_platform_superuser(user):
        return True
    if not is_app_admin(user):
        return False
    if normalize_role(getattr(user, 'role', None)) != ROLE_ADMIN:
        # Autres rôles admin-like : accès total (sécurité future)
        return True
    perms = get_user_admin_permissions(user)
    if not perms:
        # Compatibilité : admin sans droits assignés = tout
        return True
    return perm in perms


def admin_has_full_access(user) -> bool:
    """True si superuser ou admin sans restriction (liste vide)."""
    from .roles import is_platform_superuser, is_app_admin

    if is_platform_superuser(user):
        return True
    if not is_app_admin(user):
        return False
    return not get_user_admin_permissions(user)


def effective_admin_permissions(user) -> list[str]:
    """
    Liste effective pour le client (Flutter).

    Super Admin / admin sans restriction → catalogue complet.
    Admin restreint → ses clés uniquement.
    Autres → [].
    """
    from .roles import is_app_admin, is_platform_superuser

    if not is_app_admin(user):
        return []
    if is_platform_superuser(user) or admin_has_full_access(user):
        return list(ADMIN_PERMISSION_KEYS)
    return get_user_admin_permissions(user)
