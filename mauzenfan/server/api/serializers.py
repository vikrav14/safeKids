from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from .models import UserProfile, Child, LocationPoint, SafeZone, Alert, UserDevice, Message # Added Message

class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True, label="Confirm password")
    phone_number = serializers.CharField(required=False, allow_blank=True, write_only=True, allow_null=True)

    class Meta:
        model = User
        fields = ('username', 'email', 'password', 'password2', 'first_name', 'last_name', 'phone_number')
        extra_kwargs = {
            'first_name': {'required': False},
            'last_name': {'required': False},
            'email': {'required': True}
        }

    def validate_email(self, value):
        if User.objects.filter(email=value.lower()).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value.lower()

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password_confirmation": "Password fields didn't match."})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        phone_number_data = validated_data.pop('phone_number', None)

        user_kwargs = {
            'username': validated_data['username'],
            'email': validated_data['email'].lower(),
            'password': validated_data['password']
        }
        if 'first_name' in validated_data:
            user_kwargs['first_name'] = validated_data['first_name']
        if 'last_name' in validated_data:
            user_kwargs['last_name'] = validated_data['last_name']

        user = User.objects.create_user(**user_kwargs)

        profile_kwargs = {'user': user}
        if phone_number_data is not None:
            profile_kwargs['phone_number'] = phone_number_data
        UserProfile.objects.create(**profile_kwargs)

        return user

class ChildSerializer(serializers.ModelSerializer):
    parent = serializers.PrimaryKeyRelatedField(read_only=True)
    device_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    last_seen_at = serializers.DateTimeField(read_only=True, allow_null=True)

    class Meta:
        model = Child
        fields = ['id', 'name', 'parent', 'device_id', 'battery_status', 'last_seen_at', 'created_at', 'updated_at']
        read_only_fields = ('created_at', 'updated_at', 'parent', 'last_seen_at')

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Child's name cannot be empty.")
        return value

class LocationPointSerializer(serializers.ModelSerializer):
    class Meta:
        model = LocationPoint
        fields = ['latitude', 'longitude', 'timestamp', 'accuracy']
        extra_kwargs = {
            'accuracy': {'required': False, 'allow_null': True}
        }

class SafeZoneSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = SafeZone
        fields = ['id', 'name', 'owner', 'latitude', 'longitude', 'radius', 'created_at', 'updated_at']
        read_only_fields = ('created_at', 'updated_at', 'owner')

class SOSAlertSerializer(serializers.Serializer):
    child_id = serializers.IntegerField(required=True)
    device_id = serializers.CharField(required=True, max_length=255)
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)

class AlertSerializer(serializers.ModelSerializer):
    alert_type_display = serializers.CharField(source='get_alert_type_display', read_only=True)

    class Meta:
        model = Alert
        fields = [
            'id',
            'recipient',
            'child',
            'alert_type',
            'alert_type_display',
            'message',
            'timestamp',
            'is_read'
        ]
        read_only_fields = fields

class DeviceRegistrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserDevice
        fields = ['device_token', 'device_type']

    def validate_device_token(self, value):
        if not value:
            raise serializers.ValidationError("Device token cannot be empty.")
        return value

class CheckInSerializer(serializers.Serializer):
    child_id = serializers.IntegerField(required=True)
    device_id = serializers.CharField(required=True, max_length=255)
    check_in_type = serializers.CharField(required=True, max_length=50)
    custom_message = serializers.CharField(required=False, allow_blank=True, max_length=150)
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=True)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=True)
    location_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    client_timestamp_iso = serializers.DateTimeField(required=True)

class MessageUserSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'display_name']

    def get_display_name(self, obj):
        # Check if this user is a proxy for a child
        # The related_name from Child.proxy_user to User is 'messaging_child_profile'
        if hasattr(obj, 'messaging_child_profile') and obj.messaging_child_profile:
            return obj.messaging_child_profile.name # Return Child's name
        full_name = obj.get_full_name()
        return full_name if full_name else obj.username # Default to User's full name or username

class MessageSerializer(serializers.ModelSerializer):
    sender = MessageUserSerializer(read_only=True)
    receiver_id = serializers.IntegerField(write_only=True, help_text="ID of the recipient user.")
    receiver = MessageUserSerializer(read_only=True) # For displaying receiver details on retrieval

    class Meta:
        model = Message
        fields = ['id', 'sender', 'receiver_id', 'receiver', 'content', 'timestamp', 'is_read']
        read_only_fields = ('id', 'sender', 'timestamp', 'is_read', 'receiver')

    def validate_receiver_id(self, value):
        if not User.objects.filter(pk=value).exists():
            raise serializers.ValidationError("Recipient user does not exist.")
        # Accessing self.context['request'] requires request to be passed in context
        if self.context.get('request') and self.context['request'].user.id == value:
            raise serializers.ValidationError("Cannot send messages to yourself.")
        return value
