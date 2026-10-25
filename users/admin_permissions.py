"""Catalogue des permissions admin.

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
PERM_STATS = 'stats'
PERM_ACCOUNTING = 'accounting'
PERM_CLIENT_SERVICE = 'client_service'
PERM_AGENTS = 'agents'
PERM_EXPENSES_CHINA = 'expenses_china'
PERM_SHIPMENTS_RECEPTION = 'shipments_reception'

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
    PERM_STATS,
    PERM_ACCOUNTING,
    PERM_CLIENT_SERVICE,
    PERM_AGENTS,
    PERM_EXPENSES_CHINA,
    PERM_SHIPMENTS_RECEPTION,
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
    PERM_STATS: 'Statistiques',
    PERM_ACCOUNTING: 'Comptabilité',
    PERM_CLIENT_SERVICE: 'Service client',
    PERM_AGENTS: 'Agents & accès',
    PERM_EXPENSES_CHINA: 'Dépenses Chine',
    PERM_SHIPMENTS_RECEPTION: 'Réception MCO (aéroport)',
}


# Presets métier (référence Super Admin / Flutter).
ADMIN_ROLE_PRESETS: dict[str, tuple[str, ...]] = {
    'parcel_manager': (
        PERM_GROUPING,
        PERM_SHIPMENTS,
        PERM_PARCELS,
        PERM_IMPORT,
        PERM_EXPENSES_CHINA,
    ),
    'client_service': (
        PERM_CLIENT_SERVICE,
        PERM_PARCELS,
    ),
    'accountant': (
        PERM_ACCOUNTING,
        PERM_PAYMENTS,
        PERM_STATS,
    ),
    'reception': (
        PERM_SHIPMENTS_RECEPTION,
    ),
}


def normalize_admin_permissions(raw) -> list[str]:
    """Nettoie une liste de permissions ; ignore les clés inconnues ; déduplique."""
    if raw is None:
        return []
    if isinstance(raw, str):
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
        return True
    perms = get_user_admin_permissions(user)
    if not perms:
        if getattr(user, 'permissions_restricted', False):
            return False
        return True
    return perm in perms


def admin_has_full_access(user) -> bool:
    from .roles import is_platform_superuser, is_app_admin

    if is_platform_superuser(user):
        return True
    if not is_app_admin(user):
        return False
    if getattr(user, 'permissions_restricted', False):
        return False
    return not get_user_admin_permissions(user)


def effective_admin_permissions(user) -> list[str]:
    from .roles import is_app_admin, is_platform_superuser

    if not is_app_admin(user):
        return []
    if is_platform_superuser(user) or admin_has_full_access(user):
        return list(ADMIN_PERMISSION_KEYS)
    return get_user_admin_permissions(user)


def can_pay_worker_salary(user) -> bool:
    """Super Admin ou comptable (permission accounting)."""
    from .roles import is_platform_superuser

    if is_platform_superuser(user):
        return True
    return has_admin_permission(user, PERM_ACCOUNTING)


def can_list_workers_for_salary(user) -> bool:
    return can_pay_worker_salary(user)


def is_shipments_reception_only(user) -> bool:
    """Accès MCO limité à la réception aéroport (arrived)."""
    from .roles import is_platform_superuser

    if is_platform_superuser(user) or admin_has_full_access(user):
        return False
    if has_admin_permission(user, PERM_SHIPMENTS):
        return False
    return has_admin_permission(user, PERM_SHIPMENTS_RECEPTION)


def can_manage_china_expenses(user) -> bool:
    from .roles import is_platform_superuser

    if is_platform_superuser(user):
        return True
    return has_admin_permission(user, PERM_ACCOUNTING) or has_admin_permission(
        user, PERM_EXPENSES_CHINA
    )


def can_view_full_accounting(user) -> bool:
    from .roles import is_platform_superuser

    if is_platform_superuser(user):
        return True
    return has_admin_permission(user, PERM_ACCOUNTING)
