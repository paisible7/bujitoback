from rest_framework import permissions

from .roles import is_app_admin


class IsAdminUser(permissions.BasePermission):
    """
    Lecture pour tout utilisateur authentifié ;
    écriture réservée aux admins app / superusers.
    """

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        return is_app_admin(request.user)

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        return is_app_admin(request.user)


class IsAppAdmin(permissions.BasePermission):
    """Accès réservé aux admins de l'application (admin + superuser)."""

    def has_permission(self, request, view):
        return is_app_admin(request.user)
