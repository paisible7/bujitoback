from django.urls import path
from .views import (
    RegisterView,
    UserProfileView,
    UserListCreateView,
    UserAdminDetailView,
    AgentSalaryView,
    PasswordResetVerifyView,
    PasswordResetView,
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='auth_register'),
    path('profile/', UserProfileView.as_view(), name='auth_profile'),
    path(
        'profile/salary/',
        AgentSalaryView.as_view(),
        name='auth_profile_salary',
    ),
    path('users/', UserListCreateView.as_view(), name='auth_users_list'),
    path(
        'users/<str:pk>/salary/',
        AgentSalaryView.as_view(),
        name='auth_users_salary',
    ),
    path(
        'users/<str:pk>/',
        UserAdminDetailView.as_view(),
        name='auth_users_detail',
    ),
    path(
        'password-reset/verify/',
        PasswordResetVerifyView.as_view(),
        name='auth_password_reset_verify',
    ),
    path(
        'password-reset/',
        PasswordResetView.as_view(),
        name='auth_password_reset',
    ),
]
