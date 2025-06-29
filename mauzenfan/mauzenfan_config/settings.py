"""
Django settings for main_project project.
"""
import os
from pathlib import Path

# Weather API Configuration
WEATHER_api_app_KEY = os.environ.get('WEATHER_api_app_KEY', None)
WEATHER_CACHE_TIMEOUT = 1800  # 30 minutes

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # Adjust based on actual location

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
CSRF_TRUSTED_ORIGINS = os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS', 'http://localhost:8000 http://127.0.0.1:8000').split()

# Add frontend URL to CSRF trusted origins
CSRF_TRUSTED_ORIGINS.append('https://safekids-y3s2.onrender.com')

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'channels',
    'rest_framework',
    'rest_framework.authtoken',
    'apps.api_app',  # Fixed app reference
    'django_celery_beat',
    'corsheaders',
    'drf_spectacular',
    'whitenoise.runserver_nostatic',  # Add WhiteNoise
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',           # <<< MOVED HERE: CORS Middleware
    'whitenoise.middleware.WhiteNoiseMiddleware',      # WhiteNoise middleware
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'mauzenfan_config.urls'
WSGI_APPLICATION = 'mauzenfan_config.wsgi.application'
ASGI_APPLICATION = 'mauzenfan_config.asgi.application'

# Frontend Configuration
FRONTEND_DIR = BASE_DIR / 'frontend'  # Path to your frontend directory
FRONTEND_BUILD_DIR = FRONTEND_DIR / 'build'  # Path to your frontend build

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [FRONTEND_BUILD_DIR],  # Point to your frontend build
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
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Where Django will look for additional static files
STATICFILES_DIRS = [
    FRONTEND_BUILD_DIR / 'static',  # Frontend static files
]

# WhiteNoise configuration
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

# =================================================================
# ==                  CORS CONFIGURATION                         ==
# =================================================================
# A list of origins that are authorized to make cross-site HTTP requests.
# Add your local frontend development URL and your production URL here.
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",      # Your local React/Vue/Svelte frontend
    "http://127.0.0.1:3000",
    "https://safekids-y3s2.onrender.com", # Your production frontend
]

# If True, cookies may be included in cross-domain requests.
CORS_ALLOW_CREDENTIALS = True
# =================================================================


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
        'rest_framework.authentication.TokenAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',  # Fixed schema class
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10
}

# DRF Spectacular
SPECTACULAR_SETTINGS = {
    'TITLE': 'MauZenfan API',
    'DESCRIPTION': 'API for the MauZenfan Family Safety Application',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

# Production settings
if not DEBUG:
    # Security headers
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    
    # HTTPS settings
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
