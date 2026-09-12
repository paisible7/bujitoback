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

# Valeurs par défaut (si BusinessSettings absent / non migré)
WAREHOUSE_PHONE = '18575740344'
WAREHOUSE_STREET = '佛山市南海区狮山镇塘头村一队新一巷3号bujito'


def _warehouse_parts():
    """Téléphone + rue globaux (modifiables admin via BusinessSettings)."""
    try:
        from pricing.models import BusinessSettings

        settings = BusinessSettings.load()
        phone = (settings.china_warehouse_phone or '').strip() or WAREHOUSE_PHONE
        street = (settings.china_warehouse_street or '').strip() or WAREHOUSE_STREET
        return phone, street
    except Exception:
        return WAREHOUSE_PHONE, WAREHOUSE_STREET


def build_china_warehouse_address(full_name: str, phone_number, city: str) -> str:
    """Adresse à coller sur les colis Chine : BU.Nom + entrepôt + (nom tél ville)."""
    name = (full_name or '').strip() or 'Client'
    phone = (phone_number or '').strip()
    ville = (city or '').strip()
    paren_parts = [p for p in (name, phone, ville) if p]
    paren = ' '.join(paren_parts)
    warehouse_phone, warehouse_street = _warehouse_parts()
    return f'BU.{name} {warehouse_phone} {warehouse_street} ( {paren} )'


class UserSerializer(serializers.ModelSerializer):
    china_warehouse_address = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            'id', 'email', 'role', 'full_name', 'phone_number', 'city',
            'is_active', 'stars', 'china_warehouse_address',
        )
        read_only_fields = (
            'id', 'email', 'role', 'full_name', 'phone_number', 'city',
            'is_active', 'china_warehouse_address',
        )

    def get_china_warehouse_address(self, obj):
        return build_china_warehouse_address(
            obj.full_name,
            obj.phone_number,
            getattr(obj, 'city', '') or '',
        )


class AdminUserUpdateSerializer(serializers.ModelSerializer):
    """Admin : attribution d'étoiles (1–5) aux clients."""

    stars = serializers.IntegerField(min_value=0, max_value=5)

    class Meta:
        model = User
        fields = ('stars',)

    def validate(self, attrs):
        instance = self.instance
        if instance is not None:
            role = normalize_role(instance.role)
            if role not in (ROLE_CLIENT, 'user'):
                raise serializers.ValidationError(
                    "Les étoiles ne s'appliquent qu'aux clients."
                )
        return attrs


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    full_name = serializers.CharField(required=False, allow_blank=True, default='')
    phone_number = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    city = serializers.CharField(required=True, allow_blank=False, max_length=100)

    class Meta:
        model = User
        fields = ('email', 'password', 'full_name', 'phone_number', 'city')

    def validate_city(self, value):
        city = (value or '').strip()
        if not city:
            raise serializers.ValidationError('La ville est obligatoire.')
        return city

    def create(self, validated_data):
        phone = validated_data.get('phone_number') or None
        if phone is not None and str(phone).strip() == '':
            phone = None
        return User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            role=ROLE_CLIENT,
            full_name=validated_data.get('full_name', ''),
            phone_number=phone,
            city=validated_data.get('city', ''),
        )


class AdminCreateUserSerializer(serializers.Serializer):
    """Création d'utilisateur par admin (clients) ou superuser (clients + admins)."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=6)
    full_name = serializers.CharField(required=False, allow_blank=True, default='')
    phone_number = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    city = serializers.CharField(required=False, allow_blank=True, default='')
    role = serializers.ChoiceField(
        choices=[ROLE_CLIENT, ROLE_ADMIN],
        default=ROLE_CLIENT,
    )

    def validate_email(self, value):
        email = value.strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError('Un compte existe déjà avec cet email.')
        return email

    def validate(self, attrs):
        role = normalize_role(attrs.get('role', ROLE_CLIENT))
        city = (attrs.get('city') or '').strip()
        attrs['city'] = city
        if role == ROLE_CLIENT and not city:
            raise serializers.ValidationError({
                'city': 'La ville est obligatoire pour un client.',
            })
        return attrs

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
            city=validated_data.get('city', ''),
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
            'city': getattr(user, 'city', '') or '',
            'stars': getattr(user, 'stars', 0) or 0,
            'china_warehouse_address': build_china_warehouse_address(
                user.full_name,
                user.phone_number,
                getattr(user, 'city', '') or '',
            ),
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
