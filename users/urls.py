from django.urls import path
from .views import RegisterView, UserProfileView, UserListView

urlpatterns = [
    path('register/', RegisterView.as_view(), name='auth_register'),
    path('profile/', UserProfileView.as_view(), name='auth_profile'),
    path('users/', UserListView.as_view(), name='auth_users_list'),
]
