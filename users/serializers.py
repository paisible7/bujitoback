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
    def validate(self, attrs):
        data = super().validate(attrs)
        data['email'] = self.user.email
        data['role'] = self.user.role
        data['full_name'] = self.user.full_name
        data['phone_number'] = self.user.phone_number # Ajout de phone_number à la réponse du token
        return data