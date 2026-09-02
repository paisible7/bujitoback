from rest_framework import serializers
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'email', 'role', 'full_name', 'phone_number') # Ajout de 'phone_number'

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    full_name = serializers.CharField(required=False, allow_blank=True, default='')
    phone_number = serializers.CharField(required=False, allow_blank=True, allow_null=True) # Ajout du champ phone_number

    class Meta:
        model = User
        fields = ('email', 'password', 'role', 'full_name', 'phone_number') # Ajout de 'phone_number'

    def create(self, validated_data):
        user = User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            role=validated_data.get('role', 'user'),
            full_name=validated_data.get('full_name', ''),
            phone_number=validated_data.get('phone_number', None) # Passage du phone_number au create_user
        )
        return user

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

        # Compat SimpleJWT : self.user utilisé ensuite par la classe parente / refresh
        self.user = user
        refresh = self.get_token(user)
        data = {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'email': user.email,
            'role': user.role,
            'full_name': user.full_name,
            'phone_number': user.phone_number,
        }
        print(f'[auth/login.validate] OK user_id={user.pk} role={user.role}')
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
        # Ne pas utiliser update_fields=['password'] : certains backends
        # d'auth nécessitent un save() complet pour persister correctement.
        user.save()
        return user