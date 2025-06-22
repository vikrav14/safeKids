# mauzenfan/server/api/tests/test_serializers.py
from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework import serializers # For ValidationError
from unittest.mock import MagicMock # For mocking request context

from api.models import (
    Child, UserProfile, Message, SafeZone, Alert,
    LearnedRoutine, ActiveEtaShare, UserDevice, LocationPoint
)
from api.serializers import (
    UserRegistrationSerializer, MessageUserSerializer, MessageSerializer,
    ChildSerializer, LocationPointSerializer, SafeZoneSerializer, AlertSerializer,
    CheckInSerializer, DeviceRegistrationSerializer, ActiveEtaShareSerializer,
    StartEtaShareSerializer, UpdateEtaLocationSerializer
    # LearnedRoutineSerializer - Not yet created, so commented out or add if/when it is
)

class UserRegistrationSerializerTests(TestCase):
    def test_valid_registration(self):
        data = {
            "username": "newuser", "email": "newuser@example.com",
            "password": "StrongPassword123!", "password2": "StrongPassword123!",
            "phone_number": "1234567890", "first_name": "New", "last_name": "User"
        }
        serializer = UserRegistrationSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        user = serializer.save()
        self.assertIsInstance(user, User)
        self.assertEqual(user.username, "newuser")
        self.assertEqual(user.email, "newuser@example.com") # Emails are lowercased by serializer
        self.assertEqual(user.first_name, "New")
        self.assertTrue(user.check_password("StrongPassword123!"))
        self.assertTrue(UserProfile.objects.filter(user=user, phone_number="1234567890").exists())

    def test_registration_password_mismatch(self):
        data = {"username": "test", "email": "test@example.com", "password": "pw1", "password2": "pw2"}
        serializer = UserRegistrationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("password_confirmation", serializer.errors) # Key was changed in serializer

    def test_registration_existing_username(self):
        User.objects.create_user(username="existinguser", password="password")
        data = {"username": "existinguser", "email": "test@example.com", "password": "pw1", "password2": "pw1"}
        serializer = UserRegistrationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("username", serializer.errors)

    def test_registration_existing_email(self):
        User.objects.create_user(username="testuser00", email="existing@example.com", password="password")
        data = {"username": "newuser", "email": "existing@example.com", "password": "pw1", "password2": "pw1"}
        serializer = UserRegistrationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("email", serializer.errors)

class MessageUserSerializerTests(TestCase):
    def setUp(self):
        self.parent_user = User.objects.create_user(username="parentforchild")

    def test_message_user_serialization_regular_user(self):
        user = User.objects.create_user(username="msguser", first_name="Test", last_name="User")
        serializer_user = MessageUserSerializer(user)
        self.assertEqual(serializer_user.data['username'], "msguser")
        self.assertEqual(serializer_user.data['display_name'], "Test User")

    def test_message_user_serialization_proxy_user(self):
        child = Child.objects.create(parent=self.parent_user, name="Child Name")
        # Signal creates proxy_user for child
        self.assertIsNotNone(child.proxy_user, "Proxy user should have been created by signal")

        proxy_user_instance = child.proxy_user
        # Manually set first/last name on proxy if needed for testing get_full_name part,
        # but signal doesn't do it. Default __str__ of User is username.
        # Our serializer's get_display_name for proxy users should return child's name.
        proxy_user_instance.first_name = "Proxy" # Simulate if proxy had a name
        proxy_user_instance.last_name = "User"
        proxy_user_instance.save()

        serializer_proxy = MessageUserSerializer(proxy_user_instance)
        self.assertEqual(serializer_proxy.data['username'], f"child_{child.id}_proxy")
        self.assertEqual(serializer_proxy.data['display_name'], "Child Name") # Should be child's actual name

    def test_message_user_serialization_no_fullname(self):
        user_no_fullname = User.objects.create_user(username="justusername")
        serializer = MessageUserSerializer(user_no_fullname)
        self.assertEqual(serializer.data['display_name'], "justusername")


class MessageSerializerTests(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username="sender_user", password="password")
        self.user2 = User.objects.create_user(username="receiver_user", password="password")
        self.mock_request = MagicMock()
        self.mock_request.user = self.user1

    def test_valid_message_creation(self):
        data = {"receiver_id": self.user2.id, "content": "Hello there!"}
        serializer = MessageSerializer(data=data, context={'request': self.mock_request})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        message = serializer.save(sender=self.user1)
        self.assertEqual(message.content, "Hello there!")
        self.assertEqual(message.sender, self.user1)
        self.assertEqual(message.receiver, self.user2)

    def test_message_to_self_invalid(self):
        data = {"receiver_id": self.user1.id, "content": "Talking to myself"}
        serializer = MessageSerializer(data=data, context={'request': self.mock_request})
        self.assertFalse(serializer.is_valid())
        self.assertIn("receiver_id", serializer.errors)

    def test_message_to_nonexistent_receiver_invalid(self):
        data = {"receiver_id": 9999, "content": "To the void"}
        serializer = MessageSerializer(data=data, context={'request': self.mock_request})
        self.assertFalse(serializer.is_valid())
        self.assertIn("receiver_id", serializer.errors)

    def test_message_serialization_output(self):
        message = Message.objects.create(sender=self.user1, receiver=self.user2, content="Hi")
        serializer = MessageSerializer(message)
        self.assertEqual(serializer.data['content'], "Hi")
        self.assertEqual(serializer.data['sender']['username'], self.user1.username)
        self.assertEqual(serializer.data['receiver']['username'], self.user2.username)


class ChildSerializerTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="parent1")

    def test_child_serializer_valid(self):
        data = {"name": "Test Child", "device_id": "device123", "battery_status": 80}
        # In a real scenario, parent is set by the view, not part of request data for creation
        serializer = ChildSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_child_serializer_empty_name_invalid(self):
        data = {"name": " ", "device_id": "device123"}
        serializer = ChildSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("name", serializer.errors)

class StartEtaShareSerializerTests(TestCase):
    def setUp(self):
        self.sharer = User.objects.create_user(username="sharer")
        self.user_to_share_with = User.objects.create_user(username="viewer")
        self.mock_request = MagicMock()
        self.mock_request.user = self.sharer

    def test_start_eta_share_valid(self):
        data = {
            "destination_name": "Work", "destination_latitude": 1.0, "destination_longitude": 1.0,
            "current_latitude": 0.0, "current_longitude": 0.0,
            "shared_with_user_ids": [self.user_to_share_with.id]
        }
        serializer = StartEtaShareSerializer(data=data, context={'request': self.mock_request})
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_start_eta_share_with_self_invalid(self):
        data = {
            "destination_latitude": 1.0, "destination_longitude": 1.0,
            "current_latitude": 0.0, "current_longitude": 0.0,
            "shared_with_user_ids": [self.sharer.id]
        }
        serializer = StartEtaShareSerializer(data=data, context={'request': self.mock_request})
        self.assertFalse(serializer.is_valid())
        self.assertIn("shared_with_user_ids", serializer.errors)

    def test_start_eta_share_with_nonexistent_user_invalid(self):
        data = {
            "destination_latitude": 1.0, "destination_longitude": 1.0,
            "current_latitude": 0.0, "current_longitude": 0.0,
            "shared_with_user_ids": [9999]
        }
        serializer = StartEtaShareSerializer(data=data, context={'request': self.mock_request})
        self.assertFalse(serializer.is_valid())
        self.assertIn("shared_with_user_ids", serializer.errors)

class UpdateEtaLocationSerializerTests(TestCase):
    def test_update_eta_location_valid(self):
        data = {"current_latitude": 1.23, "current_longitude": 4.56}
        serializer = UpdateEtaLocationSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_update_eta_location_missing_fields(self):
        data = {"current_latitude": 1.23} # Missing longitude
        serializer = UpdateEtaLocationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("current_longitude", serializer.errors)

class CheckInSerializerTests(TestCase):
    def test_checkin_serializer_valid(self):
        data = {
            "child_id": 1, "device_id": "deviceXYZ", "check_in_type": "ARRIVED_HOME",
            "latitude": 10.0, "longitude": 20.0, "client_timestamp_iso": "2023-01-01T12:00:00Z",
            "custom_message": "I'm home!", "location_name": "Home Sweet Home"
        }
        serializer = CheckInSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_checkin_serializer_missing_required_fields(self):
        data = {"child_id": 1, "device_id": "deviceXYZ"} # Missing many fields
        serializer = CheckInSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("check_in_type", serializer.errors)
        self.assertIn("latitude", serializer.errors)
        self.assertIn("longitude", serializer.errors)
        self.assertIn("client_timestamp_iso", serializer.errors)

class DeviceRegistrationSerializerTests(TestCase):
    def test_device_registration_valid(self):
        data = {"device_token": "tok123", "device_type": "android"}
        serializer = DeviceRegistrationSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_device_registration_empty_token_invalid(self):
        data = {"device_token": "", "device_type": "android"}
        serializer = DeviceRegistrationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("device_token", serializer.errors)

# Note: AlertSerializer and ActiveEtaShareSerializer are primarily for output.
# Their tests would involve creating a model instance and checking its serialized representation.
# LocationPointSerializer is also simple, mainly for input validation within views.
# SafeZoneSerializer has basic field validation.
# These can be added for completeness but UserRegistration, Message, StartEtaShare are more complex.
