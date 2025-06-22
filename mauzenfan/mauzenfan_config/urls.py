from django.urls import path, re_path, include
from django.views.generic import TemplateView
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin

# Import your actual view functions
from apps.api_app.views import health_check, root_health_check

urlpatterns = [
    # Root health check (homepage)
    path('', root_health_check, name='root-health-check'),
    
    # API health check
    path('health-check/', health_check, name='health-check'),
    
    # API endpoints
    path('api/', include('apps.api_app.urls')),
    
    # Admin panel
    path('admin/', admin.site.urls),
    
    # Catch-all route for frontend - MUST BE LAST
    re_path(r'^.*$', TemplateView.as_view(template_name='index.html')),
]

# Only for development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)