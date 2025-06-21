# mauzenfan/server/api_app/tasks.py
from celery import shared_task
from django.utils import timezone
from datetime import timedelta, time
import logging

from .models import Child, Alert, LocationPoint, SafeZone, LearnedRoutine
from .weather_service import get_weather_forecast
from .fcm_service import send_fcm_to_user
from .geolocation_utils import distance_in_meters, calculate_average_distance_to_path
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.shortcuts import get_object_or_404
from collections import Counter
import statistics
import json

logger = logging.getLogger(__name__)

# --- Constants for Weather Alerts ---
WEATHER_ALERT_COOLDOWN_HOURS = 3
MIN_PRECIPITATION_PROBABILITY_THRESHOLD = 0.6

@shared_task(name="check_weather_for_children_alerts")
def check_weather_for_children_alerts():
    logger.info("Starting periodic weather check for children...")
    active_children = Child.objects.filter(is_active=True)

    for child in active_children:
        logger.debug(f"Checking weather for child: {child.name} (ID: {child.id})")
        location_to_check = None
        location_name = "their current area"

        if child.last_seen_at and (timezone.now() - child.last_seen_at < timedelta(hours=1)):
            last_location_point = LocationPoint.objects.filter(child=child).order_by('-timestamp').first()
            if last_location_point:
                location_to_check = {
                    "lat": float(last_location_point.latitude),
                    "lon": float(last_location_point.longitude)
                }
                location_name = f"{child.name}'s current location ({last_location_point.latitude:.2f}, {last_location_point.longitude:.2f})"
            else:
                 logger.info(f"Child {child.name} has last_seen_at but no location points. Skipping weather check.")
                 continue
        else:
            logger.info(f"No recent location for child {child.name} (last_seen_at: {child.last_seen_at}). Skipping weather check.")
            continue

        weather_data = get_weather_forecast(location_to_check["lat"], location_to_check["lon"])

        if not weather_data:
            logger.warning(f"Could not retrieve weather data for {location_name}. Skipping child {child.name}.")
            continue

        parent_user = child.parent

        if weather_data.get('alerts'):
            for national_alert in weather_data['alerts']:
                alert_event_name = national_alert.get('event', 'Weather Alert')
                alert_description = national_alert.get('description', 'Important weather information.')
                alert_message = f"Weather Alert for {location_name}: {alert_event_name}. {alert_description}"

                if not Alert.objects.filter(
                    recipient=parent_user,
                    child=child,
                    alert_type='CONTEXTUAL_WEATHER',
                    message__icontains=alert_event_name,
                    timestamp__gte=timezone.now() - timedelta(hours=WEATHER_ALERT_COOLDOWN_HOURS * 2)
                ).exists():
                    created_alert = Alert.objects.create(
                        recipient=parent_user, child=child, alert_type='CONTEXTUAL_WEATHER', message=alert_message)
                    send_fcm_to_user(parent_user, title=f"Weather Alert: {alert_event_name}", body=alert_message, data={'alert_id': str(created_alert.id), 'type': 'weather_national'})
                    logger.info(f"Sent national weather alert FCM to parent of {child.name}: {alert_event_name}")

                    channel_layer = get_channel_layer()
                    group_name = f'user_{parent_user.id}_notifications'
                    ws_message_payload = {
                        'type': 'contextual_weather_alert',
                        'alert_id': str(created_alert.id),
                        'child_id': str(child.id),
                        'child_name': child.name,
                        'message': alert_message,
                        'timestamp': created_alert.timestamp.isoformat(),
                        'event_summary': alert_event_name
                    }
                    async_to_sync(channel_layer.group_send)(
                        group_name,
                        { "type": "send_notification", "message": ws_message_payload }
                    )
                    logger.info(f"Sent national weather alert WebSocket to parent of {child.name}: {alert_event_name}")

        if weather_data.get('hourly_forecast'):
            for hourly in weather_data['hourly_forecast'][:3]:
                precip_prob = hourly.get('precipitation_probability', 0)
                if precip_prob >= MIN_PRECIPITATION_PROBABILITY_THRESHOLD:
                    weather_desc = hourly.get('detailed_status', 'precipitation')
                    alert_time_obj = timezone.datetime.fromisoformat(hourly['time'].replace('Z','+00:00'))
                    alert_time_str = alert_time_obj.strftime('%I:%M %p')

                    base_message = f"{weather_desc.capi_apptalize()} likely near {location_name} around {alert_time_str} (Prob: {int(precip_prob*100)}%)."
                    suggestion = ""
                    alert_category = "Weather Update"

                    if "rain" in weather_desc.lower(): suggestion = " Consider taking an umbrella!"
                    elif "snow" in weather_desc.lower(): suggestion = " Dress warmly!"
                    elif "thunderstorm" in weather_desc.lower():
                        suggestion = " Stay safe and be aware of lightning."
                        alert_category = "Weather Alert"
                    alert_message = f"{alert_category}: {base_message}{suggestion}"

                    if "thunderstorm" in weather_desc.lower(): push_title = f"Thunderstorm Alert for {child.name}"
                    elif "rain" in weather_desc.lower() or "snow" in weather_desc.lower(): push_title = f"{weather_desc.capi_apptalize()} Forecast for {child.name}"
                    else: push_title = f"Weather Update for {child.name}"

                    if not Alert.objects.filter(
                        recipient=parent_user, child=child, alert_type='CONTEXTUAL_WEATHER',
                        message__startswith=f"{alert_category}: {base_message}",
                        timestamp__gte=timezone.now() - timedelta(hours=WEATHER_ALERT_COOLDOWN_HOURS)
                    ).exists():
                        created_alert = Alert.objects.create(
                            recipient=parent_user, child=child, alert_type='CONTEXTUAL_WEATHER', message=alert_message)
                        send_fcm_to_user(parent_user, title=push_title, body=alert_message, data={'alert_id': str(created_alert.id), 'type': 'weather_forecast_precipitation'})
                        logger.info(f"Sent precipitation forecast FCM alert to parent of {child.name}: {alert_message}")

                        channel_layer = get_channel_layer()
                        group_name = f'user_{parent_user.id}_notifications'
                        ws_message_payload = {
                            'type': 'contextual_weather_alert',
                            'alert_id': str(created_alert.id),
                            'child_id': str(child.id),
                            'child_name': child.name,
                            'message': alert_message,
                            'timestamp': created_alert.timestamp.isoformat(),
                            'event_summary': weather_desc
                        }
                        async_to_sync(channel_layer.group_send)(
                            group_name,
                            { "type": "send_notification", "message": ws_message_payload }
                        )
                        logger.info(f"Sent precipitation forecast WebSocket alert to parent of {child.name}: {alert_message}")
                        break
    logger.info("Finished periodic weather check.")
    return "Periodic weather check for children complete."

# --- Constants for Routine Learning ---
ROUTINE_LEARNING_DATA_DAYS = 30
SIGNIFICANT_PLACE_PROXIMITY_METERS = 150
MIN_TRIP_POINTS = 5  # Re-defined here for AnalyzeTripTask, ensure consistency or import from a common place
MIN_TRIPS_FOR_ROUTINE = 3

@shared_task(name="learn_child_routine_task")
def learn_child_routine_task(child_id):
    logger.info(f"Starting routine learning for child_id: {child_id}")
    try:
        child = get_object_or_404(Child, pk=child_id, is_active=True)
    except Child.DoesNotExist:
        logger.error(f"Child with id {child_id} not found or not active. Skipping routine learning.")
        return

    parent = child.parent
    home_zone = SafeZone.objects.filter(owner=parent, name__iexact="Home", is_active=True).first()
    school_zone = SafeZone.objects.filter(owner=parent, name__iexact="Lekol", is_active=True).first()

    if not home_zone or not school_zone:
        logger.info(f"Home or School SafeZone not defined/active for parent of child {child.name}. Cannot learn Home-School routines.")
        return

    end_date = timezone.now()
    start_date = end_date - timedelta(days=ROUTINE_LEARNING_DATA_DAYS)
    locations = LocationPoint.objects.filter(
        child=child, timestamp__gte=start_date, timestamp__lte=end_date
    ).order_by('timestamp')

    if locations.count() < MIN_TRIP_POINTS * MIN_TRIPS_FOR_ROUTINE:
        logger.info(f"Not enough location data for child {child.name} in the last {ROUTINE_LEARNING_DATA_DAYS} days.")
        return

    trips_home_to_school = []
    trips_school_to_home = []
    current_trip_points = []
    current_state = 'UNKNOWN'

    if locations:
        first_point = locations[0]
        if distance_in_meters(first_point.latitude, first_point.longitude, home_zone.latitude, home_zone.longitude) <= SIGNIFICANT_PLACE_PROXIMITY_METERS:
            current_state = 'AT_HOME'
        elif distance_in_meters(first_point.latitude, first_point.longitude, school_zone.latitude, school_zone.longitude) <= SIGNIFICANT_PLACE_PROXIMITY_METERS:
            current_state = 'AT_SCHOOL'

    for point in locations:
        at_home_now = distance_in_meters(point.latitude, point.longitude, home_zone.latitude, home_zone.longitude) <= SIGNIFICANT_PLACE_PROXIMITY_METERS
        at_school_now = distance_in_meters(point.latitude, point.longitude, school_zone.latitude, school_zone.longitude) <= SIGNIFICANT_PLACE_PROXIMITY_METERS

        if current_state == 'AT_HOME':
            if not at_home_now:
                current_state = 'IN_TRANSIT_FROM_HOME'
                current_trip_points = [point]
        elif current_state == 'AT_SCHOOL':
            if not at_school_now:
                current_state = 'IN_TRANSIT_FROM_SCHOOL'
                current_trip_points = [point]
        elif current_state == 'IN_TRANSIT_FROM_HOME':
            current_trip_points.append(point)
            if at_school_now:
                if len(current_trip_points) >= MIN_TRIP_POINTS:
                    trips_home_to_school.append(list(current_trip_points))
                current_trip_points = []
                current_state = 'AT_SCHOOL'
            elif at_home_now:
                current_trip_points = []
                current_state = 'AT_HOME'
        elif current_state == 'IN_TRANSIT_FROM_SCHOOL':
            current_trip_points.append(point)
            if at_home_now:
                if len(current_trip_points) >= MIN_TRIP_POINTS:
                    trips_school_to_home.append(list(current_trip_points))
                current_trip_points = []
                current_state = 'AT_HOME'
            elif at_school_now:
                current_trip_points = []
                current_state = 'AT_SCHOOL'
        elif current_state == 'UNKNOWN':
            if at_home_now: current_state = 'AT_HOME'
            elif at_school_now: current_state = 'AT_SCHOOL'

    if len(trips_home_to_school) >= MIN_TRIPS_FOR_ROUTINE:
        process_and_save_routine(child, trips_home_to_school, home_zone, school_zone, "Home to School")
    if len(trips_school_to_home) >= MIN_TRIPS_FOR_ROUTINE:
        process_and_save_routine(child, trips_school_to_home, school_zone, home_zone, "School to Home")

    logger.info(f"Finished routine learning for child_id: {child_id}")


def process_and_save_routine(child, trips, start_zone, end_zone, routine_type_name):
    logger.info(f"Processing {len(trips)} trips for {routine_type_name} for child {child.name}")

    days_of_week = Counter()
    start_times_seconds = []

    longest_trip_path_points = []
    if trips:
        trips.sort(key=len, reverse=True)
        longest_trip_path_points = [[float(p.latitude), float(p.longitude)] for p in trips[0]]

    for trip in trips:
        if not trip: continue
        days_of_week[trip[0].timestamp.weekday()] += 1
        start_time_obj = trip[0].timestamp.time()
        start_times_seconds.append(start_time_obj.hour * 3600 + start_time_obj.minute * 60 + start_time_obj.second)

    if not days_of_week:
        logger.info(f"No valid days of week for {routine_type_name} for child {child.name}")
        return

    common_days_list = [day for day, count in days_of_week.items() if count >= len(trips) * 0.3]
    common_days_str = ",".join(map(str, sorted(common_days_list)))

    if not start_times_seconds:
        logger.info(f"No start times for {routine_type_name} for child {child.name}")
        return

    min_start_seconds = min(start_times_seconds)
    max_start_seconds = max(start_times_seconds)

    avg_start_time_min_obj = time(min_start_seconds // 3600, (min_start_seconds % 3600) // 60, min_start_seconds % 60)
    avg_start_time_max_obj = time(max_start_seconds // 3600, (max_start_seconds % 3600) // 60, max_start_seconds % 60)

    routine_name_full = f"{routine_type_name} for {child.name}"
    defaults = {
        'start_location_name': start_zone.name,
        'start_latitude_approx': float(start_zone.latitude),
        'start_longitude_approx': float(start_zone.longitude),
        'end_location_name': end_zone.name,
        'end_latitude_approx': float(end_zone.latitude),
        'end_longitude_approx': float(end_zone.longitude),
        'typical_days_of_week': common_days_str,
        'typical_time_window_start_min': avg_start_time_min_obj,
        'typical_time_window_start_max': avg_start_time_max_obj,
        'route_path_approximation_json': json.dumps(longest_trip_path_points) if longest_trip_path_points else None,
        'confidence_score': len(trips) / (ROUTINE_LEARNING_DATA_DAYS * 0.5),
        'is_active': True,
        'last_calculated_at': timezone.now()
    }

    routine, created = LearnedRoutine.objects.update_or_create(
        child=child,
        name=routine_name_full,
        defaults=defaults
    )
    status_msg = "created" if created else "updated"
    logger.info(f"LearnedRoutine {routine.name} {status_msg} with {len(trips)} trips.")

# --- Constants for Anomaly Detection ---
PATH_DEVIATION_THRESHOLD_METERS = 500
TIME_DEVIATION_THRESHOLD_MINUTES = 30
# DURATION_DEVIATION_FACTOR = 1.5 # Not used yet as typical_duration is not learned
SIGNIFICANT_PLACE_PROXIMITY_FOR_TRIP_MATCH_METERS = 200

@shared_task(name="analyze_trip_task")
def analyze_trip_task(child_id, trip_points_data):
    """
    Analyzes a given trip for anomalies against learned routines.
    trip_points_data: list of dicts, e.g., [{'lat': ..., 'lon': ..., 'ts': 'isoformat_timestamp'}, ...]
    """
    logger.info(f"Starting trip analysis for child_id: {child_id}, {len(trip_points_data)} points")
    try:
        child = get_object_or_404(Child, pk=child_id, is_active=True)
    except Child.DoesNotExist:
        logger.error(f"Child with id {child_id} not found or not active. Skipping trip analysis.")
        return

    if not trip_points_data or len(trip_points_data) < MIN_TRIP_POINTS:
        logger.info(f"Trip data insufficient for analysis for child {child_id}.")
        return

    trip_path_coords = [[p['lat'], p['lon']] for p in trip_points_data]
    trip_start_time = timezone.datetime.fromisoformat(trip_points_data[0]['ts'])
    # trip_end_time = timezone.datetime.fromisoformat(trip_points_data[-1]['ts']) # Not used yet
    # trip_duration_minutes = (trip_end_time - trip_start_time).total_seconds() / 60 # Not used yet

    routines = LearnedRoutine.objects.filter(child=child, is_active=True)
    if not routines.exists():
        logger.info(f"No active learned routines for child {child_id} to compare against.")
        return

    anomalies_found = []
    matched_routine_name = "Unknown Routine" # Default

    for routine in routines:
        # 1. Match trip to routine
        dist_to_routine_start = distance_in_meters(
            trip_path_coords[0][0], trip_path_coords[0][1],
            routine.start_latitude_approx, routine.start_longitude_approx
        )
        dist_to_routine_end = distance_in_meters(
            trip_path_coords[-1][0], trip_path_coords[-1][1],
            routine.end_latitude_approx, routine.end_longitude_approx
        )

        if dist_to_routine_start > SIGNIFICANT_PLACE_PROXIMITY_FOR_TRIP_MATCH_METERS or \
           dist_to_routine_end > SIGNIFICANT_PLACE_PROXIMITY_FOR_TRIP_MATCH_METERS:
            continue

        trip_day_str = str(trip_start_time.weekday())
        if routine.typical_days_of_week and trip_day_str not in routine.typical_days_of_week.split(','):
            continue

        matched_routine_name = routine.name # Found a potentially matching routine

        # 2. Path Deviation
        if routine.route_path_approximation_json:
            try: # Add try-except for json.loads
                routine_path_coords = json.loads(routine.route_path_approximation_json)
                if routine_path_coords: # Ensure not empty list
                    avg_path_deviation = calculate_average_distance_to_path(trip_path_coords, routine_path_coords)
                    if avg_path_deviation > PATH_DEVIATION_THRESHOLD_METERS:
                        anomalies_found.append(f"Path deviation (avg {avg_path_deviation:.0f}m) from '{routine.name}'.")
            except json.JSONDecodeError:
                logger.error(f"Error decoding route_path_approximation_json for routine {routine.id}")

        # 3. Time Deviation
        trip_start_time_obj = trip_start_time.time()
        if routine.typical_time_window_start_min and routine.typical_time_window_start_max:
            # Convert model TimeFields to datetime.time for comparison if they aren't already
            routine_min_time = routine.typical_time_window_start_min
            routine_max_time = routine.typical_time_window_start_max

            if not (routine_min_time <= trip_start_time_obj <= routine_max_time):
                # Check if trip started significantly earlier or later than the window
                # Create datetime objects for comparison, using the trip's date
                min_datetime = timezone.make_aware(timezone.datetime.combine(trip_start_time.date(), routine_min_time))
                max_datetime = timezone.make_aware(timezone.datetime.combine(trip_start_time.date(), routine_max_time))

                # Ensure trip_start_time is also aware for correct comparison
                aware_trip_start_time = trip_start_time if timezone.is_aware(trip_start_time) else timezone.make_aware(trip_start_time)

                if (aware_trip_start_time - max_datetime).total_seconds() / 60 > TIME_DEVIATION_THRESHOLD_MINUTES or \
                   (min_datetime - aware_trip_start_time).total_seconds() / 60 > TIME_DEVIATION_THRESHOLD_MINUTES:
                    anomalies_found.append(f"Start time {trip_start_time_obj.strftime('%H:%M')} outside typical window ({routine_min_time.strftime('%H:%M')}-{routine_max_time.strftime('%H:%M')}) for '{routine.name}'.")

        if anomalies_found:
            break

    if anomalies_found:
        alert_message = f"Unusual activity detected for {child.name} regarding routine '{matched_routine_name}': " + " | ".join(anomalies_found)
        logger.warning(alert_message)

        if not Alert.objects.filter(
            recipient=child.parent, child=child, alert_type='UNUSUAL_ROUTE',
            timestamp__gte=timezone.now() - timedelta(hours=1)
        ).exists():
            created_alert = Alert.objects.create(
                recipient=child.parent, child=child, alert_type='UNUSUAL_ROUTE', message=alert_message)

            send_fcm_to_user(child.parent, title=f"Unusual Activity Detected for {child.name}", body=alert_message, data={'alert_id': str(created_alert.id), 'type': 'unusual_route'})
            logger.info(f"Sent UNUSUAL_ROUTE alert for child {child.id}.")
        else:
            logger.info(f"UNUSUAL_ROUTE alert for child {child.id} on cooldown.")
    else:
        logger.info(f"Trip for child {child.id} analyzed, no significant anomalies found against routines.")

    return f"Trip analysis complete for child {child.id}. Anomalies: {len(anomalies_found)}"

@shared_task(name="schedule_routine_learning_for_all_active_children")
def schedule_routine_learning_for_all_active_children():
    logger.info("Starting scheduler task: Queuing routine learning for all active children.")
    active_children = Child.objects.filter(is_active=True)
    count = 0
    for child in active_children:
        learn_child_routine_task.delay(child.id)
        count += 1
    logger.info(f"Queued routine learning for {count} active children.")
    return f"Queued routine learning for {count} children."
