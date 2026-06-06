from rest_framework import permissions

class IsAdminUser(permissions.BasePermission):
    """
    Custom permission to only allow admin users to access an object.
    Assumes the user model has a 'role' field.
    """

    def has_permission(self, request, view):
        # Allow read-only access for any authenticated user (GET, HEAD, OPTIONS)
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated

        # Write access (POST, PUT, PATCH, DELETE) only for admin users
        return request.user and request.user.is_authenticated and request.user.role == 'admin'

    def has_object_permission(self, request, view, obj):
        # Object-level permissions are not strictly needed for list views,
        # but can be useful for detail views.
        # For now, we'll apply the same logic: read for all authenticated, write for admin.
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        
        return request.user and request.user.is_authenticated and request.user.role == 'admin'
