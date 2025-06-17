# mauzenfan/server/api/tests/test_views.py
from rest_framework.test import APITestCase
from django.contrib.auth.models import User
from api.models import Child, SafeZone, UserProfile, LocationPoint, Alert, ActiveEtaShare, Message, UserDevice # Added UserDevice
from django.urls import reverse
from rest_framework import status
from unittest.mock import patch, MagicMock
from django.utils import timezone
from datetime import timedelta
import json
import logging

# Optional: Disable logging for cleaner test output
# logging.disable(logging.CRITICAL)

class ChildViewSetTests(APITestCase):
    def setUp(self):
        self.parent1 = User.objects.create_user(username='parent1', password='password123', email='p1@example.com')
        self.parent2 = User.objects.create_user(username='parent2', password='password123', email='p2@example.com')
        self.child1_p1 = Child.objects.create(parent=self.parent1, name='Child One P1', device_id='dev1p1')
        self.child2_p1 = Child.objects.create(parent=self.parent1, name='Child Two P1', device_id='dev2p1')
        self.child1_p2 = Child.objects.create(parent=self.parent2, name='Child One P2', device_id='dev1p2')
        self.list_create_url = reverse('child-list')
        self.detail_url_p1_c1 = reverse('child-detail', kwargs={'pk': self.child1_p1.pk})

    def test_list_children_authenticated_parent(self):
        self.client.force_authenticate(user=self.parent1)
        response = self.client.get(self.list_create_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 2)
        child_names = [c['name'] for c in results]
        self.assertIn('Child One P1', child_names)
        self.assertNotIn('Child One P2', child_names)

    def test_list_children_unauthenticated(self):
        response = self.client.get(self.list_create_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_child_authenticated_parent(self):
        self.client.force_authenticate(user=self.parent1)
        data = {'name': 'New Child P1', 'device_id': 'newdevp1', 'battery_status': 90}
        response = self.client.post(self.list_create_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(Child.objects.filter(parent=self.parent1, name='New Child P1').count(), 1)
        new_child = Child.objects.get(parent=self.parent1, name='New Child P1')
        self.assertIsNotNone(new_child.proxy_user, "Proxy user should be created by signal.")

    def test_create_child_missing_name_fails(self):
        self.client.force_authenticate(user=self.parent1)
        data = {'device_id': 'baddata'}
        response = self.client.post(self.list_create_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('name', response.data)

    def test_retrieve_own_child_authenticated_parent(self):
        self.client.force_authenticate(user=self.parent1)
        response = self.client.get(self.detail_url_p1_c1)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], self.child1_p1.name)

    def test_retrieve_other_parent_child_fails(self):
        self.client.force_authenticate(user=self.parent1)
        other_child_url = reverse('child-detail', kwargs={'pk': self.child1_p2.pk})
        response = self.client.get(other_child_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_own_child(self):
        self.client.force_authenticate(user=self.parent1)
        data = {'name': 'Updated Child One P1', 'battery_status': 75}
        response = self.client.patch(self.detail_url_p1_c1, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.child1_p1.refresh_from_db()
        self.assertEqual(self.child1_p1.name, 'Updated Child One P1')
        self.assertEqual(self.child1_p1.battery_status, 75)

    def test_delete_own_child(self):
        self.client.force_authenticate(user=self.parent1)
        response = self.client.delete(self.detail_url_p1_c1)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Child.objects.filter(pk=self.child1_p1.pk).exists())


class SafeZoneViewSetTests(APITestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username='user1_sz', password='password123')
        self.user2 = User.objects.create_user(username='user2_sz', password='password123')
        self.zone1_u1 = SafeZone.objects.create(owner=self.user1, name='Home U1', latitude=1.0, longitude=1.0, radius=100)
        self.zone2_u1 = SafeZone.objects.create(owner=self.user1, name='School U1', latitude=2.0, longitude=2.0, radius=200)
        self.zone1_u2 = SafeZone.objects.create(owner=self.user2, name='Home U2', latitude=3.0, longitude=3.0, radius=150)
        self.list_create_url = reverse('safezone-list')
        self.detail_url_u1_z1 = reverse('safezone-detail', kwargs={'pk': self.zone1_u1.pk})

    def test_list_safezones_authenticated_user(self):
        self.client.force_authenticate(user=self.user1)
        response = self.client.get(self.list_create_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 2)
        zone_names = [z['name'] for z in results]
        self.assertIn('Home U1', zone_names)
        self.assertNotIn('Home U2', zone_names)

    def test_list_safezones_unauthenticated(self):
        response = self.client.get(self.list_create_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_safezone_authenticated_user(self):
        self.client.force_authenticate(user=self.user1)
        data = {'name': 'Work U1', 'latitude': 4.0, 'longitude': 4.0, 'radius': 250, 'is_active': True}
        response = self.client.post(self.list_create_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(SafeZone.objects.filter(owner=self.user1, name='Work U1').exists())

    def test_retrieve_own_safezone(self):
        self.client.force_authenticate(user=self.user1)
        response = self.client.get(self.detail_url_u1_z1)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], self.zone1_u1.name)

    def test_retrieve_other_user_safezone_fails(self):
        self.client.force_authenticate(user=self.user1)
        other_zone_url = reverse('safezone-detail', kwargs={'pk': self.zone1_u2.pk})
        response = self.client.get(other_zone_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_own_safezone(self):
        self.client.force_authenticate(user=self.user1)
        data = {'name': 'Updated Home U1', 'radius': 120}
        response = self.client.patch(self.detail_url_u1_z1, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.zone1_u1.refresh_from_db()
        self.assertEqual(self.zone1_u1.name, 'Updated Home U1')
        self.assertEqual(self.zone1_u1.radius, 120)

    def test_delete_own_safezone(self):
        self.client.force_authenticate(user=self.user1)
        response = self.client.delete(self.detail_url_u1_z1)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(SafeZone.objects.filter(pk=self.zone1_u1.pk).exists())


class LocationUpdateViewTests(APITestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username='testparent_loc', password='password')
        self.child = Child.objects.create(parent=self.parent, name='TrackedChild', device_id='device123_loc', is_active=True)
        self.url = reverse('location-update')

    @patch('api.views.get_channel_layer')
    @patch('api.views.send_fcm_to_user')
    def test_location_update_success(self, mock_send_fcm, mock_get_channel_layer):
        mock_channel_layer_instance = MagicMock()
        mock_get_channel_layer.return_value = mock_channel_layer_instance
        data = {
            "child_id": self.child.id, "device_id": "device123_loc",
            "latitude": 10.123456, "longitude": 20.654321,
            "battery_status": 85, "timestamp": timezone.now().isoformat()
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(LocationPoint.objects.filter(child=self.child).count(), 1)
        self.child.refresh_from_db()
        self.assertEqual(self.child.battery_status, 85)
        self.assertIsNotNone(self.child.last_seen_at)
        self.assertTrue(mock_channel_layer_instance.group_send.called)
        location_update_call_found = False
        for call_args in mock_channel_layer_instance.group_send.call_args_list:
            args, kwargs = call_args
            if kwargs.get('type') == 'location.update':
                location_update_call_found = True
                self.assertEqual(args[0], f'user_{self.parent.id}_notifications')
                break
        self.assertTrue(location_update_call_found, "location.update was not sent via channel_layer")

    def test_location_update_invalid_device_id(self):
        data = {"child_id": self.child.id, "device_id": "wrong_device", "latitude": 10.0, "longitude": 20.0, "timestamp": timezone.now().isoformat()}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_location_update_child_not_found(self):
        data = {"child_id": 999, "device_id": "any_device", "latitude": 10.0, "longitude": 20.0, "timestamp": timezone.now().isoformat()}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

class LocationUpdateViewAlertGenerationTests(APITestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username='alert_test_parent', password='password')
        self.child = Child.objects.create(parent=self.parent, name='AlertChild', device_id='dev_alert', is_active=True)
        self.home_zone = SafeZone.objects.create(
            owner=self.parent, name="Home",
            latitude=0.0, longitude=0.0, radius=100, is_active=True
        )
        self.update_url = reverse('location-update')

    @patch('api.views.send_fcm_to_user')
    @patch('api.views.get_channel_layer')
    def test_location_update_triggers_low_battery_alert(self, mock_get_channel_layer, mock_send_fcm):
        mock_channel_layer_instance = MagicMock()
        mock_get_channel_layer.return_value = mock_channel_layer_instance
        data = {
            "child_id": self.child.id, "device_id": "dev_alert",
            "latitude": 10.0, "longitude": 20.0, "battery_status": 15,
            "timestamp": timezone.now().isoformat()
        }
        response = self.client.post(self.update_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Alert.objects.filter(child=self.child, alert_type='LOW_BATTERY').exists())
        # Check if FCM was called for the low battery alert
        fcm_call_for_low_battery = any(
            call_args[1].get('data', {}).get('alert_type') == 'LOW_BATTERY'
            for call_args in mock_send_fcm.call_args_list
        )
        self.assertTrue(fcm_call_for_low_battery)

        low_battery_ws_call_found = False
        for call_args in mock_channel_layer_instance.group_send.call_args_list:
            args, kwargs = call_args
            if kwargs.get('message', {}).get('type') == 'low_battery_alert':
                low_battery_ws_call_found = True
                break
        self.assertTrue(low_battery_ws_call_found, "low_battery_alert WebSocket message not found")

    @patch('api.views.send_fcm_to_user')
    @patch('api.views.get_channel_layer')
    def test_safe_zone_exit_alert_and_cooldown(self, mock_get_channel_layer, mock_send_fcm):
        mock_ch_layer = MagicMock()
        mock_get_channel_layer.return_value = mock_ch_layer

        # Simulate child was previously inside
        Alert.objects.create(recipient=self.parent, child=self.child, safe_zone=self.home_zone,
                             alert_type='ENTERED_ZONE', message="Entered Home",
                             timestamp=timezone.now() - timedelta(minutes=20))

        # Child moves outside the zone
        data_outside = {
            "child_id": self.child.id, "device_id": "dev_alert", "latitude": 0.002, "longitude": 0.002,
            "timestamp": timezone.now().isoformat(), "battery_status": 89
        }
        response = self.client.post(self.update_url, data_outside)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(Alert.objects.filter(child=self.child, alert_type='LEFT_ZONE', safe_zone=self.home_zone).exists())

        fcm_call_for_left_zone = any(
            call_args[1].get('data', {}).get('alert_type') == 'LEFT_ZONE'
            for call_args in mock_send_fcm.call_args_list
        )
        self.assertTrue(fcm_call_for_left_zone)

        alert_ws_call_found = any(
            call_args[1]['message'].get('type') == 'safezone_alert' and call_args[1]['message'].get('alert_type') == 'LEFT_ZONE'
            for call_args in mock_ch_layer.group_send.call_args_list
        )
        self.assertTrue(alert_ws_call_found)

        # Reset mocks for cooldown test
        mock_send_fcm.reset_mock()
        mock_ch_layer.reset_mock() # Reset all mocks on this instance

        # Child moves again, still outside, within cooldown
        data_still_outside = {
            "child_id": self.child.id, "device_id": "dev_alert", "latitude": 0.003, "longitude": 0.003,
            "timestamp": (Alert.objects.get(child=self.child, alert_type='LEFT_ZONE').timestamp + timedelta(minutes=1)).isoformat(),
            "battery_status": 88
        }
        response = self.client.post(self.update_url, data_still_outside)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Alert.objects.filter(child=self.child, alert_type='LEFT_ZONE', safe_zone=self.home_zone).count(), 1) # Still 1
        mock_send_fcm.assert_not_called()


class ChildCheckInViewTests(APITestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username='parent_checkin', password='password')
        self.child = Child.objects.create(parent=self.parent, name='CheckerChild', device_id='dev_checkin', is_active=True)
        self.url = reverse('child-check-in')

    @patch('api.views.send_fcm_to_user')
    @patch('api.views.get_channel_layer')
    def test_child_check_in_success(self, mock_get_channel_layer, mock_send_fcm):
        mock_channel_layer_instance = MagicMock()
        mock_get_channel_layer.return_value = mock_channel_layer_instance
        data = {
            "child_id": self.child.id, "device_id": "dev_checkin",
            "check_in_type": "ARRIVED_SCHOOL", "custom_message": "",
            "latitude": 12.34, "longitude": 56.78, "location_name": "School Front Gate",
            "client_timestamp_iso": timezone.now().isoformat()
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(Alert.objects.filter(child=self.child, alert_type='CHECK_IN').exists())
        self.assertTrue(LocationPoint.objects.filter(child=self.child, latitude=12.34).exists())
        mock_send_fcm.assert_called_once()
        mock_channel_layer_instance.group_send.assert_called_once()
        args, kwargs = mock_channel_layer_instance.group_send.call_args
        self.assertEqual(kwargs['message']['type'], 'child_check_in')


class SOSAlertViewTests(APITestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username='parent_sos', password='password')
        self.child = Child.objects.create(parent=self.parent, name='SOSChild', device_id='dev_sos', is_active=True)
        self.url = reverse('alert-sos')

    @patch('api.views.send_fcm_to_user')
    def test_sos_alert_success(self, mock_send_fcm):
        data = {
            "child_id": self.child.id, "device_id": "dev_sos",
            "latitude": 15.0, "longitude": 30.0
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(Alert.objects.filter(child=self.child, alert_type='SOS').exists())
        mock_send_fcm.assert_called_once()


class LocationRetrievalViewTests(APITestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username='parent_loc_retrieve', password='password')
        self.child = Child.objects.create(parent=self.parent, name='RetrievedChild', device_id='dev_retrieve', is_active=True)
        self.other_parent = User.objects.create_user(username='otherparent_loc', password='password')
        LocationPoint.objects.create(child=self.child, latitude=1.0, longitude=1.0, timestamp=timezone.now() - timedelta(minutes=10))
        LocationPoint.objects.create(child=self.child, latitude=1.1, longitude=1.1, timestamp=timezone.now() - timedelta(minutes=5))
        self.latest_loc_obj = LocationPoint.objects.create(child=self.child, latitude=1.2, longitude=1.2, timestamp=timezone.now() - timedelta(minutes=1))
        self.current_url = reverse('child-current-location', kwargs={'child_id': self.child.id})
        self.history_url = reverse('child-location-history', kwargs={'child_id': self.child.id})

    def test_get_current_location_success(self):
        self.client.force_authenticate(user=self.parent)
        response = self.client.get(self.current_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(float(response.data['latitude']), self.latest_loc_obj.latitude)

    def test_get_current_location_unauthorized(self):
        self.client.force_authenticate(user=self.other_parent)
        response = self.client.get(self.current_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_location_history_success(self):
        self.client.force_authenticate(user=self.parent)
        response = self.client.get(self.history_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 3)
        self.assertEqual(float(results[0]['latitude']), 1.2)

    def test_get_location_history_with_time_filter(self):
        self.client.force_authenticate(user=self.parent)
        start_time = (timezone.now() - timedelta(minutes=7)).isoformat()
        response = self.client.get(f"{self.history_url}?start_timestamp={start_time}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 2)


class EtaSharingViewSetTests(APITestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username='eta_sharer', password='password', email='eta1@example.com')
        self.user2 = User.objects.create_user(username='eta_viewer1', password='password', email='eta2@example.com')
        self.user3 = User.objects.create_user(username='eta_viewer2', password='password', email='eta3@example.com')
        self.start_url = reverse('eta-start')

    @patch('api.views.send_fcm_to_user')
    @patch('api.views.get_channel_layer')
    def test_start_eta_share_success(self, mock_get_channel_layer, mock_send_fcm):
        mock_channel_layer_instance = MagicMock()
        mock_get_channel_layer.return_value = mock_channel_layer_instance
        self.client.force_authenticate(user=self.user1)
        data = {
            "destination_name": "Work", "destination_latitude": 1.23, "destination_longitude": 4.56,
            "current_latitude": 0.12, "current_longitude": 0.34,
            "shared_with_user_ids": [self.user2.id, self.user3.id]
        }
        response = self.client.post(self.start_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(ActiveEtaShare.objects.count(), 1)
        eta_share = ActiveEtaShare.objects.first()
        self.assertEqual(eta_share.sharer, self.user1)
        self.assertIn(self.user2, eta_share.shared_with.all())
        self.assertIsNotNone(eta_share.calculated_eta)
        self.assertEqual(mock_send_fcm.call_count, 2)
        self.assertEqual(mock_channel_layer_instance.group_send.call_count, 2)
        args, kwargs = mock_channel_layer_instance.group_send.call_args_list[0]
        self.assertEqual(kwargs['message']['type'], 'eta_started')

    def test_start_eta_share_invalid_data(self):
        self.client.force_authenticate(user=self.user1)
        data = {"destination_latitude": 1.0}
        response = self.client.post(self.start_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('api.views.get_channel_layer')
    def test_update_eta_location_success(self, mock_get_channel_layer):
        mock_channel_layer_instance = MagicMock()
        mock_get_channel_layer.return_value = mock_channel_layer_instance
        self.client.force_authenticate(user=self.user1)
        eta_share = ActiveEtaShare.objects.create(
            sharer=self.user1, destination_latitude=1.0, destination_longitude=1.0,
            current_latitude=0.0, current_longitude=0.0, status='ACTIVE'
        )
        eta_share.shared_with.add(self.user2)
        update_url = reverse('eta-update-location', kwargs={'share_id': eta_share.id})
        data = {"current_latitude": 0.5, "current_longitude": 0.5}
        response = self.client.post(update_url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        eta_share.refresh_from_db()
        self.assertEqual(eta_share.current_latitude, 0.5)
        self.assertIsNotNone(response.data.get('calculated_eta'))
        self.assertEqual(mock_channel_layer_instance.group_send.call_count, 2)
        args, kwargs = mock_channel_layer_instance.group_send.call_args_list[0]
        self.assertEqual(kwargs['message']['type'], 'eta_updated')

    def test_update_eta_location_not_sharer_forbidden(self):
        self.client.force_authenticate(user=self.user2)
        eta_share = ActiveEtaShare.objects.create(sharer=self.user1, destination_latitude=1.0, destination_longitude=1.0, status='ACTIVE')
        update_url = reverse('eta-update-location', kwargs={'share_id': eta_share.id})
        data = {"current_latitude": 0.5, "current_longitude": 0.5}
        response = self.client.post(update_url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_active_eta_shares(self):
        self.client.force_authenticate(user=self.user1)
        ActiveEtaShare.objects.create(sharer=self.user1, destination_latitude=1.0, destination_longitude=1.0, status='ACTIVE')
        ActiveEtaShare.objects.create(sharer=self.user2, destination_latitude=2.0, destination_longitude=2.0, status='ACTIVE').shared_with.add(self.user1)
        ActiveEtaShare.objects.create(sharer=self.user2, destination_latitude=3.0, destination_longitude=3.0, status='CANCELLED').shared_with.add(self.user1)

        response = self.client.get(reverse('eta-active-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 2)

    @patch('api.views.get_channel_layer')
    def test_cancel_eta_share_success(self, mock_get_channel_layer):
        mock_channel_layer_instance = MagicMock()
        mock_get_channel_layer.return_value = mock_channel_layer_instance
        self.client.force_authenticate(user=self.user1)
        eta_share = ActiveEtaShare.objects.create(sharer=self.user1, destination_latitude=1.0, destination_longitude=1.0, status='ACTIVE')
        eta_share.shared_with.add(self.user2)

        cancel_url = reverse('eta-cancel', kwargs={'share_id': eta_share.id})
        response = self.client.post(cancel_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        eta_share.refresh_from_db()
        self.assertEqual(eta_share.status, 'CANCELLED')
        self.assertEqual(mock_channel_layer_instance.group_send.call_count, 2)
        args, kwargs = mock_channel_layer_instance.group_send.call_args_list[0]
        self.assertEqual(kwargs['message']['type'], 'eta_cancelled')

    @patch('api.views.get_channel_layer')
    def test_arrived_eta_share_success(self, mock_get_channel_layer):
        mock_channel_layer_instance = MagicMock()
        mock_get_channel_layer.return_value = mock_channel_layer_instance
        self.client.force_authenticate(user=self.user1)
        eta_share = ActiveEtaShare.objects.create(sharer=self.user1, destination_latitude=1.0, destination_longitude=1.0, status='ACTIVE')
        eta_share.shared_with.add(self.user2)

        arrived_url = reverse('eta-arrived', kwargs={'share_id': eta_share.id})
        response = self.client.post(arrived_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        eta_share.refresh_from_db()
        self.assertEqual(eta_share.status, 'ARRIVED')
        self.assertEqual(mock_channel_layer_instance.group_send.call_count, 2)
        args, kwargs = mock_channel_layer_instance.group_send.call_args_list[0]
        self.assertEqual(kwargs['message']['type'], 'eta_arrived')


class MessagingViewTests(APITestCase):
    def setUp(self):
        self.user_msg1 = User.objects.create_user(username='msg_sender', password='password', first_name='Msg', last_name='Sender')
        self.user_msg2 = User.objects.create_user(username='msg_receiver', password='password', first_name='Msg', last_name='Receiver')
        self.parent_for_child_msg = User.objects.create_user(username='parent_msg_child', password='password')
        self.child_msg = Child.objects.create(parent=self.parent_for_child_msg, name='MessagingChild', device_id='dev_msg_child', is_active=True)

        self.send_msg_url = reverse('message-send')
        self.child_send_msg_url = reverse('child-message-send')
        self.conversations_url = reverse('message-conversations')
        self.history_url_user2 = reverse('message-history', kwargs={'other_user_id': self.user_msg2.id})
        self.read_url = reverse('messages-mark-read')

    @patch('api.views.send_fcm_to_user')
    @patch('api.views.get_channel_layer')
    def test_send_message_parent_to_parent_success(self, mock_get_channel_layer, mock_send_fcm):
        mock_channel_layer_instance = MagicMock()
        mock_get_channel_layer.return_value = mock_channel_layer_instance
        self.client.force_authenticate(user=self.user_msg1)

        data = {"receiver_id": self.user_msg2.id, "content": "Hello Parent2 from Parent1"}
        response = self.client.post(self.send_msg_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(Message.objects.count(), 1)
        msg = Message.objects.first()
        self.assertEqual(msg.sender, self.user_msg1)
        self.assertEqual(msg.receiver, self.user_msg2)

        mock_send_fcm.assert_called_once()
        mock_channel_layer_instance.group_send.assert_called_once()
        args, kwargs = mock_channel_layer_instance.group_send.call_args
        self.assertEqual(kwargs['type'], 'new.chat.message')
        self.assertEqual(kwargs['payload']['type'], 'new_message')


    @patch('api.views.send_fcm_to_user')
    @patch('api.views.get_channel_layer')
    def test_send_message_child_to_parent_success(self, mock_get_channel_layer, mock_send_fcm):
        mock_channel_layer_instance = MagicMock()
        mock_get_channel_layer.return_value = mock_channel_layer_instance

        data = {
            "child_id": self.child_msg.id,
            "device_id": self.child_msg.device_id,
            "content": "Hello Parent from Child"
        }
        response = self.client.post(self.child_send_msg_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(Message.objects.count(), 1)
        msg = Message.objects.first()
        self.assertEqual(msg.sender, self.child_msg.proxy_user)
        self.assertEqual(msg.receiver, self.parent_for_child_msg)

        mock_send_fcm.assert_called_once()
        mock_channel_layer_instance.group_send.assert_called_once()
        args, kwargs = mock_channel_layer_instance.group_send.call_args
        self.assertEqual(kwargs['type'], 'new.chat.message')
        self.assertEqual(kwargs['payload']['type'], 'new_message')

    def test_list_conversations(self):
        self.client.force_authenticate(user=self.user_msg1)
        Message.objects.create(sender=self.user_msg1, receiver=self.user_msg2, content="Hi U2")
        Message.objects.create(sender=self.parent_for_child_msg, receiver=self.user_msg1, content="Hi U1 from Parent")

        response = self.client.get(self.conversations_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_get_message_history(self):
        self.client.force_authenticate(user=self.user_msg1)
        Message.objects.create(sender=self.user_msg1, receiver=self.user_msg2, content="Msg1")
        Message.objects.create(sender=self.user_msg2, receiver=self.user_msg1, content="Msg2 reply")

        response = self.client.get(self.history_url_user2)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['content'], "Msg1")

    @patch('api.views.get_channel_layer')
    def test_mark_messages_as_read(self, mock_get_channel_layer):
        mock_channel_layer_instance = MagicMock()
        mock_get_channel_layer.return_value = mock_channel_layer_instance
        self.client.force_authenticate(user=self.user_msg1)

        Message.objects.create(sender=self.user_msg2, receiver=self.user_msg1, content="Unread Msg", is_read=False)
        self.assertEqual(Message.objects.filter(receiver=self.user_msg1, is_read=False).count(), 1)

        data = {"other_user_id": self.user_msg2.id}
        response = self.client.post(self.read_url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['messages_updated'], 1)
        self.assertEqual(Message.objects.filter(receiver=self.user_msg1, is_read=False).count(), 0)

        mock_channel_layer_instance.group_send.assert_called_once()
        args, kwargs = mock_channel_layer_instance.group_send.call_args
        self.assertEqual(kwargs['type'], 'messages.read.receipt')
        self.assertEqual(kwargs['payload']['reader_id'], str(self.user_msg1.id))

class DeviceRegistrationViewTests(APITestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username='dev_rego_user1', password='password')
        self.user2 = User.objects.create_user(username='dev_rego_user2', password='password')
        self.url = reverse('device-register')

    def test_register_new_device_success(self):
        self.client.force_authenticate(user=self.user1)
        data = {"device_token": "new_device_token_123", "device_type": "android"}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(UserDevice.objects.filter(user=self.user1, device_token="new_device_token_123", device_type="android", is_active=True).exists())

    def test_register_same_device_same_user_updates(self):
        self.client.force_authenticate(user=self.user1)
        UserDevice.objects.create(user=self.user1, device_token="existing_token_456", device_type="ios", is_active=True)

        data = {"device_token": "existing_token_456", "device_type": "android"}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(UserDevice.objects.filter(device_token="existing_token_456").count(), 1)
        user_device = UserDevice.objects.get(device_token="existing_token_456")
        self.assertEqual(user_device.user, self.user1)
        self.assertEqual(user_device.device_type, "android")
        self.assertTrue(user_device.is_active)

    def test_register_same_device_different_user_deactivates_old(self):
        UserDevice.objects.create(user=self.user1, device_token="shared_token_789", device_type="android", is_active=True)

        self.client.force_authenticate(user=self.user2)
        data = {"device_token": "shared_token_789", "device_type": "ios"}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        old_device_entry = UserDevice.objects.get(user=self.user1, device_token="shared_token_789")
        self.assertFalse(old_device_entry.is_active)

        new_device_entry = UserDevice.objects.get(user=self.user2, device_token="shared_token_789")
        self.assertTrue(new_device_entry.is_active)
        self.assertEqual(new_device_entry.device_type, "ios")

    def test_register_device_unauthenticated(self):
        data = {"device_token": "unauth_token", "device_type": "android"}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_register_device_empty_token_fails(self):
        self.client.force_authenticate(user=self.user1)
        data = {"device_token": "", "device_type": "android"}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("device_token", response.data)
