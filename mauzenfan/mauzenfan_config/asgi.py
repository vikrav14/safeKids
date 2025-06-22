import os
import sys
from pathlib import Path
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

# Calculate the base directory of your Django project
BASE_DIR = Path(__file__).resolve().parent.parent

# Add project directory to Python path
sys.path.append(str(BASE_DIR))

# Set default settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mauzenfan_config.settings')

# Initialize Django application
django_application = get_asgi_application()

# Import routing AFTER setting up path and Django
from apps.api_app import routing  # Updated import path

application = ProtocolTypeRouter({
    "http": django_application,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            routing.websocket_urlpatterns
        )
    ),
})