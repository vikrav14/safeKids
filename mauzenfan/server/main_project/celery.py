# mauzenfan/server/main_project/celery.py
from __future__ import absolute_import, unicode_literals
import os
from celery import Celery
from django.conf import settings # Import settings to use CELERY_TIMEZONE

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'main_project.settings')

app = Celery('main_project')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Set the Celery app's timezone from Django settings
# This ensures that Celery tasks and schedules use the same timezone as the Django project.
# The CELERY_TIMEZONE setting should be defined in your settings.py
app.conf.timezone = settings.TIME_ZONE # Use Django's TIME_ZONE by default

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
