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
    AlertListView,
    DeviceRegistrationView,
    ChildCheckInView,
    SendMessageView,
    ConversationListView,
    MessageHistoryView,
    MarkMessagesAsReadView,
    ChildSendMessageView,
    StartEtaShareView,
    UpdateEtaLocationView,
    ListActiveEtaSharesView,
    CancelEtaShareView,
    ArrivedEtaShareView,
    health_check  # Add this import
)
from rest_framework.authtoken.views import obtain_auth_token
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView # Add for documentation

router = DefaultRouter()
router.register(r'children', ChildViewSet, basename='child')
router.register(r'safezones', SafeZoneViewSet, basename='safezone')

urlpatterns = [
    # ====== Added Endpoints ======
    # Health Check
    path('health/', health_check, name='health-check'),
    
    # api_app Documentation
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    # ====== End Added Endpoints ======
    
    # Auth
    path('auth/register/', RegistrationView.as_view(), name='user-register'),
    path('auth/login/', obtain_auth_token, name='user-login'),

    # Device Registration
    path('device/register/', DeviceRegistrationView.as_view(), name='device-register'),

    # Child Check-In
    path('child/check-in/', ChildCheckInView.as_view(), name='child-check-in'),

    # Messaging
    path('messages/send/', SendMessageView.as_view(), name='message-send'),
    path('child/messages/send/', ChildSendMessageView.as_view(), name='child-message-send'),
    path('messages/conversations/', ConversationListView.as_view(), name='message-conversations'),
    path('messages/conversation/<int:other_user_id>/', MessageHistoryView.as_view(), name='message-history'),
    path('messages/read/', MarkMessagesAsReadView.as_view(), name='messages-mark-read'),

    # ETA Sharing
    path('eta/start/', StartEtaShareView.as_view(), name='eta-start'),
    path('eta/<int:share_id>/update/', UpdateEtaLocationView.as_view(), name='eta-update-location'),
    path('eta/active/', ListActiveEtaSharesView.as_view(), name='eta-active-list'),
    path('eta/<int:share_id>/cancel/', CancelEtaShareView.as_view(), name='eta-cancel'),
    path('eta/<int:share_id>/arrived/', ArrivedEtaShareView.as_view(), name='eta-arrived'),

    # Standalone location update
    path('location/update/', LocationUpdateView.as_view(), name='location-update'),

    # SOS Alert
    path('alert/sos/', SOSAlertView.as_view(), name='alert-sos'),

    # Alert Listing
    path('alerts/', AlertListView.as_view(), name='alerts-list'),

    # Child-specific location views
    path('children/<int:child_id>/location/current/', ChildCurrentLocationView.as_view(), name='child-current-location'),
    path('children/<int:child_id>/location/history/', ChildLocationHistoryView.as_view(), name='child-location-history'),

    # Include router URLs
    path('', include(router.urls)),
]