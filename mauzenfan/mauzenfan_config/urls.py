# mauzenfan_config/urls.py
from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from django.http import HttpResponse  # Add this for health check

# Add this view for health check
def health_check_view(request):
    return HttpResponse("SafeKids API is running", status=200)

# URL patterns for API documentation
schema_urlpatterns = [
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

urlpatterns = [
    # Health check endpoints
    path('', health_check_view, name='root-health-check'),
    path('health-check/', health_check_view, name='health-check'),
    
    # API documentation
    path('api/', include(schema_urlpatterns)),
    
    # Admin interface
    path('admin/', admin.site.urls),
    
    # Your app endpoints
    path('api/', include('apps.api_app.urls')),
]