# mauzenfan/server/api/tasks.py
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import logging

from .models import Child, Alert, LocationPoint
from .weather_service import get_weather_forecast
from .fcm_service import send_fcm_to_user
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)

# --- Constants for Weather Alerts ---
WEATHER_ALERT_COOLDOWN_HOURS = 3
MIN_PRECIPITATION_PROBABILITY_THRESHOLD = 0.6 # 60%

@shared_task(name="check_weather_for_children_alerts")
def check_weather_for_children_alerts():
    logger.info("Starting periodic weather check for children...")
    # Ensure Child model has 'is_active' or adjust filter accordingly
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
            else: # Child has last_seen_at but no LocationPoint objects (unlikely but possible)
                 logger.info(f"Child {child.name} has last_seen_at but no location points. Skipping weather check.")
                 continue
        else: # No recent location update for the child
            logger.info(f"No recent location for child {child.name} (last_seen_at: {child.last_seen_at}). Skipping weather check.")
            continue

        weather_data = get_weather_forecast(location_to_check["lat"], location_to_check["lon"])

        if not weather_data:
            logger.warning(f"Could not retrieve weather data for {location_name}. Skipping child {child.name}.")
            continue

        parent_user = child.parent

        # 1. Check National Weather Alerts from API
        if weather_data.get('alerts'):
            for national_alert in weather_data['alerts']:
                alert_event_name = national_alert.get('event', 'Weather Alert')
                alert_description = national_alert.get('description', 'Important weather information.')
                alert_message = f"Weather Alert for {location_name}: {alert_event_name}. {alert_description}"

                # Cooldown check for this specific national alert event based on message content
                if not Alert.objects.filter(
                    recipient=parent_user,
                    child=child,
                    alert_type='CONTEXTUAL_WEATHER',
                    message__icontains=alert_event_name, # Check if this specific event was already sent
                    timestamp__gte=timezone.now() - timedelta(hours=WEATHER_ALERT_COOLDOWN_HOURS * 2) # Longer cooldown for national
                ).exists():
                    created_alert = Alert.objects.create(
                        recipient=parent_user, child=child, alert_type='CONTEXTUAL_WEATHER', message=alert_message)
                    send_fcm_to_user(parent_user, title=f"Weather Alert: {alert_event_name}", body=alert_message, data={'alert_id': str(created_alert.id), 'type': 'weather_national'})
                    logger.info(f"Sent national weather alert FCM to parent of {child.name}: {alert_event_name}")

                    # Send WebSocket notification for national weather alert
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
                        {
                            "type": "send_notification",
                            "message": ws_message_payload
                        }
                    )
                    logger.info(f"Sent national weather alert WebSocket to parent of {child.name}: {alert_event_name}")

        # 2. Check Hourly Forecast for Imminent Precipitation
        if weather_data.get('hourly_forecast'):
            for hourly in weather_data['hourly_forecast'][:3]: # Check next 3 hours
                precip_prob = hourly.get('precipitation_probability', 0)
                if precip_prob >= MIN_PRECIPITATION_PROBABILITY_THRESHOLD:
                    weather_desc = hourly.get('detailed_status', 'precipitation')
                    alert_time_obj = timezone.datetime.fromisoformat(hourly['time'].replace('Z','+00:00'))
                    alert_time_str = alert_time_obj.strftime('%I:%M %p') # Removed timezone for brevity, date is implied

                    base_message = f"{weather_desc.capitalize()} likely near {location_name} around {alert_time_str} (Prob: {int(precip_prob*100)}%)."
                    suggestion = ""
                    alert_category = "Weather Update"

                    if "rain" in weather_desc.lower():
                        suggestion = " Consider taking an umbrella!"
                    elif "snow" in weather_desc.lower():
                        suggestion = " Dress warmly!"
                    elif "thunderstorm" in weather_desc.lower():
                        suggestion = " Stay safe and be aware of lightning."
                        alert_category = "Weather Alert"

                    alert_message = f"{alert_category}: {base_message}{suggestion}"

                    # Determine push_title based on severity
                    if "thunderstorm" in weather_desc.lower():
                        push_title = f"Thunderstorm Alert for {child.name}"
                    elif "rain" in weather_desc.lower() or "snow" in weather_desc.lower():
                        push_title = f"{weather_desc.capitalize()} Forecast for {child.name}"
                    else:
                        push_title = f"Weather Update for {child.name}"

                    # Cooldown check for "precipitation" type alerts
                    if not Alert.objects.filter(
                        recipient=parent_user,
                        child=child,
                        alert_type='CONTEXTUAL_WEATHER',
                        # More specific cooldown: check if a similar message (ignoring suggestion) was sent recently
                        message__startswith=f"{alert_category}: {base_message}",
                        timestamp__gte=timezone.now() - timedelta(hours=WEATHER_ALERT_COOLDOWN_HOURS)
                    ).exists():
                        created_alert = Alert.objects.create(
                            recipient=parent_user, child=child, alert_type='CONTEXTUAL_WEATHER', message=alert_message)

                        send_fcm_to_user(parent_user, title=push_title, body=alert_message, data={'alert_id': str(created_alert.id), 'type': 'weather_forecast_precipitation'})
                        logger.info(f"Sent precipitation forecast FCM alert to parent of {child.name}: {alert_message}")

                        # Send WebSocket notification for precipitation forecast
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
                            {
                                "type": "send_notification",
                                "message": ws_message_payload
                            }
                        )
                        logger.info(f"Sent precipitation forecast WebSocket alert to parent of {child.name}: {alert_message}")
                        break

    logger.info("Finished periodic weather check.")
    return "Periodic weather check for children complete."
