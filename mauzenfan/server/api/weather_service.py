# mauzenfan/server/api/weather_service.py
from pyowm import OWM
from pyowm.utils import config as owm_config
from pyowm.utils import timestamps as owm_timestamps
# from pyowm.weatherapi25.one_call import OneCall # OneCall might be directly on mgr or OWM object in newer pyowm
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

# --- OWM Client Initialization ---
OWM_API_KEY = getattr(settings, '63fbe66f4b681cac9b433aa3e86b7622', None)
owm_client = None

if OWM_API_KEY:
    try:
        # pyowm config can be customized if needed
        # default_config = owm_config.get_default_config()
        # default_config['language'] = 'en'
        owm_client = OWM(OWM_API_KEY)
        logger.info("OpenWeatherMap client initialized successfully.")
    except Exception as e:
        logger.error(f"Error initializing OpenWeatherMap client: {e}", exc_info=True)
        owm_client = None
else:
    logger.warning("WEATHER_API_KEY not found in settings. Weather service will not function.")

def get_weather_forecast(lat, lon):
    """
    Fetches weather forecast using OWM's One Call API for a given lat/lon.
    Parses relevant information (e.g., imminent rain, significant weather changes).
    Returns a simplified dictionary or None if an error occurs or service not available.
    """
    if not owm_client:
        logger.error("OWM client not initialized. Cannot fetch weather.")
        return None

    try:
        mgr = owm_client.weather_manager()
        # Note: The exact method for OneCall API 3.0 might differ slightly based on pyowm version.
        # This example aims to get hourly and daily forecasts, and alerts.
        one_call_data = mgr.one_call(lat=float(lat), lon=float(lon), exclude='minutely,current')

        parsed_weather = {
            'hourly_forecast': [],
            'daily_forecast': [], # Added daily forecast for broader utility
            'alerts': []
        }

        if one_call_data:
            # Hourly forecast (e.g., for the next 12 hours)
            if one_call_data.forecast_hourly:
                for i, hourly_data in enumerate(one_call_data.forecast_hourly):
                    if i >= 12:
                        break
                    parsed_weather['hourly_forecast'].append({
                        'time': hourly_data.reference_time('iso'),
                        'temp': hourly_data.temperature('celsius').get('temp'),
                        'feels_like': hourly_data.temperature('celsius').get('feels_like'),
                        'humidity': hourly_data.humidity,
                        'wind_speed': hourly_data.wind().get('speed'),
                        'precipitation_probability': hourly_data.precipitation_probability,
                        'weather_code': hourly_data.weather_code,
                        'detailed_status': hourly_data.detailed_status,
                        'rain_volume_1h': hourly_data.rain.get('1h', 0) if hourly_data.rain else 0,
                        'snow_volume_1h': hourly_data.snow.get('1h', 0) if hourly_data.snow else 0,
                    })

            # Daily forecast (e.g., for the next 7 days)
            if one_call_data.forecast_daily:
                for daily_data in one_call_data.forecast_daily: # Typically 7 or 8 days
                    parsed_weather['daily_forecast'].append({
                        'date': daily_data.reference_time('iso').split('T')[0], # Just the date part
                        'temp_day': daily_data.temperature('celsius').get('day'),
                        'temp_min': daily_data.temperature('celsius').get('min'),
                        'temp_max': daily_data.temperature('celsius').get('max'),
                        'humidity': daily_data.humidity,
                        'precipitation_probability': daily_data.precipitation_probability,
                        'weather_code': daily_data.weather_code,
                        'detailed_status': daily_data.detailed_status,
                        'sunrise_time': daily_data.sunrise_time('iso'),
                        'sunset_time': daily_data.sunset_time('iso'),
                    })

            # National weather alerts
            if one_call_data.national_weather_alerts:
                for alert_data in one_call_data.national_weather_alerts:
                    parsed_weather['alerts'].append({
                        'sender_name': alert_data.sender_name,
                        'event': alert_data.event_name, # Using event_name as per typical pyowm attribute
                        'start_time': alert_data.start_time('iso'),
                        'end_time': alert_data.end_time('iso'),
                        'description': alert_data.description,
                        'tags': alert_data.tags if hasattr(alert_data, 'tags') else [] # Some alerts have tags
                    })

            return parsed_weather

    except Exception as e:
        logger.error(f"Error fetching or parsing weather data for lat={lat}, lon={lon}: {e}", exc_info=True)
        return None

# Example Test (conceptual, not run by subtask)
# if __name__ == '__main__':
#     # This needs Django settings to be configured if run standalone,
#     # or OWM_API_KEY set directly for simple testing.
#     # import django; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'main_project.settings'); settings.configure(DEBUG=True, WEATHER_API_KEY="YOUR_KEY_HERE"); django.setup()
#     if OWM_API_KEY:
#         test_lat, test_lon = -20.1609, 57.5012
#         weather = get_weather_forecast(test_lat, test_lon)
#         if weather:
#             print("Weather Forecast Fetched:")
#             import json
#             print(json.dumps(weather, indent=2))
#         else:
#             print("Could not fetch weather.")
#     else:
#         print("Skipping weather test as OWM_API_KEY is not set.")
