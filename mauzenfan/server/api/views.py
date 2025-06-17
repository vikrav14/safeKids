from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, viewsets, permissions, generics
from rest_framework.permissions import AllowAny, IsAuthenticated
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
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes # For OpenAPI schema refinement
from rest_framework import serializers as drf_serializers # For inline schema serializers

import logging

logger = logging.getLogger(__name__)

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


class RegistrationView(APIView):
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
            201: OpenApiTypes.OBJECT, # Example: {"message": "User registered successfully.", "user_id": 1, "username": "newuser"}
            400: OpenApiTypes.OBJECT  # For validation errors
        }
    )
    def post(self, request, *args, **kwargs):
        """
        Registers a new user.
        Requires username, email, password, and password2.
        Optional: first_name, last_name, phone_number.
        """
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response({"message": "User registered successfully.", "user_id": user.id, "username": user.username}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@extend_schema(
    summary="Manage Child Profiles",
    description="Allows authenticated parents to list, create, retrieve, update, and delete child profiles associated with their account. A proxy user for messaging is automatically created for each new child."
)
class ChildViewSet(viewsets.ModelViewSet):
    """
    Manages CRUD operations for Child profiles.
    Restricted to the authenticated parent user.
    A proxy_user for messaging is automatically created for each new child.
    """
    serializer_class = ChildSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        This view should return a list of all the children
        for the currently authenticated user.
        """
        return Child.objects.filter(parent=self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        """
        Set the parent of the child to the currently authenticated user.
        """
        serializer.save(parent=self.request.user)

class LocationUpdateView(APIView):
    """
    Receives location updates from a child's device.
    This endpoint is also responsible for triggering Safe Zone breach checks
    and Low Battery alerts based on the received location and battery status.
    Device authentication is based on child_id and device_id.
    """
    permission_classes = [AllowAny]
    # Note: We use LocationUpdateRequestSchemaSerializer for @extend_schema's request body,
    # but LocationPointSerializer for the actual data validation of the location part.
    # This is because the request includes more than just LocationPoint fields.

    @extend_schema(
        summary="Submit Child Location Update",
        description="Receives a location update from a child's device. This endpoint also triggers checks for Safe Zone breaches and Low Battery alerts.",
        request=LocationUpdateRequestSchemaSerializer,
        responses={
            201: SimpleMessageResponseSerializer,
            400: OpenApiTypes.OBJECT,
            403: OpenApiTypes.OBJECT,
            404: OpenApiTypes.OBJECT
        }
    )
    def post(self, request, *args, **kwargs):
        """
        Processes a location update from a device.
        Requires child_id, device_id, latitude, longitude, and timestamp.
        Optional: battery_status, accuracy.
        Returns success or error. Triggers alerts and WebSocket pushes internally.
        """
        # Validate the overall request structure first using the schema-specific serializer
        schema_serializer = LocationUpdateRequestSchemaSerializer(data=request.data)
        if not schema_serializer.is_valid():
            return Response(schema_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated_input = schema_serializer.validated_data # Use this for child_id, device_id etc.

        child_id_from_req = validated_input.get('child_id')
        device_id_from_request = validated_input.get('device_id')
        battery_status_from_req = validated_input.get('battery_status')

        # No need for `if not all([...])` as schema_serializer handles required fields.

        try: child = get_object_or_404(Child, pk=child_id_from_req)
        except ValueError: return Response({"error": "Invalid child_id format."}, status=status.HTTP_400_BAD_REQUEST) # Should be caught by IntegerField

        if not child.device_id or child.device_id != device_id_from_request:
            return Response( {"error": "Device ID mismatch or not registered for this child."}, status=status.HTTP_403_FORBIDDEN )

        # Validate location-specific parts using LocationPointSerializer
        # Pass only relevant data to LocationPointSerializer
        location_data_for_serializer = {
            'latitude': validated_input['latitude'],
            'longitude': validated_input['longitude'],
            'timestamp': validated_input['timestamp'],
        }
        if validated_input.get('accuracy') is not None: # Handle optional field
            location_data_for_serializer['accuracy'] = validated_input['accuracy']

        location_serializer = LocationPointSerializer(data=location_data_for_serializer)
        if location_serializer.is_valid():
            LocationPoint.objects.create( child=child, **location_serializer.validated_data)

            if battery_status_from_req is not None:
                try: child.battery_status = int(battery_status_from_req) # Already int via schema_serializer if valid
                except ValueError: logger.warning(f"Invalid battery_status '{battery_status_from_req}' for child {child.id}")
            child.last_seen_at = timezone.now(); child.save(update_fields=['battery_status', 'last_seen_at'])

            channel_layer = get_channel_layer(); parent_user_id = child.parent.id; group_name = f'user_{parent_user_id}_notifications'
            location_data_for_ws = { 'type': 'location_update', 'child_id': child.id, 'child_name': child.name, 'latitude': float(location_serializer.validated_data['latitude']), 'longitude': float(location_serializer.validated_data['longitude']), 'timestamp': location_serializer.validated_data['timestamp'].isoformat(), 'accuracy': float(location_serializer.validated_data.get('accuracy')) if location_serializer.validated_data.get('accuracy') is not None else None, 'battery_status': child.battery_status }
            async_to_sync(channel_layer.group_send)( group_name, { "type": "location.update", "payload": location_data_for_ws } )

            parent_user = child.parent; current_location_lat = location_serializer.validated_data['latitude']; current_location_lon = location_serializer.validated_data['longitude']

            active_safe_zones = SafeZone.objects.filter(owner=parent_user, is_active=True); ALERT_COOLDOWN_MINUTES = 10
            for zone in active_safe_zones:
                distance_to_zone_center_m = distance_in_meters( current_location_lat, current_location_lon, zone.latitude, zone.longitude )
                currently_inside_zone = distance_to_zone_center_m <= zone.radius
                last_alert_for_zone = Alert.objects.filter( recipient=parent_user, child=child, safe_zone_id=zone.id ).order_by('-timestamp').first()
                previous_status_was_inside = False; alert_on_cooldown = False
                if last_alert_for_zone:
                    if last_alert_for_zone.alert_type == 'ENTERED_ZONE': previous_status_was_inside = True
                    if (timezone.now() - last_alert_for_zone.timestamp) < timedelta(minutes=ALERT_COOLDOWN_MINUTES): alert_on_cooldown = True
                new_alert_type = None; alert_message = ""
                if currently_inside_zone and not previous_status_was_inside and not alert_on_cooldown: new_alert_type = 'ENTERED_ZONE'; alert_message = f"{child.name} has entered {zone.name}."
                elif not currently_inside_zone and previous_status_was_inside and not alert_on_cooldown: new_alert_type = 'LEFT_ZONE'; alert_message = f"{child.name} has left {zone.name}."
                if new_alert_type:
                    created_breach_alert = Alert.objects.create( recipient=parent_user, child=child, alert_type=new_alert_type, message=alert_message, safe_zone_id=zone.id )
                    push_title = f"Safe Zone Alert: {child.name}"; push_data = { 'alert_type': new_alert_type, 'child_id': str(child.id), 'child_name': child.name, 'zone_id': str(zone.id), 'zone_name': zone.name, 'alert_id': str(created_breach_alert.id) }
                    send_fcm_to_user(user=parent_user, title=push_title, body=alert_message, data=push_data)
                    ws_message_payload = { 'type': 'safezone_alert', 'alert_id': created_breach_alert.id, 'child_id': child.id, 'child_name': child.name, 'zone_id': zone.id, 'zone_name': zone.name, 'alert_type': new_alert_type, 'message': alert_message, 'timestamp': created_breach_alert.timestamp.isoformat() }
                    async_to_sync(channel_layer.group_send)( group_name, { "type": "send_notification", "message": ws_message_payload } )

            LOW_BATTERY_THRESHOLD = 20; LOW_BATTERY_ALERT_COOLDOWN_MINUTES = 60
            if validated_input.get('battery_status') is not None: # Use validated_input here
                try:
                    current_battery_level = validated_input['battery_status'] # Already int if valid
                    if current_battery_level < LOW_BATTERY_THRESHOLD:
                        last_low_battery_alert = Alert.objects.filter( recipient=parent_user, child=child, alert_type='LOW_BATTERY' ).order_by('-timestamp').first()
                        send_new_low_battery_alert = True
                        if last_low_battery_alert:
                            if (timezone.now() - last_low_battery_alert.timestamp) < timedelta(minutes=LOW_BATTERY_ALERT_COOLDOWN_MINUTES): send_new_low_battery_alert = False
                        if send_new_low_battery_alert:
                            alert_message = f"{child.name}'s phone battery is low: {current_battery_level}%."
                            created_low_battery_alert = Alert.objects.create( recipient=parent_user, child=child, alert_type='LOW_BATTERY', message=alert_message )
                            push_title = f"Low Battery Warning: {child.name}"; push_data = { 'alert_type': 'LOW_BATTERY', 'child_id': str(child.id), 'child_name': child.name, 'battery_level': str(current_battery_level), 'alert_id': str(created_low_battery_alert.id) }
                            send_fcm_to_user(user=parent_user, title=push_title, body=alert_message, data=push_data)
                            ws_message_payload = { 'type': 'low_battery_alert', 'alert_id': created_low_battery_alert.id, 'child_id': child.id, 'child_name': child.name, 'battery_level': current_battery_level, 'message': alert_message, 'timestamp': created_low_battery_alert.timestamp.isoformat() }
                            async_to_sync(channel_layer.group_send)( group_name, { "type": "send_notification", "message": ws_message_payload } )
                except ValueError: logger.warning(f"Invalid battery_status value received: {validated_input.get('battery_status')} for child {child.id}"); pass
            return Response( {"message": "Location updated successfully. Safe zone and battery checks performed."}, status=status.HTTP_201_CREATED )
        return Response(location_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ChildCurrentLocationView(generics.RetrieveAPIView):
    """
    Retrieves the most recent known location for a specific child.
    Only accessible by the parent of the child.
    """
    serializer_class = LocationPointSerializer
    permission_classes = [IsAuthenticated]
    def get_object(self):
        child_id = self.kwargs.get('child_id'); child = get_object_or_404(Child, pk=child_id, parent=self.request.user)
        location_point = LocationPoint.objects.filter(child=child).order_by('-timestamp').first()
        if not location_point: raise Http404("No location data found for this child.")
        return location_point

class ChildLocationHistoryView(generics.ListAPIView):
    """
    Retrieves the location history for a specific child.
    Only accessible by the parent of the child. Supports pagination.
    Optional query parameters: `start_timestamp` and `end_timestamp` (ISO 8601 format).
    """
    serializer_class = LocationPointSerializer; permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination

    @extend_schema(
        summary="Retrieve Child Location History",
        description="Lists location points for a specific child, optionally filtered by a time range. Results are paginated.",
        parameters=[
            OpenApiParameter(
                name='start_timestamp', type=OpenApiTypes.DATETIME, location=OpenApiParameter.QUERY,
                required=False, description='Filter history from this ISO 8601 timestamp. E.g., 2023-01-01T00:00:00Z'
            ),
            OpenApiParameter(
                name='end_timestamp', type=OpenApiTypes.DATETIME, location=OpenApiParameter.QUERY,
                required=False, description='Filter history up to this ISO 8601 timestamp. E.g., 2023-01-01T12:00:00Z'
            )
        ]
    )
    def get(self, request, *args, **kwargs):
        """
        GET /api/children/{child_id}/location/history/
        Returns paginated location history for the specified child.
        """
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        child_id = self.kwargs.get('child_id')
        child = get_object_or_404(Child, pk=child_id, parent=self.request.user)
        queryset = LocationPoint.objects.filter(child=child).order_by('timestamp')
        start_timestamp_str = self.request.query_params.get('start_timestamp'); end_timestamp_str = self.request.query_params.get('end_timestamp')
        if start_timestamp_str:
            try:
                start_timestamp = parse_datetime(start_timestamp_str)
                if start_timestamp:
                    if timezone.is_naive(start_timestamp): start_timestamp = timezone.make_aware(start_timestamp, timezone.get_default_timezone())
                    queryset = queryset.filter(timestamp__gte=start_timestamp)
            except (ValueError, TypeError): pass
        if end_timestamp_str:
            try:
                end_timestamp = parse_datetime(end_timestamp_str)
                if end_timestamp:
                    if timezone.is_naive(end_timestamp): end_timestamp = timezone.make_aware(end_timestamp, timezone.get_default_timezone())
                    queryset = queryset.filter(timestamp__lte=end_timestamp)
            except (ValueError, TypeError): pass
        return queryset

@extend_schema(
    summary="Manage Safe Zones",
    description="Allows authenticated parents to list, create, retrieve, update, and delete Safe Zones (geofenced areas) associated with their account."
)
class SafeZoneViewSet(viewsets.ModelViewSet):
    """
    Manages CRUD operations for Safe Zones (geofenced areas).
    Each Safe Zone is owned by a user (parent). Users can only manage their own Safe Zones.
    """
    serializer_class = SafeZoneSerializer; permission_classes = [IsAuthenticated]
    def get_queryset(self): return SafeZone.objects.filter(owner=self.request.user).order_by('-created_at')
    def perform_create(self, serializer): serializer.save(owner=self.request.user)

class SOSAlertView(APIView):
    """
    Receives SOS alerts from a child's device.
    Device authentication is based on child_id and device_id.
    Creates an 'SOS' Alert and notifies the parent via FCM.
    """
    permission_classes = [AllowAny]
    serializer_class = SOSAlertSerializer

    @extend_schema(
        summary="Trigger SOS Alert",
        request=SOSAlertSerializer,
        responses={201: SimpleMessageResponseSerializer, 400: OpenApiTypes.OBJECT, 403: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT}
    )
    def post(self, request, *args, **kwargs):
        """
        Triggers an SOS alert for a child.
        Requires child_id and device_id. Optional: latitude, longitude.
        If location is provided, it's included in the alert. Otherwise, tries to use last known location.
        """
        serializer = SOSAlertSerializer(data=request.data);
        if not serializer.is_valid(): return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        validated_data = serializer.validated_data; child_id = validated_data.get('child_id'); device_id_from_request = validated_data.get('device_id'); latitude = validated_data.get('latitude'); longitude = validated_data.get('longitude')
        try: child = get_object_or_404(Child, pk=child_id)
        except Http404: return Response({"error": "Child not found."}, status=status.HTTP_404_NOT_FOUND)
        if not child.device_id or child.device_id != device_id_from_request: return Response({"error": "Device ID mismatch or not registered for this child."}, status=status.HTTP_403_FORBIDDEN)
        parent_user = child.parent; message_parts = [f"SOS triggered by {child.name}."]; location_known = False
        if latitude is not None and longitude is not None: message_parts.append(f"Current location: lat {latitude}, lon {longitude}."); location_known = True
        else:
            last_location = LocationPoint.objects.filter(child=child).order_by('-timestamp').first()
            if last_location: message_parts.append(f"Last known location (at {last_location.timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')}): lat {last_location.latitude}, lon {last_location.longitude}."); location_known = True
        if not location_known: message_parts.append("Current location not available.")
        sos_message = " ".join(message_parts)
        created_alert = Alert.objects.create(recipient=parent_user, child=child, alert_type='SOS', message=sos_message)
        push_title = f"SOS Alert: {child.name}"; push_data = {'alert_type': 'SOS', 'child_id': str(child.id), 'child_name': child.name, 'alert_id': str(created_alert.id)}
        if latitude is not None and longitude is not None: push_data['latitude'] = str(latitude); push_data['longitude'] = str(longitude)
        elif 'last_location' in locals() and last_location: push_data['latitude'] = str(last_location.latitude); push_data['longitude'] = str(last_location.longitude); push_data['location_timestamp'] = last_location.timestamp.isoformat()
        send_fcm_to_user(user=parent_user, title=push_title, body=sos_message, data=push_data)
        return Response({"message": "SOS alert successfully triggered, recorded, and notification sent."}, status=status.HTTP_201_CREATED)

@extend_schema(summary="List User Alerts")
class AlertListView(generics.ListAPIView):
    """
    Lists alerts for the authenticated user.
    Alerts are ordered by newest first and paginated.
    """
    serializer_class = AlertSerializer; permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination
    def get_queryset(self): return Alert.objects.filter(recipient=self.request.user).order_by('-timestamp')

class DeviceRegistrationView(APIView):
    """
    Handles registration of user devices for FCM push notifications.
    Associates a device token with the authenticated user.
    If the token was previously registered to another user, it's deactivated for the old user.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = DeviceRegistrationSerializer

    @extend_schema(
        summary="Register Device for FCM",
        request=DeviceRegistrationSerializer,
        responses={200: SimpleMessageResponseSerializer, 201: SimpleMessageResponseSerializer, 400: OpenApiTypes.OBJECT}
    )
    def post(self, request, *args, **kwargs):
        """
        Register a device token for FCM.
        Requires device_token. Optional: device_type ('android', 'ios', 'web').
        """
        serializer = DeviceRegistrationSerializer(data=request.data);
        if serializer.is_valid():
            device_token = serializer.validated_data['device_token']; device_type = serializer.validated_data.get('device_type')
            UserDevice.objects.filter(device_token=device_token).exclude(user=request.user).update(is_active=False)
            user_device, created = UserDevice.objects.update_or_create( user=request.user, device_token=device_token, defaults={'is_active': True, 'device_type': device_type} )
            if created: return Response({"message": "Device registered successfully."}, status=status.HTTP_201_CREATED)
            else: return Response({"message": "Device registration updated successfully."}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ChildCheckInView(APIView):
    """
    Allows a child's device to send a "check-in" message.
    This creates a LocationPoint and an Alert for the parent.
    Device authentication is based on child_id and device_id.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = CheckInSerializer

    @extend_schema(
        summary="Child Check-In",
        request=CheckInSerializer,
        responses={201: SimpleMessageResponseSerializer, 400: OpenApiTypes.OBJECT, 403: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT}
    )
    def post(self, request, *args, **kwargs):
        """
        Processes a child check-in.
        Requires child_id, device_id, check_in_type, location data, and client_timestamp_iso.
        Optional: custom_message, location_name.
        """
        serializer = CheckInSerializer(data=request.data)
        if not serializer.is_valid(): return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        validated_data = serializer.validated_data; child_id = validated_data['child_id']; device_id_from_request = validated_data['device_id']
        try: child = get_object_or_404(Child, pk=child_id, is_active=True)
        except Http404: return Response({"error": "Child not found or not active."}, status=status.HTTP_404_NOT_FOUND)
        if not child.device_id or child.device_id != device_id_from_request: return Response( {"error": "Device ID mismatch or not registered for this child."}, status=status.HTTP_403_FORBIDDEN )
        parent_user = child.parent
        LocationPoint.objects.create( child=child, latitude=validated_data['latitude'], longitude=validated_data['longitude'], timestamp=validated_data['client_timestamp_iso'], )
        check_in_type_str = validated_data['check_in_type'].replace('_', ' ').title(); location_desc = validated_data.get('location_name') or f"coordinates {validated_data['latitude']}, {validated_data['longitude']}"
        if validated_data.get('custom_message'): alert_message = f"{child.name} checked in from {location_desc}: \"{validated_data['custom_message']}\""
        else: alert_message = f"{child.name} {check_in_type_str} from {location_desc}."
        created_alert = Alert.objects.create( recipient=parent_user, child=child, alert_type='CHECK_IN', message=alert_message, )
        push_title = f"Check-In: {child.name}"; push_data = { 'alert_type': 'CHECK_IN', 'child_id': str(child.id), 'child_name': child.name, 'check_in_type': validated_data['check_in_type'], 'message': alert_message, 'latitude': str(validated_data['latitude']), 'longitude': str(validated_data['longitude']), 'location_name': validated_data.get('location_name', ''), 'alert_id': str(created_alert.id), 'timestamp': validated_data['client_timestamp_iso'].isoformat() }
        send_fcm_to_user(user=parent_user, title=push_title, body=alert_message, data=push_data)
        channel_layer = get_channel_layer(); group_name = f'user_{parent_user.id}_notifications'
        ws_message_payload = { 'type': 'child_check_in', 'alert_id': str(created_alert.id), 'data': push_data }
        async_to_sync(channel_layer.group_send)( group_name, { "type": "send_notification", "message": ws_message_payload } )
        logger.info(f"Processed check-in for child {child.name}, parent {parent_user.username}")
        return Response({"message": "Check-in processed successfully."}, status=status.HTTP_201_CREATED)

class SendMessageView(APIView):
    """
    Allows an authenticated user (parent or another user) to send a direct message
    to another user (parent or a child's proxy_user).
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MessageSerializer

    @extend_schema(
        summary="Send Direct Message",
        request=MessageSerializer, # This implicitly uses write-only fields for request, read-only for response
        responses={201: MessageSerializer, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT}
    )
    def post(self, request, *args, **kwargs):
        """
        Sends a new message.
        Requires `receiver_id` (User ID of the recipient) and `content`.
        Returns the created Message object.
        Triggers WebSocket and FCM notifications to the recipient.
        """
        serializer = MessageSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            receiver_id = serializer.validated_data['receiver_id']
            content = serializer.validated_data['content']
            try: receiver = User.objects.get(pk=receiver_id)
            except User.DoesNotExist: return Response({"error": "Recipient not found."}, status=status.HTTP_404_NOT_FOUND)
            message = Message.objects.create( sender=request.user, receiver=receiver, content=content )
            broadcast_serializer = MessageSerializer(message)
            channel_layer = get_channel_layer(); recipient_group_name = f'user_{receiver.id}_notifications'
            ws_message_payload = { 'type': 'new_message', 'data': broadcast_serializer.data }
            async_to_sync(channel_layer.group_send)( recipient_group_name, { "type": "new.chat.message", "payload": ws_message_payload } )

            sender_display_name = request.user.get_full_name() or request.user.username
            message_preview = (message.content[:70] + '...') if len(message.content) > 70 else message.content
            fcm_push_data = {
                'type': 'new_message', 'message_id': str(message.id), 'sender_id': str(request.user.id),
                'sender_name': sender_display_name, 'conversation_with_user_id': str(request.user.id),
                'content_preview': message_preview
            }
            send_fcm_to_user( user=receiver, title=f"New message from {sender_display_name}", body=message_preview, data=fcm_push_data )
            logger.info(f"Message from {request.user.username} to {receiver.username} sent, broadcasted via WS, and FCM notification queued.")
            return Response(broadcast_serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20; page_size_query_param = 'page_size'; max_page_size = 100

class ConversationListView(APIView):
    """
    Lists recent conversations for the authenticated user.
    A "conversation" is with another User (could be a parent or a child's proxy_user).
    Each item includes details of the other user, the last message exchanged, and unread count.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="List User Conversations",
        responses={ 200: OpenApiTypes.OBJECT } # Actual response is a list of custom objects
    )
    def get(self, request, *args, **kwargs):
        """
        Retrieve a list of conversations, sorted by the most recent message.
        """
        user = request.user
        sent_to_users = User.objects.filter(received_messages__sender=user).distinct()
        received_from_users = User.objects.filter(sent_messages__receiver=user).distinct()
        contact_users_qs = (sent_to_users | received_from_users).distinct()
        conversations = []
        for contact_user in contact_users_qs:
            last_message = Message.objects.filter( (Q(sender=user, receiver=contact_user) | Q(sender=contact_user, receiver=user)) ).order_by('-timestamp').first()
            if last_message:
                unread_count = Message.objects.filter(sender=contact_user, receiver=user, is_read=False).count()
                conversations.append({ 'contact_user_id': contact_user.id, 'contact_details': MessageUserSerializer(contact_user).data, 'last_message': MessageSerializer(last_message).data, 'unread_count': unread_count, 'last_message_timestamp': last_message.timestamp })
        conversations.sort(key=lambda c: c['last_message_timestamp'], reverse=True)
        return Response(conversations, status=status.HTTP_200_OK)

@extend_schema(summary="Get Message History with User")
class MessageHistoryView(generics.ListAPIView):
    """
    Retrieves the message history between the authenticated user and another specified user.
    Messages are paginated and ordered chronologically.
    """
    serializer_class = MessageSerializer; permission_classes = [IsAuthenticated]; pagination_class = StandardResultsSetPagination
    def get_queryset(self):
        """
        GET /api/messages/conversation/<other_user_id>/
        Returns paginated message history with the specified user.
        """
        other_user_id = self.kwargs.get('other_user_id'); user = self.request.user
        if str(other_user_id) == str(user.id): return Message.objects.none()
        try: User.objects.get(pk=other_user_id)
        except User.DoesNotExist: return Message.objects.none()
        queryset = Message.objects.filter( (Q(sender=user, receiver_id=other_user_id) | Q(sender_id=other_user_id, receiver=user)) ).select_related('sender__messaging_child_profile', 'receiver__messaging_child_profile').order_by('timestamp')
        return queryset

class MarkMessagesAsReadRequestSerializer(drf_serializers.Serializer):
    other_user_id = drf_serializers.IntegerField(help_text="ID of the user whose messages were read.")

class MarkMessagesAsReadView(APIView):
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
        """
        Mark messages as read.
        Requires `other_user_id` in the request body, indicating the sender of messages to be marked as read.
        Triggers a WebSocket notification to the other user about the read status.
        """
        serializer = MarkMessagesAsReadRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        other_user_id = serializer.validated_data['other_user_id']
        try: other_user = User.objects.get(pk=other_user_id)
        except User.DoesNotExist: return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        messages_updated_count = Message.objects.filter( sender=other_user, receiver=request.user, is_read=False ).update(is_read=True)
        if messages_updated_count > 0 and other_user:
            channel_layer = get_channel_layer(); sender_notification_group_name = f'user_{other_user.id}_notifications'
            read_receipt_payload = { 'type': 'messages_read', 'reader_id': str(request.user.id), 'conversation_with_user_id': str(request.user.id), 'read_at_timestamp': timezone.now().isoformat() }
            async_to_sync(channel_layer.group_send)( sender_notification_group_name, { "type": "messages.read.receipt", "payload": read_receipt_payload } )
            logger.info(f"Sent read receipt to user {other_user.username} for conversation with {request.user.username}")
        return Response({"message": f"{messages_updated_count} messages marked as read."}, status=status.HTTP_200_OK)

class ChildSendMessageRequestSerializer(drf_serializers.Serializer): # For ChildSendMessageView schema
    child_id = drf_serializers.IntegerField(help_text="ID of the child sending the message.")
    device_id = drf_serializers.CharField(max_length=255, help_text="Device ID for authentication.")
    content = drf_serializers.CharField(help_text="Text content of the message.")

class ChildSendMessageView(APIView):
    """
    Allows a child's device to send a message to their parent.
    Device authentication is based on child_id and device_id.
    The message is sent from the child's proxy_user to the parent.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = ChildSendMessageRequestSerializer

    @extend_schema(
        summary="Child Send Message to Parent",
        request=ChildSendMessageRequestSerializer,
        responses={201: MessageSerializer, 400: OpenApiTypes.OBJECT, 403: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT, 500: OpenApiTypes.OBJECT}
    )
    def post(self, request, *args, **kwargs):
        """
        Sends a message from a child to their parent.
        Requires `child_id`, `device_id`, and `content`.
        """
        serializer = ChildSendMessageRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated_data = serializer.validated_data
        child_id = validated_data['child_id']; device_id_from_request = validated_data['device_id']; content = validated_data['content']

        if not content.strip(): return Response({"error": "Message content cannot be empty."}, status=status.HTTP_400_BAD_REQUEST) # Already handled by serializer if CharField has no allow_blank
        try: child = get_object_or_404(Child, pk=child_id, is_active=True)
        except Http404: return Response({"error": "Child not found or not active."}, status=status.HTTP_404_NOT_FOUND)
        if not child.device_id or child.device_id != device_id_from_request: return Response({"error": "Device ID mismatch or not registered."}, status=status.HTTP_403_FORBIDDEN)
        if not child.proxy_user: logger.error(f"Child {child.id} ({child.name}) does not have a proxy_user for messaging. Cannot send message."); return Response({"error": "Messaging not enabled for this child account."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        parent_user = child.parent; sender_proxy_user = child.proxy_user
        message = Message.objects.create( sender=sender_proxy_user, receiver=parent_user, content=content )
        broadcast_serializer = MessageSerializer(message)
        channel_layer = get_channel_layer(); recipient_group_name = f'user_{parent_user.id}_notifications'
        ws_message_payload = {'type': 'new_message', 'data': broadcast_serializer.data}
        async_to_sync(channel_layer.group_send)( recipient_group_name, {"type": "new.chat.message", "payload": ws_message_payload} )
        sender_display_name = child.name; message_preview = (message.content[:70] + '...') if len(message.content) > 70 else message.content
        fcm_push_data = { 'type': 'new_message', 'message_id': str(message.id), 'sender_id': str(sender_proxy_user.id), 'sender_name': sender_display_name, 'conversation_with_user_id': str(sender_proxy_user.id), 'child_sender_actual_id': str(child.id), 'content_preview': message_preview }
        send_fcm_to_user( user=parent_user, title=f"New message from {sender_display_name}", body=message_preview, data=fcm_push_data )
        logger.info(f"Message from Child {child.name} (via proxy {sender_proxy_user.username}) to Parent {parent_user.username} sent, broadcasted via WS, and FCM notification queued.")
        return Response(broadcast_serializer.data, status=status.HTTP_201_CREATED)

@extend_schema(summary="Start ETA Share")
class StartEtaShareView(APIView):
    """
    Initiates a new "On My Way" ETA share.
    Allows an authenticated user (sharer) to start sharing their ETA to a specified
    destination with a list of other users. An initial ETA is calculated.
    Notifications (FCM & WebSocket) are sent to users this ETA is shared with.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = StartEtaShareSerializer

    @extend_schema( # More specific for post if needed, otherwise class-level serializer_class is used
        request=StartEtaShareSerializer,
        responses={201: ActiveEtaShareSerializer, 400: OpenApiTypes.OBJECT}
    )
    def post(self, request, *args, **kwargs):
        """
        Create a new ETA share session.
        Requires destination coordinates, sharer's current coordinates.
        Optional: destination_name, list of user_ids to share_with.
        Returns the created ActiveEtaShare object.
        """
        serializer = StartEtaShareSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid(): return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        validated_data = serializer.validated_data; sharer = request.user
        calculated_eta_datetime = None
        try:
            distance_m = distance_in_meters( validated_data['current_latitude'], validated_data['current_longitude'], validated_data['destination_latitude'], validated_data['destination_longitude'] )
            speed_kmh = float(getattr(settings, 'DEFAULT_ETA_SPEED_KMH', 30))
            if speed_kmh <= 0: speed_kmh = 30
            duration_hours = (distance_m / 1000.0) / speed_kmh; duration_seconds = duration_hours * 3600
            calculated_eta_datetime = timezone.now() + timedelta(seconds=duration_seconds)
        except Exception as e: logger.error(f"Error calculating ETA: {e}", exc_info=True)
        eta_share = ActiveEtaShare.objects.create( sharer=sharer, destination_name=validated_data.get('destination_name'), destination_latitude=validated_data['destination_latitude'], destination_longitude=validated_data['destination_longitude'], current_latitude=validated_data['current_latitude'], current_longitude=validated_data['current_longitude'], calculated_eta=calculated_eta_datetime, status='ACTIVE' )
        shared_with_users = []
        if validated_data.get('shared_with_user_ids'):
            shared_with_users = User.objects.filter(pk__in=validated_data['shared_with_user_ids'])
            eta_share.shared_with.set(shared_with_users)
        output_serializer = ActiveEtaShareSerializer(eta_share, context={'request': request}); eta_share_data_for_client = output_serializer.data
        fcm_title = f"ETA Share Started by {sharer.get_full_name() or sharer.username}"; fcm_body = f"Tracking {sharer.get_full_name() or sharer.username} to {validated_data.get('destination_name', 'destination')}. ETA: {calculated_eta_datetime.strftime('%I:%M %p') if calculated_eta_datetime else 'N/A'}"
        fcm_push_data = { 'type': 'eta_started', 'share_id': str(eta_share.id), 'sharer_id': str(sharer.id), 'sharer_name': sharer.get_full_name() or sharer.username, 'destination_name': eta_share.destination_name, 'eta': eta_share.calculated_eta.isoformat() if eta_share.calculated_eta else None }
        ws_payload = { 'type': 'eta_started', 'data': eta_share_data_for_client }; channel_layer = get_channel_layer()
        for user_to_notify in shared_with_users:
            send_fcm_to_user(user=user_to_notify, title=fcm_title, body=fcm_body, data=fcm_push_data)
            recipient_group_name = f'user_{user_to_notify.id}_notifications'
            async_to_sync(channel_layer.group_send)( recipient_group_name, {"type": "send_notification", "message": ws_payload} )
        logger.info(f"ETA Share ID {eta_share.id} started by {sharer.username} and notifications sent.")
        return Response(eta_share_data_for_client, status=status.HTTP_201_CREATED)

@extend_schema(summary="Update ETA Location")
class UpdateEtaLocationView(APIView):
    """
    Allows the sharer of an active ETA to update their current location.
    This recalculates the ETA and broadcasts the update to users it's shared with.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UpdateEtaLocationSerializer

    @extend_schema( # More specific for post
        request=UpdateEtaLocationSerializer,
        responses={200: ActiveEtaShareSerializer, 400: OpenApiTypes.OBJECT, 403: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT}
    )
    def post(self, request, share_id, *args, **kwargs):
        """
        Update current location for an active ETA share.
        Requires `current_latitude` and `current_longitude`.
        Recalculates ETA and notifies shared users.
        """
        try: eta_share = get_object_or_404(ActiveEtaShare, pk=share_id, status='ACTIVE')
        except Http404: return Response({"error": "Active ETA share not found."}, status=status.HTTP_404_NOT_FOUND)
        if eta_share.sharer != request.user: return Response( {"error": "You do not have permission to update this ETA share."}, status=status.HTTP_403_FORBIDDEN )
        serializer = UpdateEtaLocationSerializer(data=request.data)
        if not serializer.is_valid(): return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        validated_data = serializer.validated_data
        eta_share.current_latitude = validated_data['current_latitude']; eta_share.current_longitude = validated_data['current_longitude']
        new_calculated_eta_datetime = None
        try:
            distance_m = distance_in_meters( eta_share.current_latitude, eta_share.current_longitude, eta_share.destination_latitude, eta_share.destination_longitude )
            speed_kmh = float(getattr(settings, 'DEFAULT_ETA_SPEED_KMH', 30))
            if speed_kmh <= 0: speed_kmh = 30
            duration_hours = (distance_m / 1000.0) / speed_kmh; duration_seconds = duration_hours * 3600
            new_calculated_eta_datetime = timezone.now() + timedelta(seconds=duration_seconds); eta_share.calculated_eta = new_calculated_eta_datetime
        except Exception as e: logger.error(f"Error recalculating ETA for share {share_id}: {e}", exc_info=True)
        eta_share.save()
        output_serializer = ActiveEtaShareSerializer(eta_share, context={'request': request}); eta_share_data_for_client = output_serializer.data
        channel_layer = get_channel_layer(); ws_payload = { 'type': 'eta_updated', 'data': eta_share_data_for_client }
        for user_to_notify in eta_share.shared_with.all():
            recipient_group_name = f'user_{user_to_notify.id}_notifications'
            async_to_sync(channel_layer.group_send)( recipient_group_name, {"type": "send_notification", "message": ws_payload} )
        sharer_group_name = f'user_{eta_share.sharer.id}_notifications'
        async_to_sync(channel_layer.group_send)( sharer_group_name, {"type": "send_notification", "message": ws_payload} )
        logger.info(f"ETA Share ID {eta_share.id} updated by {request.user.username}. New ETA: {eta_share.calculated_eta}")
        return Response(eta_share_data_for_client, status=status.HTTP_200_OK)

@extend_schema(summary="List Active ETA Shares")
class ListActiveEtaSharesView(generics.ListAPIView):
    """
    Lists active ETA shares relevant to the authenticated user.
    This includes shares started by the user and shares shared with the user.
    """
    serializer_class = ActiveEtaShareSerializer
    permission_classes = [permissions.IsAuthenticated]
    # pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        """
        Returns active ETA shares where the user is the sharer or in the 'shared_with' list.
        """
        user = self.request.user
        return ActiveEtaShare.objects.filter(
            Q(status='ACTIVE'),
            Q(sharer=user) | Q(shared_with=user)
        ).distinct().order_by('-updated_at')

@extend_schema(summary="Cancel ETA Share")
class CancelEtaShareView(APIView):
    """
    Allows the sharer to cancel an active ETA share.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ActiveEtaShareSerializer # For response documentation

    @extend_schema(responses={200: SimpleMessageResponseSerializer, 403:OpenApiTypes.OBJECT, 404:OpenApiTypes.OBJECT})
    def post(self, request, share_id, *args, **kwargs):
        """
        Cancel an active ETA share. Only the original sharer can perform this action.
        """
        try:
            eta_share = get_object_or_404(ActiveEtaShare, pk=share_id, status='ACTIVE')
        except Http404:
            return Response({"error": "Active ETA share not found."}, status=status.HTTP_404_NOT_FOUND)

        if eta_share.sharer != request.user:
            return Response({"error": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

        eta_share.status = 'CANCELLED'
        eta_share.save(update_fields=['status', 'updated_at'])

        channel_layer = get_channel_layer()
        ws_payload = {
            'type': 'eta_cancelled',
            'data': ActiveEtaShareSerializer(eta_share, context={'request': request}).data
        }

        users_to_notify = list(eta_share.shared_with.all()) + [eta_share.sharer]
        for user_to_notify in users_to_notify:
            if user_to_notify:
                group_name = f'user_{user_to_notify.id}_notifications'
                async_to_sync(channel_layer.group_send)(
                    group_name,
                    {"type": "send_notification", "message": ws_payload}
                )

        logger.info(f"ETA Share ID {eta_share.id} cancelled by {request.user.username}.")
        return Response({"message": "ETA share cancelled successfully."}, status=status.HTTP_200_OK)

@extend_schema(summary="Mark ETA Share as Arrived")
class ArrivedEtaShareView(APIView):
    """
    Allows the sharer to mark an active ETA share as 'ARRIVED'.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ActiveEtaShareSerializer # For response documentation

    @extend_schema(responses={200: SimpleMessageResponseSerializer, 403:OpenApiTypes.OBJECT, 404:OpenApiTypes.OBJECT})
    def post(self, request, share_id, *args, **kwargs):
        """
        Mark an active ETA share as arrived. Only the original sharer can perform this action.
        """
        try:
            eta_share = get_object_or_404(ActiveEtaShare, pk=share_id, status='ACTIVE')
        except Http404:
            return Response({"error": "Active ETA share not found."}, status=status.HTTP_404_NOT_FOUND)

        if eta_share.sharer != request.user:
            return Response({"error": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

        eta_share.status = 'ARRIVED'
        eta_share.save(update_fields=['status', 'updated_at'])

        channel_layer = get_channel_layer()
        ws_payload = {
            'type': 'eta_arrived',
            'data': ActiveEtaShareSerializer(eta_share, context={'request': request}).data
        }

        users_to_notify = list(eta_share.shared_with.all()) + [eta_share.sharer]
        for user_to_notify in users_to_notify:
                if user_to_notify:
                    group_name = f'user_{user_to_notify.id}_notifications'
                    async_to_sync(channel_layer.group_send)(
                        group_name,
                        {"type": "send_notification", "message": ws_payload}
                    )

        logger.info(f"ETA Share ID {eta_share.id} marked as arrived by {request.user.username}.")
        return Response({"message": "ETA share marked as arrived."}, status=status.HTTP_200_OK)
