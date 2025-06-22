# mauzenfan/server/api_app/tests/test_tasks.py
from django.test import TestCase
from unittest.mock import patch, MagicMock, call, ANY
from django.contrib.auth.models import User
from api_app.models import Child, LocationPoint, SafeZone, Alert, LearnedRoutine, UserDevice
from api_app.tasks import (
    check_weather_for_children_alerts,
    learn_child_routine_task,
    analyze_trip_task,
    schedule_routine_learning_for_all_active_children,
    MIN_PRECIPITATION_PROBABILITY_THRESHOLD,
    WEATHER_ALERT_COOLDOWN_HOURS,
    ROUTINE_LEARNING_DATA_DAYS, # Import constants used in tasks
    SIGNIFICANT_PLACE_PROXIMITY_METERS,
    MIN_TRIP_POINTS,
    MIN_TRIPS_FOR_ROUTINE,
    PATH_DEVIATION_THRESHOLD_METERS,
    TIME_DEVIATION_THRESHOLD_MINUTES,
    SIGNIFICANT_PLACE_PROXIMITY_FOR_TRIP_MATCH_METERS
)
from django.utils import timezone
from datetime import timedelta, time, datetime
import json
import logging

# Disable most logging for cleaner test output, enable for debugging if needed
# logging.disable(logging.INFO)


class CheckWeatherForChildrenAlertsTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username='task_parent_weather', password='password')
        self.child1 = Child.objects.create(parent=self.parent, name='WeatherChild1', device_id='dev_weather1', is_active=True, last_seen_at=timezone.now() - timedelta(minutes=30))
        LocationPoint.objects.create(
            child=self.child1, latitude=10.0, longitude=10.0,
            timestamp=self.child1.last_seen_at
        )
        self.child2 = Child.objects.create(parent=self.parent, name='WeatherChild2NoRecentLoc', device_id='dev_weather2', is_active=True, last_seen_at=timezone.now() - timedelta(hours=2))
        self.child3_inactive = Child.objects.create(parent=self.parent, name='WeatherChild3Inactive', device_id='dev_weather3', is_active=False, last_seen_at=timezone.now() - timedelta(minutes=30))

    @patch('api_app.tasks.get_channel_layer') # Patch for potential WebSocket calls if added later
    @patch('api_app.tasks.send_fcm_to_user')
    @patch('api_app.tasks.get_weather_forecast')
    def test_weather_alert_for_precipitation(self, mock_get_weather, mock_send_fcm, mock_get_channel_layer):
        mock_weather_data = {
            'alerts': [],
            'hourly_forecast': [{
                'time': (timezone.now() + timedelta(hours=1)).isoformat(),
                'precipitation_probability': 0.8,
                'detailed_status': 'heavy rain',
                'temp': 20, 'weather_code': 501, 'rain_volume_1h': 2.5, 'snow_volume_1h':0, 'feels_like': 19, 'humidity': 80, 'wind_speed': 5.0
            }] * 3
        }
        mock_get_weather.return_value = mock_weather_data

        check_weather_for_children_alerts()

        self.assertTrue(Alert.objects.filter(child=self.child1, alert_type='CONTEXTUAL_WEATHER', message__icontains='heavy rain').exists())
        mock_send_fcm.assert_called_once()
        fcm_args, fcm_kwargs = mock_send_fcm.call_args
        self.assertEqual(fcm_args[0], self.parent)
        self.assertIn("heavy rain", fcm_kwargs['body'].lower())
        mock_get_weather.assert_called_once_with(10.0, 10.0)

    @patch('api_app.tasks.get_channel_layer')
    @patch('api_app.tasks.send_fcm_to_user')
    @patch('api_app.tasks.get_weather_forecast')
    def test_weather_alert_cooldown(self, mock_get_weather, mock_send_fcm, mock_get_channel_layer):
        mock_weather_data = {'alerts': [], 'hourly_forecast': [{'precipitation_probability': 0.8, 'detailed_status': 'rain', 'time': (timezone.now() + timedelta(hours=1)).isoformat(), 'temp': 18, 'weather_code': 500, 'rain_volume_1h': 1.0, 'snow_volume_1h':0, 'feels_like': 17, 'humidity': 85, 'wind_speed': 4.0}]*3}
        mock_get_weather.return_value = mock_weather_data

        check_weather_for_children_alerts()
        self.assertEqual(Alert.objects.filter(child=self.child1, alert_type='CONTEXTUAL_WEATHER').count(), 1)
        mock_send_fcm.assert_called_once()

        mock_send_fcm.reset_mock()
        check_weather_for_children_alerts()
        self.assertEqual(Alert.objects.filter(child=self.child1, alert_type='CONTEXTUAL_WEATHER').count(), 1)
        mock_send_fcm.assert_not_called()

        existing_alert = Alert.objects.filter(child=self.child1, alert_type='CONTEXTUAL_WEATHER').first()
        existing_alert.timestamp = timezone.now() - timedelta(hours=WEATHER_ALERT_COOLDOWN_HOURS + 1)
        existing_alert.save()

        check_weather_for_children_alerts()
        self.assertEqual(Alert.objects.filter(child=self.child1, alert_type='CONTEXTUAL_WEATHER').count(), 2)
        mock_send_fcm.assert_called_once()


class LearnChildRoutineTaskTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username='task_parent_routine', password='password')
        self.child = Child.objects.create(parent=self.parent, name='RoutineChild', device_id='dev_routine', is_active=True)
        self.home_zone = SafeZone.objects.create(owner=self.parent, name='Home', latitude=0.0, longitude=0.0, radius=SIGNIFICANT_PLACE_PROXIMITY_METERS, is_active=True)
        self.school_zone = SafeZone.objects.create(owner=self.parent, name='Lekol', latitude=1.0, longitude=1.0, radius=SIGNIFICANT_PLACE_PROXIMITY_METERS, is_active=True)

        # Simulate 3 Home-To-School trips on Mon, Tue, Wed mornings
        days = [0, 1, 2] # Mon, Tue, Wed
        start_hours = [8, 8, 8]
        start_minutes = [0, 5, 2]

        for i, day_offset in enumerate(days):
            # Find the actual date for that day of the week (e.g., next Monday)
            today = timezone.now().date()
            actual_date = today + timedelta(days=(day_offset - today.weekday() + 7) % 7)

            current_time = timezone.make_aware(datetime.combine(actual_date, time(start_hours[i], start_minutes[i])))

            # Start slightly outside home zone, move towards school zone
            # For simplicity, creating a linear path
            for j in range(MIN_TRIP_POINTS + 1): # e.g., 6 points for a 5-segment trip
                progress = j / MIN_TRIP_POINTS
                lat = self.home_zone.latitude + (self.school_zone.latitude - self.home_zone.latitude) * progress
                lon = self.home_zone.longitude + (self.school_zone.longitude - self.home_zone.longitude) * progress
                # Add some minor "outside zone" points at start/end if needed by strict segmentation
                if j == 0: lat -= 0.002; lon -=0.002 # Start "outside" home
                if j == MIN_TRIP_POINTS : lat +=0.002; lon +=0.002 # End "outside" school (or rather, ensure last point is IN school)

                # Ensure first point is outside home, last point is inside school for H-S trip
                if j == 0:
                    lat = self.home_zone.latitude + (0.002 if self.school_zone.latitude > self.home_zone.latitude else -0.002) # Just outside
                    lon = self.home_zone.longitude + (0.002 if self.school_zone.longitude > self.home_zone.longitude else -0.002)
                elif j == MIN_TRIP_POINTS: # Ensure last point is well within school zone
                    lat = self.school_zone.latitude
                    lon = self.school_zone.longitude


                LocationPoint.objects.create(child=self.child, latitude=lat, longitude=lon, timestamp=current_time + timedelta(minutes=j*5))

    def test_learn_home_to_school_routine(self):
        LearnedRoutine.objects.filter(child=self.child).delete()
        learn_child_routine_task(self.child.id)

        self.assertTrue(LearnedRoutine.objects.filter(child=self.child, name__icontains="Home to School").exists())
        routine = LearnedRoutine.objects.get(child=self.child, name__icontains="Home to School")

        self.assertEqual(routine.start_location_name, "Home")
        self.assertEqual(routine.end_location_name, "Lekol")
        # Days might be tricky due to date generation, check if any common days were found
        self.assertTrue(len(routine.typical_days_of_week.split(',')) > 0, "Should find some common days")
        self.assertAlmostEqual(routine.typical_time_window_start_min.hour, 8, delta=1)
        self.assertIsNotNone(routine.route_path_approximation_json)
        path_data = json.loads(routine.route_path_approximation_json)
        self.assertGreaterEqual(len(path_data), MIN_TRIP_POINTS)
        self.assertGreater(routine.confidence_score, 0)


class AnalyzeTripTaskTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username='task_parent_analyze', password='password')
        self.child = Child.objects.create(parent=self.parent, name='AnalyzeChild', device_id='dev_analyze', is_active=True)
        self.routine = LearnedRoutine.objects.create(
            child=self.child, name="Home to School Test Routine",
            start_latitude_approx=0.0, start_longitude_approx=0.0,
            end_latitude_approx=1.0, end_longitude_approx=1.0,
            typical_days_of_week="0,1,2,3,4",
            typical_time_window_start_min=time(8,0), typical_time_window_start_max=time(9,0),
            route_path_approximation_json=json.dumps([[0.0,0.0],[0.5,0.5],[1.0,1.0]]),
            confidence_score=0.8, is_active=True
        )

    @patch('api_app.tasks.send_fcm_to_user')
    @patch('api_app.tasks.get_channel_layer')
    def test_analyze_trip_normal_trip_matches_routine(self, mock_get_channel_layer, mock_send_fcm):
        trip_time = timezone.make_aware(datetime(2023, 10, 2, 8, 30)) # Monday 8:30 AM
        trip_points = [
            {'lat': 0.0, 'lon': 0.0, 'ts': trip_time.isoformat()},
            {'lat': 0.5, 'lon': 0.5, 'ts': (trip_time + timedelta(minutes=10)).isoformat()},
            {'lat': 1.0, 'lon': 1.0, 'ts': (trip_time + timedelta(minutes=20)).isoformat()},
        ]
        analyze_trip_task(self.child.id, trip_points)
        self.assertFalse(Alert.objects.filter(child=self.child, alert_type='UNUSUAL_ROUTE').exists())
        mock_send_fcm.assert_not_called()

    @patch('api_app.tasks.send_fcm_to_user')
    @patch('api_app.tasks.get_channel_layer')
    def test_analyze_trip_path_deviation(self, mock_get_channel_layer, mock_send_fcm):
        trip_time = timezone.make_aware(datetime(2023, 10, 2, 8, 30))
        trip_points = [
            {'lat': 0.0, 'lon': 0.0, 'ts': trip_time.isoformat()},
            {'lat': 0.5, 'lon': 5.0, 'ts': (trip_time + timedelta(minutes=10)).isoformat()},
            {'lat': 1.0, 'lon': 1.0, 'ts': (trip_time + timedelta(minutes=20)).isoformat()},
        ]
        analyze_trip_task(self.child.id, trip_points)
        self.assertTrue(Alert.objects.filter(child=self.child, alert_type='UNUSUAL_ROUTE').exists())
        mock_send_fcm.assert_called_once()


class ScheduleRoutineLearningTests(TestCase):
    @patch('api_app.tasks.learn_child_routine_task.delay')
    def test_schedule_all_children(self, mock_learn_delay):
        parent1 = User.objects.create_user(username='sched_parent1')
        Child.objects.create(parent=parent1, name='SchedChild1', is_active=True)
        Child.objects.create(parent=parent1, name='SchedChild2', is_active=True)
        Child.objects.create(parent=parent1, name='SchedChild3Inactive', is_active=False)

        schedule_routine_learning_for_all_active_children()

        self.assertEqual(mock_learn_delay.call_count, 2)
