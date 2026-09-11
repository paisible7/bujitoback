from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from django.db.models import Q
from django.contrib.auth import get_user_model

from .serializers import (
    RegisterSerializer,
    UserSerializer,
    AdminCreateUserSerializer,
    CustomTokenObtainPairSerializer,
    PasswordResetVerifySerializer,
    PasswordResetSerializer,
    build_china_warehouse_address,
)
from .roles import (
    CLIENT_ROLES,
    ROLE_ADMIN,
    ROLE_CLIENT,
    is_app_admin,
    is_platform_superuser,
    normalize_role,
)
from .permissions import IsAppAdmin

User = get_user_model()


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            refresh = RefreshToken.for_user(user)
            return Response({
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'email': user.email,
                'role': normalize_role(user.role),
                'full_name': user.full_name,
                'phone_number': user.phone_number,
                'city': getattr(user, 'city', '') or '',
                'china_warehouse_address': build_china_warehouse_address(
                    user.full_name,
                    user.phone_number,
                    getattr(user, 'city', '') or '',
                ),
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        email = request.data.get('email') or request.data.get('username')
        print(
            f'[auth/login] host={request.get_host()!r} '
            f'email={email!r} has_password={bool(request.data.get("password"))}'
        )
        response = super().post(request, *args, **kwargs)
        print(f'[auth/login] status={response.status_code}')
        return response


class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)


class UserListCreateView(generics.ListCreateAPIView):
    """
    Liste / création d'utilisateurs.
    - Admin : voit et crée des clients
    - Superuser : voit clients + admins, peut créer clients et admins
    """
    permission_classes = [IsAuthenticated, IsAppAdmin]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return AdminCreateUserSerializer
        return UserSerializer

    def get_queryset(self):
        actor = self.request.user
        if is_platform_superuser(actor):
            qs = User.objects.filter(
                role__in=[ROLE_CLIENT, ROLE_ADMIN, 'user'],
            ).order_by('role', 'email')
        else:
            qs = User.objects.filter(role__in=CLIENT_ROLES).order_by('email')

        role_filter = self.request.query_params.get('role', '').strip().lower()
        if role_filter:
            role_filter = normalize_role(role_filter)
            if role_filter == ROLE_CLIENT:
                qs = qs.filter(role__in=CLIENT_ROLES)
            else:
                qs = qs.filter(role=role_filter)

        # Par défaut pour l'écran notif : clients actifs seulement
        clients_only = self.request.query_params.get('clients_only', '').lower() in (
            '1', 'true', 'yes',
        )
        if clients_only:
            qs = qs.filter(role__in=CLIENT_ROLES, is_active=True)

        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(email__icontains=search)
                | Q(full_name__icontains=search)
                | Q(phone_number__icontains=search)
            )
        return qs

    def create(self, request, *args, **kwargs):
        serializer = AdminCreateUserSerializer(
            data=request.data,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            UserSerializer(user).data,
            status=status.HTTP_201_CREATED,
        )


class PasswordResetVerifyView(APIView):
    """Étape 1 : vérifier que l'email correspond à un compte actif."""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            {'detail': 'Email vérifié. Vous pouvez définir un nouveau mot de passe.'},
            status=status.HTTP_200_OK,
        )


class PasswordResetView(APIView):
    """Étape 2 : réinitialiser le mot de passe (sans lien email pour l'instant)."""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {'detail': 'Mot de passe mis à jour avec succès.'},
            status=status.HTTP_200_OK,
        )
