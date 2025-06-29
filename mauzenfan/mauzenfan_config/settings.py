import os
from pathlib import Path
from datetime import timedelta

# Weather API Configuration
WEATHER_api_app_KEY = os.environ.get('WEATHER_api_app_KEY', None)
WEATHER_CACHE_TIMEOUT = 1800  # 30 minutes

# Build paths inside the project like this: BASE_DIR / 'subdir'.
# Assuming manage.py is in the parent directory of the one containing this settings file's parent directory.
# If settings.py is at /project_root/config_dir/settings.py, then BASE_DIR is /project_root/
# Adjust if your structure is different (e.g., if manage.py is at the same level as the 'mauzenfan' directory from logs)
BASE_DIR = Path(__file__).resolve().parent.parent 
# Original was: BASE_DIR = Path(__file__).resolve().parent.parent.parent 

# Define ALLOWED_HOSTS first
ALLOWED_HOSTS = ['localhost', '127.0.0.1']

# Add Render hostname if available
RENDER_EXTERNAL_HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

# Add production domain
ALLOWED_HOSTS.append('safekids-y3s2.onrender.com')

# Security settings
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-$w-i1pgmtf+9*)7=lul@6nv4#y6dl!^ajs+#f&0^9ck4z#&1ct')
DEBUG = os.environ.get('DJANGO_DEBUG', 'False') == 'True'  # Default to False in production

# =================================================================
# ==                  CORS & SECURITY CONFIGURATION              ==
# =================================================================
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_CREDENTIALS = True

CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    # "https://safekids-y3s2.onrender.com", # Usually not needed for self-origin, but harmless
                                         # More relevant if you had a different frontend domain.
]

CSRF_TRUSTED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://safekids-y3s2.onrender.com", # Trust POSTs from your own domain
]

CORS_ALLOW_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]

CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]

# Cookie settings for cross-site requests (important if frontend and backend are different subdomains/ports)
SESSION_COOKIE_SAMESITE = 'None' if not DEBUG else 'Lax'
SESSION_COOKIE_SECURE = not DEBUG # Ensure True in production (when DEBUG=False)
CSRF_COOKIE_SAMESITE = 'None' if not DEBUG else 'Lax' # For CSRF cookie if needed cross-site
CSRF_COOKIE_SECURE = not DEBUG # Ensure True in production

# Settings for running behind a proxy like Render
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# =================================================================

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'whitenoise.runserver_nostatic', # WhiteNoise (should be high, but after staticfiles if it depends on it. Check docs for specific placement)
    'django.contrib.staticfiles',
    'channels',
    'rest_framework',
    'rest_framework_simplejwt',  # JWT authentication
    'rest_framework.authtoken',
    'djoser',  # User management
    'apps.api_app',  # Fixed app reference
    'django_celery_beat',
    'corsheaders',
    'drf_spectacular',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware', # Should be as high as possible
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware', # After SecurityMiddleware, before most others
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'mauzenfan_config.urls' # Ensure 'mauzenfan_config' is the correct name of your project's config folder
WSGI_APPLICATION = 'mauzenfan_config.wsgi.application'
ASGI_APPLICATION = 'mauzenfan_config.asgi.application'

# Frontend Configuration (Review if Django is actually serving your frontend)
# If frontend is deployed separately, these might not be needed or cause issues if paths are wrong.
FRONTEND_DIR = BASE_DIR / 'frontend'  # Path to your frontend directory
FRONTEND_BUILD_DIR = FRONTEND_DIR / 'build'  # Path to your frontend build

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        # Consider removing FRONTEND_BUILD_DIR if Django doesn't serve index.html for a SPA
        # or if the path is incorrect (causes warnings if dir doesn't exist).
        'DIRS': [FRONTEND_BUILD_DIR], 
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# Static files configuration
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles' # For collectstatic

# Where Django will look for additional static files during development
# This path also causes warnings if it doesn't exist.
STATICFILES_DIRS = [
    FRONTEND_BUILD_DIR / 'static',  # Frontend static files
]

# WhiteNoise configuration
# Use 'whitenoise.storage.CompressedManifestStaticFilesStorage' or 'whitenoise.storage.CompressedStaticFilesStorage'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'mediafiles'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Database
import dj_database_url
DATABASES = {
    'default': dj_database_url.config(
        default=os.environ.get('DATABASE_URL'),
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Channels/Redis
REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [(REDIS_HOST, REDIS_PORT)]},
    }
}

if not os.environ.get('REDIS_HOST'):
    CHANNEL_LAYERS['default'] = {'BACKEND': 'channels.layers.InMemoryChannelLayer'}

# Celery
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

# FCM
FCM_SERVICE_ACCOUNT_KEY_PATH = os.environ.get('FCM_CREDENTIAL_PATH', None)

# App Settings
DEFAULT_ETA_SPEED_KMH = 30

# Django REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',  # JWT authentication
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10
}

# Simple JWT Configuration
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}

# Djoser Configuration
DJOSER = {
    'SERIALIZERS': {
        'user_create': 'apps.api_app.serializers.UserCreateSerializer',
        'user': 'apps.api_app.serializers.UserSerializer',
        'current_user': 'apps.api_app.serializers.UserSerializer',
    },
    'PERMISSIONS': {
        'user_list': ['rest_framework.permissions.IsAdminUser'],
        'user': ['rest_framework.permissions.IsAuthenticated'],
    },
    'HIDE_USERS': False,
}

# DRF Spectacular
SPECTACULAR_SETTINGS = {
    'TITLE': 'SafeKids API',
    'DESCRIPTION': 'API for the SafeKids Child Safety Application',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'SCHEMA_PATH_PREFIX': r'/api/',
}

# Production settings specific block
if not DEBUG:
    # Security headers
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    
    # HTTPS settings (SECURE_SSL_REDIRECT is crucial)
    SECURE_SSL_REDIRECT = True
    # SESSION_COOKIE_SECURE and CSRF_COOKIE_SECURE are already set based on DEBUG status above

    # HSTS Settings (Optional but recommended for production once everything is stable)
    # SECURE_HSTS_SECONDS = 31536000  # 1 year
    # SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    # SECURE_HSTS_PRELOAD = True

# Ensure these cookie settings are explicitly handled for production (not DEBUG)
# These were already set using 'not DEBUG', which is good.
# SESSION_COOKIE_SECURE = not DEBUG
# CSRF_COOKIE_SECURE = not DEBUG