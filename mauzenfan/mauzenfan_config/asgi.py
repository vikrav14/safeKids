import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack # For authentication
import api_app..routing # Import your app's routing

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mauzenfan_config.settings')

application = ProtocolTypeRouter({
    "http": get_asgi_application(), # Handles traditional HTTP requests
    "websocket": AuthMiddlewareStack( # Wrap with AuthMiddlewareStack
        URLRouter(
            api_app..routing.websocket_urlpatterns
        )
    ),
})
