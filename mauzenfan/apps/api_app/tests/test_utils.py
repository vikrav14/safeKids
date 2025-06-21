# mauzenfan/server/api_app./tests/test_utils.py
from django.test import TestCase
from unittest.mock import patch, MagicMock, ANY
from api_app..geolocation_utils import distance_in_meters, calculate_average_distance_to_path
from api_app. import weather_service # Import the module to allow patching its globals
from api_app. import fcm_service     # Import the module to allow patching its globals
from django.conf import settings
from django.contrib.auth.models import User
from api_app..models import UserDevice
# To prevent "Apps aren't loaded yet" error when fcm_service.py (which imports models) is imported at test collection time
# We might need to ensure Django is fully set up if fcm_service.py tries to access models at import time.
# However, fcm_service.UserDevice import is inside a function, so it should be fine.

# If firebase_admin is imported at module level in fcm_service.py and tries to initialize,
# we might need to mock it very early or ensure settings are configured.
# For now, assume fcm_service.py is structured to allow testing without full SDK init.

class GeolocationUtilsTests(TestCase):
    def test_distance_in_meters(self):
        # Approx Eiffel Tower to Notre Dame
        lat1, lon1 = 48.8584, 2.2945
        lat2, lon2 = 48.8530, 2.3499
        distance = distance_in_meters(lat1, lon1, lat2, lon2)
        self.assertAlmostEqual(distance, 4114, delta=50)

    def test_calculate_average_distance_to_path(self):
        routine_path = [[0.0, 0.0], [0.0, 1.0], [0.0, 2.0]]
        trip1 = [[0.0, 0.0], [0.0, 1.0], [0.0, 2.0]] # Perfect match
        self.assertAlmostEqual(calculate_average_distance_to_path(trip1, routine_path), 0.0, delta=1)

        # Each point in trip2 is approx 111.195 meters away from the corresponding routine_path vertex
        # (0.001 degree latitude difference)
        trip2 = [[0.001, 0.0], [0.001, 1.0], [0.001, 2.0]]
        expected_avg_dist_trip2 = distance_in_meters(0.001, 0.0, 0.0, 0.0)
        self.assertAlmostEqual(calculate_average_distance_to_path(trip2, routine_path), expected_avg_dist_trip2, delta=1)

        self.assertEqual(calculate_average_distance_to_path([], routine_path), float('inf'))
        self.assertEqual(calculate_average_distance_to_path(trip1, []), float('inf'))


class WeatherServiceTests(TestCase):

    @patch('api_app..weather_service.OWM') # Patch OWM class used for client creation
    def test_get_weather_forecast_success(self, MockOWM):
        # Configure the mock OWM client and its manager
        mock_owm_instance = MagicMock()
        mock_mgr = MagicMock()
        mock_owm_instance.weather_manager.return_value = mock_mgr
        MockOWM.return_value = mock_owm_instance # OWM(api_app._KEY) returns our mock

        # Mock the one_call response
        mock_one_call_data = MagicMock()
        mock_hourly1 = MagicMock()
        mock_hourly1.reference_time.return_value = '2023-01-01T12:00:00Z'
        mock_hourly1.temperature.return_value = {'temp': 10.0, 'feels_like': 9.0}
        mock_hourly1.humidity = 80
        mock_hourly1.wind.return_value = {'speed': 5.0}
        mock_hourly1.precipitation_probability = 0.1
        mock_hourly1.weather_code = 800
        mock_hourly1.detailed_status = 'clear sky'
        mock_hourly1.rain = {}
        mock_hourly1.snow = {}

        mock_one_call_data.forecast_hourly = [mock_hourly1] * 12
        mock_one_call_data.forecast_daily = []
        mock_one_call_data.national_weather_alerts = []
        mock_mgr.one_call.return_value = mock_one_call_data

        # Temporarily set WEATHER_api_app._KEY in settings for the service to attempt initialization
        # and use our MockOWM which returns the mock_owm_instance.
        with self.settings(WEATHER_api_app._KEY='fakekey'):
            # Re-initialize the client within the service or ensure the service can use a mocked client
            # The weather_service initializes owm_client at module level.
            # To test this properly, we'd need to reload the module with new settings,
            # or the service refactored to initialize client on demand or take it as arg.
            # For this test, we directly patch the 'owm_client' global in the weather_service module.
            with patch('api_app..weather_service.owm_client', mock_owm_instance):
                result = weather_service.get_weather_forecast(10.0, 10.0)

        self.assertIsNotNone(result)
        self.assertEqual(len(result['hourly_forecast']), 12)
        self.assertEqual(result['hourly_forecast'][0]['temp'], 10.0)
        mock_mgr.one_call.assert_called_once_with(lat=10.0, lon=10.0, exclude='minutely,current')

    @patch('api_app..weather_service.owm_client', None) # Ensure client is None
    def test_get_weather_forecast_no_client(self):
        result = weather_service.get_weather_forecast(10.0, 10.0)
        self.assertIsNone(result)

    @patch('api_app..weather_service.OWM')
    def test_get_weather_forecast_api_app._error(self, MockOWM):
        mock_owm_instance = MagicMock()
        mock_mgr = MagicMock()
        mock_mgr.one_call.side_effect = Exception("OWM api_app. Error")
        mock_owm_instance.weather_manager.return_value = mock_mgr
        MockOWM.return_value = mock_owm_instance

        with self.settings(WEATHER_api_app._KEY='fakekey_error'):
            with patch('api_app..weather_service.owm_client', mock_owm_instance):
                result = weather_service.get_weather_forecast(10.0, 10.0)
        self.assertIsNone(result)


@patch('api_app..fcm_service.firebase_admin.initialize_app') # Mock initialize_app
@patch('api_app..fcm_service.firebase_admin.credentials.Certificate') # Mock Certificate
@patch('api_app..fcm_service.firebase_admin.messaging') # Mock messaging module
class FCMServiceTests(TestCase):

    def setUp(self):
        self.user1 = User.objects.create_user(username='fcmuser1')
        UserDevice.objects.create(user=self.user1, device_token='token1', is_active=True)
        UserDevice.objects.create(user=self.user1, device_token='token2', is_active=True)

        # Ensure the fcm_service's global 'firebase_admin._apps' thinks it's initialized
        # This prevents re-initialization attempts if the module was already imported.
        # We also need to ensure our mock_messaging is used.
        # The fcm_service module might have already been imported.
        # One way is to patch firebase_admin._apps at module level for fcm_service
        self.apps_patch = patch.object(fcm_service.firebase_admin, '_apps', {'mock_app': True})
        self.apps_patch.start()


    def tearDown(self):
        self.apps_patch.stop()

    def test_send_fcm_notification(self, mock_messaging, MockCertificate, MockInitializeApp):
        mock_response = MagicMock()
        mock_response.success_count = 1
        mock_response.failure_count = 0
        mock_messaging.send_multicast.return_value = mock_response

        tokens = ['token123']
        title = "Test Title"
        body = "Test Body"
        data = {"key": "value"}

        success = fcm_service.send_fcm_notification(tokens, title, body, data)

        self.assertTrue(success)
        mock_messaging.send_multicast.assert_called_once()
        # Check that MulticastMessage was called with the right parameters
        # ANY is used because Notification is an object created inside
        mock_messaging.MulticastMessage.assert_called_once_with(
            notification=ANY,
            data={'key': 'value'}, # Data should be stringified by the service
            tokens=tokens
        )

    def test_send_fcm_to_user(self, mock_messaging, MockCertificate, MockInitializeApp):
        mock_response = MagicMock()
        mock_response.success_count = 2
        mock_response.failure_count = 0
        mock_messaging.send_multicast.return_value = mock_response

        title = "User Test Title"
        body = "User Test Body"

        success = fcm_service.send_fcm_to_user(self.user1, title, body)
        self.assertTrue(success)
        mock_messaging.send_multicast.assert_called_once()
        called_message_arg = mock_messaging.MulticastMessage.call_args[0] # Get the MulticastMessage instance
        self.assertCountEqual(called_message_arg['tokens'], ['token1', 'token2'])
        # Accessing notification object from MulticastMessage call
        self.assertEqual(called_message_arg['notification'].title, title)

    def test_send_fcm_no_sdk(self, mock_messaging, MockCertificate, MockInitializeApp):
        with patch.object(fcm_service.firebase_admin, '_apps', {}): # Simulate SDK not initialized
            success = fcm_service.send_fcm_notification(['token1'], "Title", "Body")
            self.assertFalse(success)

    def test_send_fcm_no_tokens(self, mock_messaging, MockCertificate, MockInitializeApp):
        success = fcm_service.send_fcm_notification([], "Title", "Body")
        self.assertFalse(success)
        mock_messaging.send_multicast.assert_not_called()

    def test_send_fcm_to_user_no_devices(self, mock_messaging, MockCertificate, MockInitializeApp):
        no_device_user = User.objects.create_user(username='nodeviceuser')
        success = fcm_service.send_fcm_to_user(no_device_user, "Title", "Body")
        self.assertFalse(success)
        mock_messaging.send_multicast.assert_not_called()
