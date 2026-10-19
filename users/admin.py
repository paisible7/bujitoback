from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import AgentSalaryPayment, CustomUser
from .roles import apply_role_flags, normalize_role


@admin.register(CustomUser)
class CustomUserAdmin(BaseUserAdmin):
    ordering = ('email',)
    list_display = (
        'email',
        'full_name',
        'phone_number',
        'role',
        'is_staff',
        'is_active',
        'is_superuser',
    )
    list_filter = ('role', 'is_staff', 'is_active', 'is_superuser')
    search_fields = ('email', 'full_name', 'phone_number')

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Informations personnelles'), {
            'fields': ('full_name', 'phone_number', 'language'),
        }),
        (_('Rôles et permissions'), {
            'fields': (
                'role',
                'admin_permissions',
                'service_percentages',
                'worker_status',
                'permissions_restricted',
                'is_active',
                'is_staff',
                'is_superuser',
                'groups',
                'user_permissions',
            ),
        }),
        (_('Dates importantes'), {
            'fields': ('last_login', 'date_joined'),
        }),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'email',
                'full_name',
                'phone_number',
                'role',
                'password1',
                'password2',
                'is_active',
            ),
        }),
    )

    filter_horizontal = ('groups', 'user_permissions')
    # Lecture seule pour cette fondation : l'attribution UI viendra plus tard.
    readonly_fields = ('last_login', 'date_joined', 'admin_permissions')

    def save_model(self, request, obj, form, change):
        obj.role = normalize_role(obj.role)
        apply_role_flags(obj)
        super().save_model(request, obj, form, change)

    def has_module_permission(self, request):
        # Django admin réservé aux superusers
        return bool(request.user and request.user.is_active and request.user.is_superuser)

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_delete_permission(self, request, obj=None):
        return self.has_module_permission(request)


@admin.register(AgentSalaryPayment)
class AgentSalaryPaymentAdmin(admin.ModelAdmin):
    list_display = (
        'worker',
        'amount',
        'currency',
        'service',
        'status',
        'paid_at',
    )
    list_filter = ('status', 'currency', 'service')
    search_fields = ('worker__email', 'worker__full_name', 'note')
    readonly_fields = ('uuid', 'created_at')
