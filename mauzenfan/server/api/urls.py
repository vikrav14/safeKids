from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    RegistrationView,
    ChildViewSet,
    LocationUpdateView,
    ChildCurrentLocationView,
    ChildLocationHistoryView,
    SafeZoneViewSet,
    SOSAlertView,
    AlertListView # Added AlertListView
)
from rest_framework.authtoken.views import obtain_auth_token

router = DefaultRouter()
router.register(r'children', ChildViewSet, basename='child')
router.register(r'safezones', SafeZoneViewSet, basename='safezone')

urlpatterns = [
    # Auth
    path('auth/register/', RegistrationView.as_view(), name='user-register'),
    path('auth/login/', obtain_auth_token, name='user-login'),

    # Standalone location update
    path('location/update/', LocationUpdateView.as_view(), name='location-update'),

    # SOS Alert
    path('alert/sos/', SOSAlertView.as_view(), name='alert-sos'),

    # Alert Listing
    path('alerts/', AlertListView.as_view(), name='alerts-list'),

    # Child-specific location views (not part of the ViewSet default routes)
    path('children/<int:child_id>/location/current/', ChildCurrentLocationView.as_view(), name='child-current-location'),
    path('children/<int:child_id>/location/history/', ChildLocationHistoryView.as_view(), name='child-location-history'),

    # Include router URLs (for ChildViewSet and SafeZoneViewSet)
    path('', include(router.urls)),
]
