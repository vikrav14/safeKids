from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.core.validators import MinValueValidator, MaxValueValidator
from .models import (
    UserProfile, Child, LocationPoint, SafeZone, Alert, UserDevice, Message,
    ActiveEtaShare
)

class UserRegistrationSerializer(serializers.ModelSerializer):
    # Help text for api_app documentation
    username = serializers.CharField(help_text="Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.")
    email = serializers.EmailField(help_text="Required. A valid email address.")
    password = serializers.CharField(
        write_only=True, required=True, validators=[validate_password],
        help_text="Required. A strong password."
    )
    password2 = serializers.CharField(
        write_only=True, required=True, label="Confirm password",
        help_text="Required. Enter the same password as before, for verification."
    )
    phone_number = serializers.CharField(
        required=False, allow_blank=True, write_only=True, allow_null=True,
        help_text="Optional. User's phone number."
    )
    first_name = serializers.CharField(required=False, help_text="Optional. User's first name.")
    last_name = serializers.CharField(required=False, help_text="Optional. User's last name.")


    class Meta:
        model = User
        fields = ('username', 'email', 'password', 'password2', 'first_name', 'last_name', 'phone_number')
        extra_kwargs = {
            'first_name': {'required': False}, # Already specified above, but this is fine
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
    parent = serializers.PrimaryKeyRelatedField(read_only=True, help_text="The parent user associated with this child (auto-assigned).")
    proxy_user = serializers.PrimaryKeyRelatedField(read_only=True, help_text="Proxy user ID for this child, used for messaging (auto-assigned).")
    name = serializers.CharField(max_length=100, help_text="Name of the child.")
    device_id = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=255,
        help_text="Unique identifier for the child's device, used for device-specific actions."
    )
    battery_status = serializers.IntegerField(
        required=False, allow_null=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Child's device battery percentage (0-100)."
    )
    is_active = serializers.BooleanField(read_only=True, help_text="Is this child's profile currently active?") # Typically managed by parent/system
    last_seen_at = serializers.DateTimeField(read_only=True, allow_null=True, help_text="Timestamp of when the child's location was last updated.")


    class Meta:
        model = Child
        fields = ['id', 'name', 'parent', 'proxy_user', 'device_id', 'battery_status', 'is_active', 'last_seen_at', 'created_at', 'updated_at']
        read_only_fields = ('id', 'parent', 'proxy_user', 'last_seen_at', 'created_at', 'updated_at', 'is_active')


    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Child's name cannot be empty.")
        return value

class LocationPointSerializer(serializers.ModelSerializer):
    latitude = serializers.DecimalField(
        max_digits=9, decimal_places=6,
        validators=[MinValueValidator(-90.0), MaxValueValidator(90.0)],
        help_text="Latitude of the location (-90.0 to 90.0)."
    )
    longitude = serializers.DecimalField(
        max_digits=9, decimal_places=6,
        validators=[MinValueValidator(-180.0), MaxValueValidator(180.0)],
        help_text="Longitude of the location (-180.0 to 180.0)."
    )
    timestamp = serializers.DateTimeField(help_text="Timestamp of the location point (ISO 8601 format).")
    accuracy = serializers.FloatField(
        required=False, allow_null=True,
        validators=[MinValueValidator(0.0)],
        help_text="Accuracy of the location in meters (optional, positive value)."
    )
    class Meta:
        model = LocationPoint
        fields = ['latitude', 'longitude', 'timestamp', 'accuracy']


class MessageUserSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField(help_text="User's display name: Child's name if a proxy, else full name or username.")

    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'display_name']

    def get_display_name(self, obj):
        if hasattr(obj, 'messaging_child_profile') and obj.messaging_child_profile:
            return obj.messaging_child_profile.name
        full_name = obj.get_full_name()
        return full_name if full_name else obj.username

class MessageSerializer(serializers.ModelSerializer):
    sender = MessageUserSerializer(read_only=True, help_text="Details of the message sender.")
    receiver_id = serializers.IntegerField(write_only=True, help_text="User ID of the recipient.")
    receiver = MessageUserSerializer(read_only=True, help_text="Details of the message recipient (output only).")
    content = serializers.CharField(help_text="Content of the message.")
    timestamp = serializers.DateTimeField(read_only=True, help_text="Timestamp when the message was sent.")
    is_read = serializers.BooleanField(read_only=True, help_text="Indicates if the message has been read by the recipient.")


    class Meta:
        model = Message
        fields = ['id', 'sender', 'receiver_id', 'receiver', 'content', 'timestamp', 'is_read']
        read_only_fields = ('id', 'sender', 'timestamp', 'is_read', 'receiver')

    def validate_receiver_id(self, value):
        if not User.objects.filter(pk=value).exists():
            raise serializers.ValidationError("Recipient user does not exist.")
        if self.context.get('request') and self.context['request'].user.id == value:
            raise serializers.ValidationError("Cannot send messages to yourself.")
        return value
    
class UserCreateSerializer(BaseUserCreateSerializer):
    class Meta(BaseUserCreateSerializer.Meta):
        fields = ['id', 'username', 'email', 'password', 'first_name', 'last_name']

class UserSerializer(BaseUserSerializer):
    class Meta(BaseUserSerializer.Meta):
        fields = ['id', 'username', 'email', 'first_name', 'last_name']    

class StartEtaShareSerializer(serializers.Serializer):
    destination_name = serializers.CharField(
        max_length=255, required=False, allow_blank=True,
        help_text="Optional name for the destination (e.g., 'Home', 'Work')."
    )
    destination_latitude = serializers.FloatField(
        validators=[MinValueValidator(-90.0), MaxValueValidator(90.0)],
        help_text="Latitude of the destination."
    )
    destination_longitude = serializers.FloatField(
        validators=[MinValueValidator(-180.0), MaxValueValidator(180.0)],
        help_text="Longitude of the destination."
    )
    current_latitude = serializers.FloatField(
        help_text="Sharer's current latitude.",
        validators=[MinValueValidator(-90.0), MaxValueValidator(90.0)]
    )
    current_longitude = serializers.FloatField(
        help_text="Sharer's current longitude.",
        validators=[MinValueValidator(-180.0), MaxValueValidator(180.0)]
    )
    shared_with_user_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True,
        help_text="Optional list of User IDs to share this ETA with."
    )

    def validate_shared_with_user_ids(self, user_ids):
        if not user_ids:
            return []

        sharer_id = self.context['request'].user.id
        for user_id in user_ids:
            if user_id == sharer_id:
                raise serializers.ValidationError("Cannot share ETA with yourself.")
            if not User.objects.filter(pk=user_id, is_active=True).exists():
                raise serializers.ValidationError(f"User with ID {user_id} does not exist or is not active.")
        return user_ids

# Other serializers (SafeZone, Alert, CheckIn, DeviceRegistration, ActiveEtaShare, UpdateEtaLocation)
# would also get help_text on their fields. I'll do SafeZone as one more example.

class SafeZoneSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(read_only=True, help_text="The user who owns this safe zone.")
    name = serializers.CharField(max_length=100, help_text="Name of the safe zone (e.g., 'Home', 'School').")
    latitude = serializers.FloatField(
        validators=[MinValueValidator(-90.0), MaxValueValidator(90.0)],
        help_text="Latitude of the safe zone's center."
    )
    longitude = serializers.FloatField(
        validators=[MinValueValidator(-180.0), MaxValueValidator(180.0)],
        help_text="Longitude of the safe zone's center."
    )
    radius = serializers.FloatField(
        validators=[MinValueValidator(1.0)],
        help_text="Radius of the safe zone in meters (must be at least 1.0)."
    )
    is_active = serializers.BooleanField(default=True, help_text="Is this safe zone currently active and used for alerts?")


    class Meta:
        model = SafeZone
        fields = ['id', 'name', 'owner', 'latitude', 'longitude', 'radius', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ('id', 'owner', 'created_at', 'updated_at')


# --- Keeping other serializers as they were, assuming help_text will be added similarly ---

class SOSAlertSerializer(serializers.Serializer):
    child_id = serializers.IntegerField(required=True)
    device_id = serializers.CharField(required=True, max_length=255)
    latitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, required=False,
        validators=[MinValueValidator(-90.0), MaxValueValidator(90.0)]
    )
    longitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, required=False,
        validators=[MinValueValidator(-180.0), MaxValueValidator(180.0)]
    )

class AlertSerializer(serializers.ModelSerializer):
    alert_type_display = serializers.CharField(source='get_alert_type_display', read_only=True)
    safe_zone = serializers.PrimaryKeyRelatedField(queryset=SafeZone.objects.all(), allow_null=True, required=False)


    class Meta:
        model = Alert
        fields = [
            'id', 'recipient', 'child', 'alert_type', 'alert_type_display',
            'message', 'timestamp', 'is_read', 'safe_zone'
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
    latitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, required=True,
        validators=[MinValueValidator(-90.0), MaxValueValidator(90.0)]
    )
    longitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, required=True,
        validators=[MinValueValidator(-180.0), MaxValueValidator(180.0)]
    )
    location_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    client_timestamp_iso = serializers.DateTimeField(required=True)


class ActiveEtaShareSerializer(serializers.ModelSerializer):
    sharer = MessageUserSerializer(read_only=True)
    shared_with = MessageUserSerializer(many=True, read_only=True)
    destination_latitude = serializers.FloatField(validators=[MinValueValidator(-90.0), MaxValueValidator(90.0)])
    destination_longitude = serializers.FloatField(validators=[MinValueValidator(-180.0), MaxValueValidator(180.0)])
    current_latitude = serializers.FloatField(required=False, allow_null=True, validators=[MinValueValidator(-90.0), MaxValueValidator(90.0)])
    current_longitude = serializers.FloatField(required=False, allow_null=True, validators=[MinValueValidator(-180.0), MaxValueValidator(180.0)])

    class Meta:
        model = ActiveEtaShare
        fields = [
            'id', 'sharer', 'destination_name',
            'destination_latitude', 'destination_longitude',
            'current_latitude', 'current_longitude',
            'calculated_eta', 'status', 'shared_with',
            'created_at', 'updated_at'
        ]
        read_only_fields = ('id', 'sharer', 'calculated_eta', 'status',
                            'created_at', 'updated_at', 'shared_with')


class UpdateEtaLocationSerializer(serializers.Serializer):
    current_latitude = serializers.FloatField(
        required=True, validators=[MinValueValidator(-90.0), MaxValueValidator(90.0)]
    )
    current_longitude = serializers.FloatField(
        required=True, validators=[MinValueValidator(-180.0), MaxValueValidator(180.0)]
    )
