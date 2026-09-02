from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from .serializers import (
    RegisterSerializer,
    UserSerializer,
    CustomTokenObtainPairSerializer,
    PasswordResetVerifySerializer,
    PasswordResetSerializer,
)
from django.contrib.auth import get_user_model

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
                'role': user.role,
                'full_name': user.full_name,
                'phone_number': user.phone_number, # Ajout de phone_number à la réponse
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


class UserListView(generics.ListAPIView):
    """Liste des clients pour l'admin."""
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self.request.user, 'role', None) != 'admin':
            return User.objects.none()

        qs = User.objects.filter(role='user', is_active=True).order_by('email')
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(email__icontains=search) | qs.filter(full_name__icontains=search)
        return qs

    def list(self, request, *args, **kwargs):
        if request.user.role != 'admin':
            return Response(
                {"detail": "Action réservée aux administrateurs."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().list(request, *args, **kwargs)


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