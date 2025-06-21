from django.apps import AppConfig

class Api_appConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.api_app'

    def ready(self):
        # Add this line back, but corrected
        from . import signals 
