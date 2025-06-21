# views.py (corrected)
from rest_framework.views import APIView  # Fixed import
from rest_framework.response import Response
from rest_framework import status, viewsets, permissions, generics
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.decorators import api_view  # Fixed decorator name
from .serializers import (
    UserRegistrationSerializer,
    ChildSerializer,
    LocationPointSerializer,
    SafeZoneSerializer,
    SOSAlertSerializer,
    AlertSerializer,
    DeviceRegistrationSerializer,
    CheckInSerializer,
    MessageSerializer,
    MessageUserSerializer,
    StartEtaShareSerializer,
    ActiveEtaShareSerializer,
    UpdateEtaLocationSerializer
)
from .models import Child, LocationPoint, SafeZone, Alert, UserDevice, Message, ActiveEtaShare
from django.contrib.auth.models import User
from .fcm_service import send_fcm_to_user
from .geolocation_utils import distance_in_meters
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import timedelta
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.http import Http404
from django.utils.dateparse import parse_datetime
from django.db.models import Q, Max, Subquery, OuterRef, Count
from rest_framework.pagination import PageNumberPagination
from django.conf import settings
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes  # Fixed names

import logging

logger = logging.getLogger(__name__)

# ====== HEALTH CHECK VIEW ======
@api_view(['GET'])
def health_check(request):
    """Simple health check endpoint"""
    return Response({
        "status": "ok",
        "service": "SafeKids API",
        "version": "1.0.0"
    })

# --- Schema-only Serializer for LocationUpdateView Request Body ---
class LocationUpdateRequestSchemaSerializer(drf_serializers.Serializer):
    child_id = drf_serializers.IntegerField(help_text="ID of the child providing the location update.")
    device_id = drf_serializers.CharField(max_length=255, help_text="Device ID of the child's device for authentication.")
    latitude = drf_serializers.DecimalField(max_digits=9, decimal_places=6, help_text="Current latitude.")
    longitude = drf_serializers.DecimalField(max_digits=9, decimal_places=6, help_text="Current longitude.")
    timestamp = drf_serializers.DateTimeField(help_text="Timestamp of the location reading (ISO 8601 format).")
    accuracy = drf_serializers.FloatField(required=False, allow_null=True, help_text="GPS accuracy in meters.")
    battery_status = drf_serializers.IntegerField(required=False, allow_null=True, help_text="Device battery level (0-100).")

class SimpleMessageResponseSerializer(drf_serializers.Serializer):
    message = drf_serializers.CharField()

class RegistrationView(APIView):  # Fixed base class
    """
    Handles new user registration.
    Creates a User and an associated UserProfile.
    """
    permission_classes = [AllowAny]
    serializer_class = UserRegistrationSerializer

    @extend_schema(
        summary="Register New User",
        request=UserRegistrationSerializer,
        responses={
            201: OpenApiTypes.OBJECT,  # Fixed
            400: OpenApiTypes.OBJECT
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response({"message": "User registered successfully.", "user_id": user.id, "username": user.username}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@extend_schema(
    summary="Manage Child Profiles",
    description="Allows authenticated parents to list, create, retrieve, update, and delete child profiles associated with their account."
)
class ChildViewSet(viewsets.ModelViewSet):
    serializer_class = ChildSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Child.objects.filter(parent=self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(parent=self.request.user)

class LocationUpdateView(APIView):  # Fixed base class
    """
    Receives location updates from a child's device.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Submit Child Location Update",
        request=LocationUpdateRequestSchemaSerializer,
        responses={
            201: SimpleMessageResponseSerializer,
            400: OpenApiTypes.OBJECT,
            403: OpenApiTypes.OBJECT,
            404: OpenApiTypes.OBJECT
        }
    )
    def post(self, request, *args, **kwargs):
        schema_serializer = LocationUpdateRequestSchemaSerializer(data=request.data)
        if not schema_serializer.is_valid():
            return Response(schema_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        validated_input = schema_serializer.validated_data
        child_id_from_req = validated_input.get('child_id')
        device_id_from_request = validated_input.get('device_id')
        
        try: 
            child = get_object_or_404(Child, pk=child_id_from_req)
        except ValueError: 
            return Response({"error": "Invalid child_id format."}, status=status.HTTP_400_BAD_REQUEST)
        
        if not child.device_id or child.device_id != device_id_from_request:
            return Response({"error": "Device ID mismatch or not registered for this child."}, status=status.HTTP_403_FORBIDDEN)
        
        # ... rest of the method remains unchanged ...

class ChildCurrentLocationView(generics.RetrieveAPIView):  # Fixed base class
    """
    Retrieves the most recent known location for a specific child.
    """
    serializer_class = LocationPointSerializer
    permission_classes = [IsAuthenticated]
    
    def get_object(self):
        child_id = self.kwargs.get('child_id')
        child = get_object_or_404(Child, pk=child_id, parent=self.request.user)
        location_point = LocationPoint.objects.filter(child=child).order_by('-timestamp').first()
        if not location_point: 
            raise Http404("No location data found for this child.")
        return location_point

class ChildLocationHistoryView(generics.ListAPIView):  # Fixed base class
    """
    Retrieves the location history for a specific child.
    """
    serializer_class = LocationPointSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination

    @extend_schema(
        summary="Retrieve Child Location History",
        parameters=[
            OpenApiParameter(  # Fixed
                name='start_timestamp', type=OpenApiTypes.DATETIME, location=OpenApiParameter.QUERY,
                required=False, description='Filter history from this ISO 8601 timestamp'
            ),
            OpenApiParameter(  # Fixed
                name='end_timestamp', type=OpenApiTypes.DATETIME, location=OpenApiParameter.QUERY,
                required=False, description='Filter history up to this ISO 8601 timestamp'
            )
        ]
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        # ... method body remains unchanged ...

@extend_schema(
    summary="Manage Safe Zones",
    description="Allows authenticated parents to list, create, retrieve, update, and delete Safe Zones."
)
class SafeZoneViewSet(viewsets.ModelViewSet):
    serializer_class = SafeZoneSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self): 
        return SafeZone.objects.filter(owner=self.request.user).order_by('-created_at')
    
    def perform_create(self, serializer): 
        serializer.save(owner=self.request.user)

class SOSAlertView(APIView):  # Fixed base class
    """
    Receives SOS alerts from a child's device.
    """
    permission_classes = [AllowAny]
    serializer_class = SOSAlertSerializer

    @extend_schema(
        summary="Trigger SOS Alert",
        request=SOSAlertSerializer,
        responses={201: SimpleMessageResponseSerializer, 400: OpenApiTypes.OBJECT, 403: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT}
    )
    def post(self, request, *args, **kwargs):
        # ... method body remains unchanged ...

@extend_schema(summary="List User Alerts")
class AlertListView(generics.ListAPIView):  # Fixed base class
    """
    Lists alerts for the authenticated user.
    """
    serializer_class = AlertSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination
    
    def get_queryset(self): 
        return Alert.objects.filter(recipient=self.request.user).order_by('-timestamp')

class DeviceRegistrationView(APIView):  # Fixed base class
    """
    Handles registration of user devices for FCM push notifications.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = DeviceRegistrationSerializer

    @extend_schema(
        summary="Register Device for FCM",
        request=DeviceRegistrationSerializer,
        responses={200: SimpleMessageResponseSerializer, 201: SimpleMessageResponseSerializer, 400: OpenApiTypes.OBJECT}
    )
    def post(self, request, *args, **kwargs):
        # ... method body remains unchanged ...

class ChildCheckInView(APIView):  # Fixed base class
    """
    Allows a child's device to send a "check-in" message.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = CheckInSerializer

    @extend_schema(
        summary="Child Check-In",
        request=CheckInSerializer,
        responses={201: SimpleMessageResponseSerializer, 400: OpenApiTypes.OBJECT, 403: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT}
    )
    def post(self, request, *args, **kwargs):
        # ... method body remains unchanged ...

class SendMessageView(APIView):  # Fixed base class
    """
    Allows an authenticated user to send a direct message
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MessageSerializer

    @extend_schema(
        summary="Send Direct Message",
        request=MessageSerializer,
        responses={201: MessageSerializer, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT}
    )
    def post(self, request, *args, **kwargs):
        # ... method body remains unchanged ...

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

class ConversationListView(APIView):  # Fixed base class
    """
    Lists recent conversations for the authenticated user.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(summary="List User Conversations", responses={200: OpenApiTypes.OBJECT})
    def get(self, request, *args, **kwargs):
        # ... method body remains unchanged ...

@extend_schema(summary="Get Message History with User")
class MessageHistoryView(generics.ListAPIView):  # Fixed base class
    """
    Retrieves the message history between the authenticated user and another specified user.
    """
    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        # ... method body remains unchanged ...

class MarkMessagesAsReadRequestSerializer(drf_serializers.Serializer):
    other_user_id = drf_serializers.IntegerField(help_text="ID of the user whose messages were read.")

class MarkMessagesAsReadView(APIView):  # Fixed base class
    """
    Marks messages from another user as read by the authenticated user.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = MarkMessagesAsReadRequestSerializer

    @extend_schema(
        summary="Mark Messages as Read",
        request=MarkMessagesAsReadRequestSerializer,
        responses={200: SimpleMessageResponseSerializer, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT}
    )
    def post(self, request, *args, **kwargs):
        # ... method body remains unchanged ...

class ChildSendMessageRequestSerializer(drf_serializers.Serializer):
    child_id = drf_serializers.IntegerField(help_text="ID of the child sending the message.")
    device_id = drf_serializers.CharField(max_length=255, help_text="Device ID for authentication.")
    content = drf_serializers.CharField(help_text="Text content of the message.")

class ChildSendMessageView(APIView):  # Fixed base class
    """
    Allows a child's device to send a message to their parent.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = ChildSendMessageRequestSerializer

    @extend_schema(
        summary="Child Send Message to Parent",
        request=ChildSendMessageRequestSerializer,
        responses={201: MessageSerializer, 400: OpenApiTypes.OBJECT, 403: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT, 500: OpenApiTypes.OBJECT}
    )
    def post(self, request, *args, **kwargs):
        # ... method body remains unchanged ...

@extend_schema(summary="Start ETA Share")
class StartEtaShareView(APIView):  # Fixed base class
    """
    Initiates a new "On My Way" ETA share.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = StartEtaShareSerializer

    @extend_schema(
        request=StartEtaShareSerializer,
        responses={201: ActiveEtaShareSerializer, 400: OpenApiTypes.OBJECT}
    )
    def post(self, request, *args, **kwargs):
        # ... method body remains unchanged ...

@extend_schema(summary="Update ETA Location")
class UpdateEtaLocationView(APIView):  # Fixed base class
    """
    Allows the sharer of an active ETA to update their current location.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UpdateEtaLocationSerializer

    @extend_schema(
        request=UpdateEtaLocationSerializer,
        responses={200: ActiveEtaShareSerializer, 400: OpenApiTypes.OBJECT, 403: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT}
    )
    def post(self, request, share_id, *args, **kwargs):
        # ... method body remains unchanged ...

@extend_schema(summary="List Active ETA Shares")
class ListActiveEtaSharesView(generics.ListAPIView):  # Fixed base class
    """
    Lists active ETA shares relevant to the authenticated user.
    """
    serializer_class = ActiveEtaShareSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        # ... method body remains unchanged ...

@extend_schema(summary="Cancel ETA Share")
class CancelEtaShareView(APIView):  # Fixed base class
    """
    Allows the sharer to cancel an active ETA share.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ActiveEtaShareSerializer

    @extend_schema(responses={200: SimpleMessageResponseSerializer, 403: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT})
    def post(self, request, share_id, *args, **kwargs):
        # ... method body remains unchanged ...

@extend_schema(summary="Mark ETA Share as Arrived")
class ArrivedEtaShareView(APIView):  # Fixed base class
    """
    Allows the sharer to mark an active ETA share as 'ARRIVED'.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ActiveEtaShareSerializer

    @extend_schema(responses={200: SimpleMessageResponseSerializer, 403: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT})
    def post(self, request, share_id, *args, **kwargs):
        # ... method body remains unchanged ...