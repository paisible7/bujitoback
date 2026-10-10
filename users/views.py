from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from django.db.models import Q, Count
from django.contrib.auth import get_user_model

from .roles import (
    CLIENT_ROLES,
    ROLE_ADMIN,
    ROLE_CLIENT,
    is_app_admin,
    is_platform_superuser,
    normalize_role,
)
from .permissions import IsAppAdmin
from .serializers import (
    RegisterSerializer,
    UserSerializer,
    AdminCreateUserSerializer,
    AdminUserUpdateSerializer,
    AdminAgentUpdateSerializer,
    ProfileUpdateSerializer,
    CustomTokenObtainPairSerializer,
    PasswordResetVerifySerializer,
    PasswordResetSerializer,
    build_china_warehouse_address,
    build_china_air_address,
    build_china_sea_address,
)
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from core.serializers import UUIDLookupMixin
from .admin_permissions import normalize_admin_permissions
from parcels.pagination import OptionalPageNumberPagination

User = get_user_model()


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            user = serializer.save()
        except Exception as exc:
            # Contrainte unique DB (email / téléphone) → message clair.
            from django.db import IntegrityError

            if isinstance(exc, IntegrityError):
                msg = str(exc).lower()
                if 'phone' in msg:
                    return Response(
                        {'phone_number': ['Un compte existe déjà avec ce numéro.']},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                return Response(
                    {'email': ['Un compte existe déjà avec cet email.']},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            raise
        refresh = RefreshToken.for_user(user)
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'email': user.email,
            'role': normalize_role(user.role),
            'full_name': user.full_name,
            'phone_number': user.phone_number,
            'city': getattr(user, 'city', '') or '',
            'stars': getattr(user, 'stars', 0) or 0,
            'admin_permissions': normalize_admin_permissions(
                getattr(user, 'admin_permissions', None)
            ),
            'china_warehouse_address': build_china_warehouse_address(
                user.full_name,
                user.phone_number,
                getattr(user, 'city', '') or '',
            ),
            'china_air_address': build_china_air_address(
                user.full_name,
                user.phone_number,
                getattr(user, 'city', '') or '',
            ),
            'china_sea_address': build_china_sea_address(
                user.full_name,
                user.phone_number,
                getattr(user, 'city', '') or '',
            ),
        }, status=status.HTTP_201_CREATED)


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
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def _enriched_user(self, request):
        from parcels.models import Parcel
        from parcels.ownership import parcels_for_user_q
        from parcels.stats import PARCEL_RECEIVED_STATUSES, PARCEL_SENT_STATUSES

        user = (
            User.objects.filter(pk=request.user.pk)
            .annotate(orders_count=Count('orders', distinct=True))
            .first()
        ) or request.user
        visible = Parcel.objects.filter(
            parcels_for_user_q(request.user)
        ).distinct()
        user.parcels_count = visible.count()
        user.parcels_received_count = visible.filter(
            status__in=PARCEL_RECEIVED_STATUSES
        ).count()
        user.parcels_sent_count = visible.filter(
            status__in=PARCEL_SENT_STATUSES
        ).count()
        if not hasattr(user, 'orders_count'):
            user.orders_count = request.user.orders.count()
        return user

    def get(self, request):
        user = self._enriched_user(request)
        serializer = UserSerializer(user, context={'request': request})
        return Response(serializer.data)

    def patch(self, request):
        serializer = ProfileUpdateSerializer(
            request.user,
            data=request.data,
            partial=True,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        user = self._enriched_user(request)
        return Response(UserSerializer(user, context={'request': request}).data)


class UserListCreateView(generics.ListCreateAPIView):
    """
    Liste / création d'utilisateurs.
    - Admin : voit et crée des clients
    - Superuser : voit clients + admins, peut créer clients et admins
    """
    permission_classes = [IsAuthenticated, IsAppAdmin]
    pagination_class = OptionalPageNumberPagination

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return AdminCreateUserSerializer
        return UserSerializer

    def get_queryset(self):
        from parcels.stats import PARCEL_RECEIVED_STATUSES, PARCEL_SENT_STATUSES

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
        return qs.annotate(
            orders_count=Count('orders', distinct=True),
            parcels_count=Count('orders__parcels', distinct=True),
            parcels_received_count=Count(
                'orders__parcels',
                filter=Q(orders__parcels__status__in=PARCEL_RECEIVED_STATUSES),
                distinct=True,
            ),
            parcels_sent_count=Count(
                'orders__parcels',
                filter=Q(orders__parcels__status__in=PARCEL_SENT_STATUSES),
                distinct=True,
            ),
        )

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


class UserAdminDetailView(UUIDLookupMixin, generics.RetrieveUpdateAPIView):
    """Admin : détail / mise à jour (étoiles) d'un utilisateur."""

    permission_classes = [IsAuthenticated, IsAppAdmin]
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_queryset(self):
        actor = self.request.user
        if is_platform_superuser(actor):
            qs = User.objects.filter(
                role__in=[ROLE_CLIENT, ROLE_ADMIN, 'user'],
            )
        else:
            qs = User.objects.filter(role__in=CLIENT_ROLES)
        from parcels.stats import PARCEL_RECEIVED_STATUSES, PARCEL_SENT_STATUSES

        return qs.annotate(
            orders_count=Count('orders', distinct=True),
            parcels_count=Count('orders__parcels', distinct=True),
            parcels_received_count=Count(
                'orders__parcels',
                filter=Q(orders__parcels__status__in=PARCEL_RECEIVED_STATUSES),
                distinct=True,
            ),
            parcels_sent_count=Count(
                'orders__parcels',
                filter=Q(orders__parcels__status__in=PARCEL_SENT_STATUSES),
                distinct=True,
            ),
        )

    def get_serializer_class(self):
        if self.request.method == 'PATCH':
            return AdminUserUpdateSerializer
        return UserSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['request'] = self.request
        return ctx

    def patch(self, request, *args, **kwargs):
        instance = self.get_object()
        # Super Admin : mise à jour permissions / activation d'un agent.
        if (
            is_platform_superuser(request.user)
            and normalize_role(instance.role) == ROLE_ADMIN
            and (
                'admin_permissions' in request.data
                or 'is_active' in request.data
            )
        ):
            serializer = AdminAgentUpdateSerializer(
                instance, data=request.data, partial=True
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()
            instance.refresh_from_db()
            return Response(
                UserSerializer(instance, context={'request': request}).data
            )

        serializer = AdminUserUpdateSerializer(
            instance, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        instance.refresh_from_db()
        return Response(
            UserSerializer(instance, context={'request': request}).data
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
