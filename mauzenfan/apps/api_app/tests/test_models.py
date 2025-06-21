# mauzenfan/server/api_app./tests/test_models.py
from django.test import TestCase
from django.contrib.auth.models import User
from api_app..models import (
    Child, SafeZone, Alert, Message, LearnedRoutine, ActiveEtaShare, UserDevice, UserProfile
)
import logging

# Disable logging during tests for cleaner output, if desired
# logging.disable(logging.CRITICAL)

class ChildModelTests(TestCase):
    def setUp(self):
        self.parent_user = User.objects.create_user(username='testparent', password='password123')

    def test_child_str_representation(self):
        child = Child.objects.create(parent=self.parent_user, name='Test Child')
        self.assertEqual(str(child), 'Test Child')

    def test_proxy_user_creation_on_child_save(self):
        # Test the post_save signal
        initial_proxy_user_count = User.objects.filter(username__startswith='child_').count()

        child = Child.objects.create(parent=self.parent_user, name='Signal Child')
        self.assertIsNotNone(child.proxy_user, "Proxy user should be created and assigned.")
        self.assertEqual(child.proxy_user.username, f'child_{child.id}_proxy')
        self.assertFalse(child.proxy_user.is_active, "Proxy user should be inactive for login.")
        self.assertFalse(child.proxy_user.has_usable_password(), "Proxy user should have an unusable password.")

        # Ensure only one new proxy user was created
        self.assertEqual(User.objects.filter(username__startswith='child_').count(), initial_proxy_user_count + 1)
        self.assertEqual(User.objects.filter(username=f'child_{child.id}_proxy').count(), 1)

        # Test that saving an existing child with a proxy doesn't create another one
        # or change the existing one if not needed
        proxy_user_before_resave = child.proxy_user
        users_count_before_resave = User.objects.count()

        child.name = "Signal Child Updated"
        child.save() # Save again

        self.assertEqual(User.objects.count(), users_count_before_resave, "No new User objects should be created on re-save.")
        child.refresh_from_db() # Ensure we have the latest instance data
        self.assertEqual(child.proxy_user, proxy_user_before_resave, "Proxy user should not change on re-save.")


class UserProfileModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='profileuser', password='password123')

    def test_userprofile_str(self):
        profile = UserProfile.objects.create(user=self.user, phone_number="12345")
        self.assertEqual(str(profile), 'profileuser')

class SafeZoneModelTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='zoneowner', password='password123')

    def test_safezone_str(self):
        zone = SafeZone.objects.create(owner=self.owner, name='My Home Zone', latitude=1.0, longitude=1.0, radius=100)
        self.assertEqual(str(zone), 'My Home Zone')

class AlertModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='alertuser')
        self.child_user = User.objects.create_user(username='alertchilduser') # A user for the child if needed
        self.child = Child.objects.create(parent=self.user, name="Alert Child", proxy_user=self.child_user)

    def test_alert_str_and_display(self):
        alert = Alert.objects.create(recipient=self.user, child=self.child, alert_type='SOS', message='Help me')
        self.assertEqual(str(alert), f"SOS Panic for alertuser")
        self.assertEqual(alert.get_alert_type_display(), 'SOS Panic')

        alert_low_bat = Alert.objects.create(recipient=self.user, child=self.child, alert_type='LOW_BATTERY', message='Battery low')
        self.assertEqual(str(alert_low_bat), f"Low Battery for alertuser")
        self.assertEqual(alert_low_bat.get_alert_type_display(), 'Low Battery')

class MessageModelTests(TestCase):
    def setUp(self):
        self.sender = User.objects.create_user(username='msgsender', password='password123')
        self.receiver = User.objects.create_user(username='msgreceiver', password='password123')

    def test_message_str(self):
        msg = Message.objects.create(sender=self.sender, receiver=self.receiver, content="Hello there")
        # Exact timestamp might vary, so check start
        self.assertTrue(str(msg).startswith(f"From msgsender to msgreceiver at"))

class LearnedRoutineModelTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username='routineparent')
        self.child = Child.objects.create(parent=self.parent, name='Routine Child')

    def test_learned_routine_str(self):
        routine = LearnedRoutine.objects.create(child=self.child, name="School Run")
        self.assertEqual(str(routine), "School Run for Routine Child")
        routine_no_name = LearnedRoutine.objects.create(child=self.child)
        self.assertEqual(str(routine_no_name), "Routine for Routine Child")

class ActiveEtaShareModelTests(TestCase):
    def setUp(self):
        self.sharer = User.objects.create_user(username='etasharer')

    def test_active_eta_share_str(self):
        eta_share = ActiveEtaShare.objects.create(
            sharer=self.sharer,
            destination_name="Library",
            destination_latitude=10.0,
            destination_longitude=10.0
        )
        self.assertEqual(str(eta_share), "ETA Share by etasharer to Library")

        eta_share_no_name = ActiveEtaShare.objects.create(
            sharer=self.sharer,
            destination_latitude=11.0,
            destination_longitude=11.0
        )
        self.assertEqual(str(eta_share_no_name), "ETA Share by etasharer to Unnamed Destination")

class UserDeviceModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='devicetester')

    def test_user_device_str(self):
        device = UserDevice.objects.create(user=self.user, device_token="a_very_long_device_token_string_for_testing_ellipsis", device_type="android")
        self.assertEqual(str(device), "devicetester - android (a_very_long_device_t...)")

        device_short_token = UserDevice.objects.create(user=self.user, device_token="shorttoken", device_type="ios")
        self.assertEqual(str(device_short_token), "devicetester - ios (shorttoken)")

        device_no_type = UserDevice.objects.create(user=self.user, device_token="notypetoken")
        self.assertEqual(str(device_no_type), "devicetester - UnknownType (notypetoken)")
