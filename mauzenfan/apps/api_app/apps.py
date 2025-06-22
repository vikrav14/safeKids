# apps/api_app/apps.py
from django.apps import AppConfig

# Change to match exactly what Django expects
class ApiAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.api_app'