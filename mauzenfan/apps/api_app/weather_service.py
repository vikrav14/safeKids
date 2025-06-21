from pyowm import OWM
import logging
from django.conf import settings
from django.core.cache import cache  # For caching
import os  # For environment variables if needed

logger = logging.getLogger(__name__)

# --- OWM Client Initialization ---
OWM_API_KEY = getattr(settings, 'WEATHER_API_KEY', None)
owm_client = None

if OWM_API_KEY:
    try:
        # Configure timeout settings
        config_dict = {
            'connection': {
                'timeout': 10  # 10-second timeout for all requests
            }
        }
        owm_client = OWM(OWM_API_KEY, config=config_dict)
        logger.info("OpenWeatherMap client initialized successfully with timeout settings.")
    except Exception as e:
        logger.error(f"Error initializing OpenWeatherMap client: {e}", exc_info=True)
        owm_client = None
else:
    logger.warning("WEATHER_API_KEY not found in settings. Weather service will not function.")

def get_weather_forecast(lat, lon):
    """
    Fetches weather forecast using OWM's One Call API for a given lat/lon.
    Includes coordinate validation, API timeout, and caching.
    """
    # Validate coordinates
    try:
        # Convert to floats and validate
        lat = float(lat)
        lon = float(lon)
        
        # Validate coordinate ranges
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            logger.error(f"Coordinates out of range: lat={lat}, lon={lon}")
            return None
    except (TypeError, ValueError):
        logger.error(f"Invalid coordinate values: lat={lat}, lon={lon}")
        return None
    
    # Check cache first
    cache_key = f"weather_{lat}_{lon}"
    cached_data = cache.get(cache_key)
    if cached_data:
        logger.info(f"Returning cached weather data for {lat},{lon}")
        return cached_data
    
    # Check client initialization
    if not owm_client:
        logger.error("OWM client not initialized. Cannot fetch weather.")
        return None

    try:
        mgr = owm_client.weather_manager()
        
        # Get weather data with timeout
        one_call_data = mgr.one_call(
            lat=lat,
            lon=lon,
            exclude='minutely,current',
            timeout=10  # 10-second timeout for this specific call
        )
        
        parsed_weather = {'hourly_forecast': [], 'daily_forecast': [], 'alerts': []}

        if one_call_data:
            # Hourly forecast (next 12 hours)
            if one_call_data.forecast_hourly:
                for hourly_data in one_call_data.forecast_hourly[:12]:  # Limit to 12 hours
                    parsed_weather['hourly_forecast'].append({
                        'time': hourly_data.reference_time('iso'),
                        'temp': hourly_data.temperature('celsius').get('temp'),
                        'feels_like': hourly_data.temperature('celsius').get('feels_like'),
                        'humidity': hourly_data.humidity,
                        'wind_speed': hourly_data.wind().get('speed'),
                        'precipitation_probability': hourly_data.precipitation_probability,
                        'weather_code': hourly_data.weather_code,
                        'detailed_status': hourly_data.detailed_status,
                        'rain_1h': hourly_data.rain.get('1h', 0) if hourly_data.rain else 0,
                        'snow_1h': hourly_data.snow.get('1h', 0) if hourly_data.snow else 0,
                    })

            # Daily forecast (next 7 days)
            if one_call_data.forecast_daily:
                for daily_data in one_call_data.forecast_daily:
                    parsed_weather['daily_forecast'].append({
                        'date': daily_data.reference_time('iso').split('T')[0],
                        'temp_day': daily_data.temperature('celsius').get('day'),
                        'temp_min': daily_data.temperature('celsius').get('min'),
                        'temp_max': daily_data.temperature('celsius').get('max'),
                        'humidity': daily_data.humidity,
                        'precipitation_probability': daily_data.precipitation_probability,
                        'weather_code': daily_data.weather_code,
                        'detailed_status': daily_data.detailed_status,
                        'sunrise': daily_data.sunrise_time('iso'),
                        'sunset': daily_data.sunset_time('iso'),
                    })

            # Weather alerts
            if one_call_data.national_weather_alerts:
                for alert_data in one_call_data.national_weather_alerts:
                    parsed_weather['alerts'].append({
                        'sender': alert_data.sender_name,
                        'event': getattr(alert_data, 'event_name', 'Alert'),
                        'start': alert_data.start_time('iso'),
                        'end': alert_data.end_time('iso'),
                        'description': alert_data.description,
                    })
        
        # Cache the result for 15 minutes if we have data
        if parsed_weather.get('hourly_forecast') or parsed_weather.get('daily_forecast'):
            cache_timeout = getattr(settings, 'WEATHER_CACHE_TIMEOUT', 900)  # Default 15 minutes
            cache.set(cache_key, parsed_weather, cache_timeout)
            logger.info(f"Cached weather data for {lat},{lon} for {cache_timeout} seconds")
        
        return parsed_weather

    except Exception as e:
        logger.error(f"Error fetching weather for lat={lat}, lon={lon}: {e}", exc_info=True)
        return None