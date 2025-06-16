from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from .models import UserProfile

class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True, label="Confirm password")
    phone_number = serializers.CharField(required=False, allow_blank=True, write_only=True, allow_null=True) # For UserProfile

    class Meta:
        model = User
        fields = ('username', 'email', 'password', 'password2', 'first_name', 'last_name', 'phone_number')
        extra_kwargs = {
            'first_name': {'required': False},
            'last_name': {'required': False},
            'email': {'required': True}
        }

    def validate_email(self, value):
        if User.objects.filter(email=value.lower()).exists(): # Compare emails in lowercase
            raise serializers.ValidationError("An account with this email already exists.")
        return value.lower() # Store email in lowercase

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password_confirmation": "Password fields didn't match."}) # Changed key for clarity
        # No need to pop password2 here, it's not passed to create_user anyway if not a model field
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        phone_number_data = validated_data.pop('phone_number', None)

        # User fields for create_user. Password is handled by create_user.
        user_kwargs = {
            'username': validated_data['username'],
            'email': validated_data['email'].lower(), # Ensure email is lowercase
            'password': validated_data['password']
        }
        if 'first_name' in validated_data:
            user_kwargs['first_name'] = validated_data['first_name']
        if 'last_name' in validated_data:
            user_kwargs['last_name'] = validated_data['last_name']

        user = User.objects.create_user(**user_kwargs)

        # Create UserProfile
        # UserProfile is created automatically on User post_save signal if using that pattern,
        # or manually like this if not.
        # For this example, let's assume manual creation is intended.
        profile_kwargs = {'user': user}
        if phone_number_data is not None:
            profile_kwargs['phone_number'] = phone_number_data
        UserProfile.objects.create(**profile_kwargs)

        return user
