from pyowm import OWM
import logging
from django.conf import settings
from django.core.cache import cache
import os

logger = logging.getLogger(__name__)

# --- OWM Client Initialization ---
owm_client = None

# Detailed environment debugging
def log_environment_debug():
    """Log detailed environment information for troubleshooting"""
    logger.debug("===== ENVIRONMENT DEBUG INFORMATION =====")
    
    # Check all possible sources
    from_settings = getattr(settings, 'WEATHER_api_app_KEY', None)
    from_env = os.environ.get('WEATHER_api_app_KEY')
    from_env_alt = os.environ.get('WEATHER_API_KEY')  # Common alternative
    
    logger.debug(f"Key from settings: {'Present' if from_settings else 'Missing'}")
    logger.debug(f"Key from ENV['WEATHER_api_app_KEY']: {'Present' if from_env else 'Missing'}")
    logger.debug(f"Key from ENV['WEATHER_API_KEY']: {'Present' if from_env_alt else 'Missing'}")
    
    # Log all environment variables (mask sensitive values)
    logger.debug("Environment variables:")
    for key, value in os.environ.items():
        if 'KEY' in key or 'SECRET' in key or 'PASSWORD' in key:
            logger.debug(f"  {key}: {'*' * 8}{value[-3:] if value else ''}")
        else:
            logger.debug(f"  {key}: {value}")
    
    logger.debug("========================================")

# Try to get API key from multiple sources
api_key_sources = [
    getattr(settings, 'WEATHER_api_app_KEY', None),
    os.environ.get('WEATHER_api_app_KEY'),
    os.environ.get('WEATHER_API_KEY'),  # Common alternative naming
    os.environ.get('OPENWEATHER_API_KEY')  # Another common pattern
]

OWM_api_app_KEY = None
source_name = ""

for candidate in api_key_sources:
    if candidate:
        OWM_api_app_KEY = candidate
        # Identify source for logging
        if candidate == api_key_sources[0]:
            source_name = "Django settings"
        elif candidate == api_key_sources[1]:
            source_name = "ENV['WEATHER_api_app_KEY']"
        elif candidate == api_key_sources[2]:
            source_name = "ENV['WEATHER_API_KEY']"
        else:
            source_name = "ENV['OPENWEATHER_API_KEY']"
        break

if OWM_api_app_KEY:
    try:
        config_dict = {
            'connection': {
                'timeout': 10
            }
        }
        owm_client = OWM(OWM_api_app_KEY, config=config_dict)
        logger.info(f"OpenWeatherMap client initialized successfully (source: {source_name})")
    except Exception as e:
        logger.error(f"Error initializing OpenWeatherMap client: {e}", exc_info=True)
        owm_client = None
else:
    log_environment_debug()
    logger.warning("Weather API key not found in any source. Weather service will not function.")

def get_weather_forecast(lat, lon):
    """
    Fetches weather forecast using OWM's One Call API for a given lat/lon.
    Includes coordinate validation, API timeout, and caching.
    """
    # Validate coordinates
    try:
        lat = float(lat)
        lon = float(lon)
        
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            logger.error(f"Coordinates out of range: lat={lat}, lon={lon}")
            return {
                'error': 'Invalid coordinates',
                'message': "Latitude must be between -90 and 90, longitude between -180 and 180"
            }
    except (TypeError, ValueError):
        logger.error(f"Invalid coordinate values: lat={lat}, lon={lon}")
        return {
            'error': 'Invalid coordinates',
            'message': 'Latitude and longitude must be valid numbers'
        }
    
    # Check cache first
    cache_key = f"weather_{lat}_{lon}"
    cached_data = cache.get(cache_key)
    if cached_data:
        logger.info(f"Returning cached weather data for {lat},{lon}")
        return cached_data
    
    # Check client initialization
    if not owm_client:
        logger.error("OWM client not initialized. Cannot fetch weather.")
        return {
            'error': 'Service unavailable',
            'message': 'Weather service is not configured properly. ' +
                       'Check server logs for initialization errors.'
        }

    try:
        mgr = owm_client.weather_manager()
        one_call_data = mgr.one_call(
            lat=lat,
            lon=lon,
            exclude='minutely,current',
            timeout=10
        )
        
        parsed_weather = {
            'hourly_forecast': [], 
            'daily_forecast': [], 
            'alerts': [],
            'coordinates': {'lat': lat, 'lon': lon}
        }

        if one_call_data:
            # Hourly forecast
            if hasattr(one_call_data, 'forecast_hourly') and one_call_data.forecast_hourly:
                for hourly_data in one_call_data.forecast_hourly[:12]:
                    parsed_weather['hourly_forecast'].append({
                        'time': hourly_data.reference_time('iso'),
                        'temp': hourly_data.temperature('celsius').get('temp'),
                        'feels_like': hourly_data.temperature('celsius').get('feels_like'),
                        'humidity': hourly_data.humidity,
                        'wind_speed': hourly_data.wind().get('speed') if hourly_data.wind() else 0,
                        'precipitation_probability': getattr(hourly_data, 'precipitation_probability', None),
                        'weather_code': hourly_data.weather_code,
                        'detailed_status': hourly_data.detailed_status,
                        'rain_1h': hourly_data.rain.get('1h', 0) if hourly_data.rain else 0,
                        'snow_1h': hourly_data.snow.get('1h', 0) if hourly_data.snow else 0,
                    })

            # Daily forecast
            if hasattr(one_call_data, 'forecast_daily') and one_call_data.forecast_daily:
                for daily_data in one_call_data.forecast_daily:
                    parsed_weather['daily_forecast'].append({
                        'date': daily_data.reference_time('iso').split('T')[0],
                        'temp_day': daily_data.temperature('celsius').get('day'),
                        'temp_min': daily_data.temperature('celsius').get('min'),
                        'temp_max': daily_data.temperature('celsius').get('max'),
                        'humidity': daily_data.humidity,
                        'precipitation_probability': getattr(daily_data, 'precipitation_probability', None),
                        'weather_code': daily_data.weather_code,
                        'detailed_status': daily_data.detailed_status,
                        'sunrise': daily_data.sunrise_time('iso'),
                        'sunset': daily_data.sunset_time('iso'),
                    })

            # Weather alerts
            if hasattr(one_call_data, 'national_weather_alerts') and one_call_data.national_weather_alerts:
                for alert_data in one_call_data.national_weather_alerts:
                    parsed_weather['alerts'].append({
                        'sender': alert_data.sender_name,
                        'event': getattr(alert_data, 'event_name', 'Alert'),
                        'start': alert_data.start_time('iso'),
                        'end': alert_data.end_time('iso'),
                        'description': alert_data.description,
                    })
        else:
            logger.warning(f"No weather data returned for coordinates: {lat},{lon}")
            return {
                'error': 'No data',
                'message': 'Weather service returned no data for these coordinates'
            }
        
        # Cache the result
        if parsed_weather.get('hourly_forecast') or parsed_weather.get('daily_forecast'):
            cache_timeout = getattr(settings, 'WEATHER_CACHE_TIMEOUT', 900)
            cache.set(cache_key, parsed_weather, cache_timeout)
            logger.info(f"Cached weather data for {lat},{lon} for {cache_timeout} seconds")
        
        return parsed_weather

    except Exception as e:
        logger.error(f"Error fetching weather for lat={lat}, lon={lon}: {e}", exc_info=True)
        return {
            'error': 'Service error',
            'message': f'Failed to fetch weather data: {str(e)}'
        }