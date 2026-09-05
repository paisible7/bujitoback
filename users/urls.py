from django.urls import path
from .views import (
    RegisterView,
    UserProfileView,
    UserListCreateView,
    PasswordResetVerifyView,
    PasswordResetView,
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='auth_register'),
    path('profile/', UserProfileView.as_view(), name='auth_profile'),
    path('users/', UserListCreateView.as_view(), name='auth_users_list'),
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
