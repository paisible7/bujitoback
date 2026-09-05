from rest_framework import serializers
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .roles import (
    ROLE_ADMIN,
    ROLE_CLIENT,
    ROLE_SUPERUSER,
    is_platform_superuser,
    normalize_role,
)

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'email', 'role', 'full_name', 'phone_number', 'is_active')


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    full_name = serializers.CharField(required=False, allow_blank=True, default='')
    phone_number = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = User
        fields = ('email', 'password', 'full_name', 'phone_number')

    def create(self, validated_data):
        # Inscription publique = client uniquement
        return User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            role=ROLE_CLIENT,
            full_name=validated_data.get('full_name', ''),
            phone_number=validated_data.get('phone_number', None),
        )


class AdminCreateUserSerializer(serializers.Serializer):
    """Création d'utilisateur par admin (clients) ou superuser (clients + admins)."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=6)
    full_name = serializers.CharField(required=False, allow_blank=True, default='')
    phone_number = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    role = serializers.ChoiceField(
        choices=[ROLE_CLIENT, ROLE_ADMIN],
        default=ROLE_CLIENT,
    )

    def validate_email(self, value):
        email = value.strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError('Un compte existe déjà avec cet email.')
        return email

    def validate_role(self, value):
        role = normalize_role(value)
        request = self.context.get('request')
        actor = getattr(request, 'user', None)
        if role == ROLE_ADMIN and not is_platform_superuser(actor):
            raise serializers.ValidationError(
                'Seul un superuser peut créer un administrateur.'
            )
        if role == ROLE_SUPERUSER:
            raise serializers.ValidationError(
                'La création de superuser se fait via Django admin / createsuperuser.'
            )
        if role not in {ROLE_CLIENT, ROLE_ADMIN}:
            raise serializers.ValidationError('Rôle non autorisé.')
        return role

    def create(self, validated_data):
        phone = validated_data.get('phone_number') or None
        if phone is not None and str(phone).strip() == '':
            phone = None
        return User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            role=validated_data.get('role', ROLE_CLIENT),
            full_name=validated_data.get('full_name', ''),
            phone_number=phone,
        )


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Login par email, insensible à la casse."""

    def validate(self, attrs):
        from rest_framework_simplejwt.exceptions import AuthenticationFailed
        from django.utils.translation import gettext_lazy as _

        email_field = self.username_field  # 'email'
        raw_email = attrs.get(email_field, '')
        password = attrs.get('password', '')
        email = _normalize_email(str(raw_email))
        attrs[email_field] = email

        print(
            f'[auth/login.validate] raw_email={raw_email!r} '
            f'normalized={email!r} password_len={len(password)}'
        )

        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if user is None:
            print('[auth/login.validate] no active user for this email')
            raise AuthenticationFailed(
                _('Aucun compte actif n\'a été trouvé avec les identifiants fournis'),
                'no_active_account',
            )

        if not user.check_password(password):
            print('[auth/login.validate] password mismatch')
            raise AuthenticationFailed(
                _('Aucun compte actif n\'a été trouvé avec les identifiants fournis'),
                'no_active_account',
            )

        self.user = user
        refresh = self.get_token(user)
        data = {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'email': user.email,
            'role': normalize_role(user.role),
            'full_name': user.full_name,
            'phone_number': user.phone_number,
        }
        print(f'[auth/login.validate] OK user_id={user.pk} role={data["role"]}')
        return data


def _normalize_email(value: str) -> str:
    return value.strip().lower()


def _active_user_exists(email: str) -> bool:
    return User.objects.filter(email__iexact=email, is_active=True).exists()


class PasswordResetVerifySerializer(serializers.Serializer):
    """Vérifie qu'un compte actif existe pour cet email (sans envoi d'email)."""
    email = serializers.EmailField()

    def validate_email(self, value):
        email = _normalize_email(value)
        if not _active_user_exists(email):
            raise serializers.ValidationError(
                "Aucun compte actif n'est associé à cet email."
            )
        return email


class PasswordResetSerializer(serializers.Serializer):
    """Réinitialisation directe du mot de passe (temporaire, sans lien email)."""
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=6)
    confirm_password = serializers.CharField(write_only=True, min_length=6)

    def validate_email(self, value):
        email = _normalize_email(value)
        if not _active_user_exists(email):
            raise serializers.ValidationError(
                "Aucun compte actif n'est associé à cet email."
            )
        return email

    def validate(self, attrs):
        if attrs['password'] != attrs['confirm_password']:
            raise serializers.ValidationError({
                'confirm_password': 'Les mots de passe ne correspondent pas.',
            })
        return attrs

    def save(self, **kwargs):
        email = self.validated_data['email']
        user = User.objects.get(email__iexact=email, is_active=True)
        user.set_password(self.validated_data['password'])
        user.save()
        return user
