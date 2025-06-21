from django.apps import AppConfig

class api_app.Config(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api.'

    def ready(self):
        # Add this line back, but corrected
        from . import signals 
