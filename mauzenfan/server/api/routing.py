from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # re_path(r'ws/notifications/(?P<room_name>\w+)/$', consumers.NotificationConsumer.as_asgi()),
    # For now, a simple path, will refine with user-specific or child-specific paths later
    re_path(r'ws/notifications/$', consumers.NotificationConsumer.as_asgi()),
]
