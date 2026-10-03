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
from .admin_permissions import (
    normalize_admin_permissions,
)

User = get_user_model()

# Valeurs par défaut (si BusinessSettings absent / non migré)
WAREHOUSE_PHONE = '18364649039'
WAREHOUSE_STREET = (
    '浙江省台州市椒江区 浙江省台州市椒江区 '
    '市府大道1139号台州学院椒江校区台州学院椒江校区国际会议厅bujito'
)


def _business_settings():
    try:
        from pricing.models import BusinessSettings

        return BusinessSettings.load()
    except Exception:
        return None


def _warehouse_parts():
    """Téléphone + rue globaux (modifiables admin via BusinessSettings)."""
    settings = _business_settings()
    if settings is None:
        return WAREHOUSE_PHONE, WAREHOUSE_STREET
    phone = (settings.china_warehouse_phone or '').strip() or WAREHOUSE_PHONE
    street = (settings.china_warehouse_street or '').strip() or WAREHOUSE_STREET
    return phone, street


def _client_paren(full_name: str, phone_number, city: str) -> str:
    name = (full_name or '').strip() or 'Client'
    phone = (phone_number or '').strip()
    ville = (city or '').strip()
    return ' '.join(p for p in (name, phone, ville) if p)


def build_china_warehouse_address(full_name: str, phone_number, city: str) -> str:
    """Adresse à coller sur les colis Chine : BU.Nom + entrepôt + (nom tél ville)."""
    name = (full_name or '').strip() or 'Client'
    paren = _client_paren(full_name, phone_number, city)
    warehouse_phone, warehouse_street = _warehouse_parts()
    return f'BU.{name} {warehouse_phone} {warehouse_street} ( {paren} )'


def build_transport_address(base: str, full_name: str, phone_number, city: str) -> str:
    """Adresse aérien / maritime + mention client pour copie."""
    text = (base or '').strip()
    if not text:
        return ''
    paren = _client_paren(full_name, phone_number, city)
    if not paren:
        return text
    return f'{text} ( {paren} )'


def build_china_air_address(full_name: str, phone_number, city: str) -> str:
    settings = _business_settings()
    base = (getattr(settings, 'china_air_address', '') or '') if settings else ''
    return build_transport_address(base, full_name, phone_number, city)


def build_china_sea_address(full_name: str, phone_number, city: str) -> str:
    settings = _business_settings()
    base = (getattr(settings, 'china_sea_address', '') or '') if settings else ''
    return build_transport_address(base, full_name, phone_number, city)


class UserSerializer(serializers.ModelSerializer):
    china_warehouse_address = serializers.SerializerMethodField()
    china_air_address = serializers.SerializerMethodField()
    china_sea_address = serializers.SerializerMethodField()
    profile_photo_url = serializers.SerializerMethodField()
    orders_count = serializers.IntegerField(read_only=True, required=False, default=0)
    parcels_count = serializers.IntegerField(read_only=True, required=False, default=0)
    parcels_received_count = serializers.IntegerField(
        read_only=True, required=False, default=0
    )
    parcels_sent_count = serializers.IntegerField(
        read_only=True, required=False, default=0
    )
    admin_permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            'id', 'email', 'role', 'full_name', 'phone_number', 'city',
            'is_active', 'stars', 'china_warehouse_address',
            'china_air_address', 'china_sea_address',
            'profile_photo_url',
            'orders_count', 'parcels_count',
            'parcels_received_count', 'parcels_sent_count',
            'admin_permissions',
        )
        read_only_fields = (
            'id', 'email', 'role', 'full_name', 'phone_number', 'city',
            'is_active', 'china_warehouse_address',
            'china_air_address', 'china_sea_address',
            'profile_photo_url',
            'orders_count', 'parcels_count',
            'parcels_received_count', 'parcels_sent_count',
            'admin_permissions',
        )

    def get_china_warehouse_address(self, obj):
        return build_china_warehouse_address(
            obj.full_name,
            obj.phone_number,
            getattr(obj, 'city', '') or '',
        )

    def get_china_air_address(self, obj):
        return build_china_air_address(
            obj.full_name,
            obj.phone_number,
            getattr(obj, 'city', '') or '',
        )

    def get_china_sea_address(self, obj):
        return build_china_sea_address(
            obj.full_name,
            obj.phone_number,
            getattr(obj, 'city', '') or '',
        )

    def get_profile_photo_url(self, obj):
        from parcels.media_urls import absolute_media_url

        return absolute_media_url(
            getattr(obj, 'profile_photo', None),
            self.context.get('request'),
            label='profile_photo',
        )

    def get_admin_permissions(self, obj):
        # Liste stockée normalisée (vide = accès total côté helpers Flutter/backend).
        return normalize_admin_permissions(
            getattr(obj, 'admin_permissions', None)
        )

    def to_representation(self, instance):
        from parcels.models import Parcel
        from parcels.stats import PARCEL_RECEIVED_STATUSES, PARCEL_SENT_STATUSES

        data = super().to_representation(instance)
        if not hasattr(instance, 'orders_count'):
            data['orders_count'] = instance.orders.count()
        if not hasattr(instance, 'parcels_count'):
            data['parcels_count'] = Parcel.objects.filter(
                order__user_id=instance.pk
            ).count()
        if not hasattr(instance, 'parcels_received_count'):
            data['parcels_received_count'] = Parcel.objects.filter(
                order__user_id=instance.pk,
                status__in=PARCEL_RECEIVED_STATUSES,
            ).count()
        if not hasattr(instance, 'parcels_sent_count'):
            data['parcels_sent_count'] = Parcel.objects.filter(
                order__user_id=instance.pk,
                status__in=PARCEL_SENT_STATUSES,
            ).count()
        return data


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


class AdminAgentUpdateSerializer(serializers.Serializer):
    """Super Admin : permissions / activation d'un agent admin."""

    admin_permissions = serializers.ListField(
        child=serializers.CharField(),
        required=False,
    )
    is_active = serializers.BooleanField(required=False)

    def validate_admin_permissions(self, value):
        return normalize_admin_permissions(value)

    def validate(self, attrs):
        instance = self.instance
        if instance is None:
            return attrs
        role = normalize_role(instance.role)
        if role not in (ROLE_ADMIN,):
            raise serializers.ValidationError(
                "Les permissions agents ne s'appliquent qu'aux administrateurs."
            )
        if is_platform_superuser(instance):
            raise serializers.ValidationError(
                "Impossible de modifier les permissions d'un Super Admin."
            )
        if not attrs:
            raise serializers.ValidationError("Aucune modification fournie.")
        return attrs

    def update(self, instance, validated_data):
        if 'admin_permissions' in validated_data:
            instance.admin_permissions = validated_data['admin_permissions']
        if 'is_active' in validated_data:
            instance.is_active = validated_data['is_active']
        instance.save()
        return instance


class ProfileUpdateSerializer(serializers.ModelSerializer):
    """Client / admin : mise à jour de son propre profil (+ photo)."""

    class Meta:
        model = User
        fields = ('full_name', 'phone_number', 'city', 'profile_photo')
        extra_kwargs = {
            'full_name': {'required': False, 'allow_blank': True},
            'phone_number': {'required': False, 'allow_blank': True, 'allow_null': True},
            'city': {'required': False, 'allow_blank': True},
            'profile_photo': {'required': False, 'allow_null': True},
        }

    def validate_phone_number(self, value):
        phone = (value or '').strip()
        if not phone:
            return None
        qs = User.objects.filter(phone_number__iexact=phone)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "Ce numéro de téléphone est déjà utilisé."
            )
        return phone


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    full_name = serializers.CharField(required=False, allow_blank=True, default='')
    phone_number = serializers.CharField(required=True, allow_blank=False)
    city = serializers.CharField(required=True, allow_blank=False, max_length=100)

    class Meta:
        model = User
        fields = ('email', 'password', 'full_name', 'phone_number', 'city')

    def validate_email(self, value):
        email = (value or '').strip().lower()
        if not email:
            raise serializers.ValidationError("L'email est obligatoire.")
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError('Un compte existe déjà avec cet email.')
        return email

    def validate_phone_number(self, value):
        phone = (value or '').strip()
        if not phone:
            raise serializers.ValidationError('Le téléphone est obligatoire.')
        digits = ''.join(ch for ch in phone if ch.isdigit())
        if len(digits) < 8:
            raise serializers.ValidationError('Numéro de téléphone invalide.')
        # Unicité souple (même numéro avec/sans espaces ou préfixe).
        qs = User.objects.exclude(phone_number__isnull=True).exclude(phone_number='')
        for existing in qs.only('phone_number'):
            existing_digits = ''.join(
                ch for ch in (existing.phone_number or '') if ch.isdigit()
            )
            if not existing_digits:
                continue
            if existing_digits == digits:
                raise serializers.ValidationError(
                    'Un compte existe déjà avec ce numéro de téléphone.'
                )
            if (
                existing_digits.endswith(digits) or digits.endswith(existing_digits)
            ) and min(len(existing_digits), len(digits)) >= 8:
                raise serializers.ValidationError(
                    'Un compte existe déjà avec ce numéro de téléphone.'
                )
        return phone

    def validate_city(self, value):
        city = (value or '').strip()
        if not city:
            raise serializers.ValidationError('La ville est obligatoire.')
        return city

    def create(self, validated_data):
        phone = (validated_data.get('phone_number') or '').strip() or None
        return User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            role=ROLE_CLIENT,
            full_name=(validated_data.get('full_name') or '').strip(),
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

    def validate_phone_number(self, value):
        phone = (value or '').strip()
        if not phone:
            return ''
        digits = ''.join(ch for ch in phone if ch.isdigit())
        if len(digits) < 8:
            raise serializers.ValidationError('Numéro de téléphone invalide.')
        qs = User.objects.exclude(phone_number__isnull=True).exclude(phone_number='')
        for existing in qs.only('phone_number'):
            existing_digits = ''.join(
                ch for ch in (existing.phone_number or '') if ch.isdigit()
            )
            if not existing_digits:
                continue
            if existing_digits == digits or (
                (existing_digits.endswith(digits) or digits.endswith(existing_digits))
                and min(len(existing_digits), len(digits)) >= 8
            ):
                raise serializers.ValidationError(
                    'Un compte existe déjà avec ce numéro de téléphone.'
                )
        return phone

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
        }
        try:
            from parcels.media_urls import absolute_media_url

            data['profile_photo_url'] = absolute_media_url(
                getattr(user, 'profile_photo', None),
                self.context.get('request'),
                label='profile_photo',
            )
        except Exception:
            data['profile_photo_url'] = None
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
