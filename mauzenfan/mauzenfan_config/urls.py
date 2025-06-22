# mauzenfan_config/urls.py
from django.urls import path, re_path
from django.views.generic import TemplateView
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # ... your existing patterns (api, admin, etc) ...
    path('health-check/', ...),
    path('api/', ...),
    path('admin/', ...),
    
    # Add this catch-all route LAST
    re_path(r'^.*$', TemplateView.as_view(template_name='index.html')),
]

# Serve static files in development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)