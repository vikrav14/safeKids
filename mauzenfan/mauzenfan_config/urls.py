"""
URL configuration for main_project project.
"""
from django.contrib import admin
from django.urls import path, include
# Corrected import with proper class names
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

schema_urlpatterns = [
    # Corrected class name: SpectacularAPIView
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    # Optional UI:
    path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

urlpatterns = schema_urlpatterns + [
    path('admin/', admin.site.urls),
    # Fixed include path
    path('api/', include('apps.api_app.urls')),
]