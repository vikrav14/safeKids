from rest_framework import serializers as drf_serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, viewsets, permissions, generics
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate, login as django_login, logout as django_logout
from django.contrib.auth.models import User
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
    UpdateEtaLocationSerializer,
)
from .models import Child, LocationPoint, SafeZone, Alert, UserDevice, Message, ActiveEtaShare
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import timedelta
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.http import Http404
from django.utils.dateparse import parse_datetime
from django.db.models import Q
from rest_framework.pagination import PageNumberPagination
from django.conf import settings
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
import logging

logger = logging.getLogger(__name__)

# ====== HEALTH CHECK VIEWS ======
@api_view(['GET'])
def root_health_check(request):
    """Root health check endpoint"""
    return Response({
        "status": "active",
        "service": "SafeKids API",
        "version": "1.0.0",
        "endpoints": {
            "api_root": "/api/",
            "health_check": "/health-check/",
            "admin": "/admin/"
        }
    })

@api_view(['GET'])
def health_check(request):
    """Simple health check endpoint"""
    return Response({
        "status": "ok",
        "service": "SafeKids API",
        "version": "1.0.0"
    })

# ====== AUTHENTICATION VIEWS ======
@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    """
    Register a new user and return an authentication token.
    """
    serializer = UserRegistrationSerializer(data=request.data)
    if serializer.is_valid():
        try:
            user = serializer.save()
            token, created = Token.objects.get_or_create(user=user)
            return Response({
                'token': token.key,
                'user': UserSerializer(user).data
            }, status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.error(f"Registration error: {str(e)}")
            return Response({'error': 'Could not create user'}, 
                           status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
    """
    Authenticate a user and return an authentication token.
    """
    serializer = UserLoginSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    username = serializer.validated_data['username']
    password = serializer.validated_data['password']
    
    user = authenticate(request, username=username, password=password)
    
    if not user:
        logger.warning(f"Login failed for username: {username}")
        return Response({'error': 'Invalid credentials'}, 
                       status=status.HTTP_401_UNAUTHORIZED)
    
    # Create or get token
    token, created = Token.objects.get_or_create(user=user)
    
    return Response({
        'token': token.key,
        'user': UserSerializer(user).data
    }, status=status.HTTP_200_OK)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout(request):
    """
    Log out the current user and delete their token.
    """
    try:
        # Delete the token
        request.user.auth_token.delete()
        return Response({'message': 'Successfully logged out'}, 
                       status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
        return Response({'error': 'Could not log out'}, 
                       status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def current_user(request):
    """
    Get information about the currently authenticated user.
    """
    try:
        serializer = UserSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Current user error: {str(e)}")
        return Response({'error': 'Could not fetch user data'}, 
                       status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ====== SERIALIZERS FOR AUTHENTICATION ======
class UserLoginSerializer(drf_serializers.Serializer):
    username = drf_serializers.CharField(required=True)
    password = drf_serializers.CharField(required=True, style={'input_type': 'password'})

# ====== EXISTING APPLICATION VIEWS ======
# (All your original views below this point)
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
            201: OpenApiTypes.OBJECT,
            400: OpenApiTypes.OBJECT
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response({"message": "User registered successfully.", "user_id": user.id, "username": user.username}, 
                           status=status.HTTP_201_CREATED)
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

class LocationUpdateView(APIView):
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
        # Validate the overall request structure
        schema_serializer = LocationUpdateRequestSchemaSerializer(data=request.data)
        if not schema_serializer.is_valid():
            return Response(schema_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        validated_input = schema_serializer.validated_data
        child_id = validated_input.get('child_id')
        device_id = validated_input.get('device_id')
        battery_status = validated_input.get('battery_status')
        
        try: 
            child = get_object_or_404(Child, pk=child_id)
        except ValueError: 
            return Response({"error": "Invalid child_id format."}, status=status.HTTP_400_BAD_REQUEST)
        
        if not child.device_id or child.device_id != device_id:
            return Response({"error": "Device ID mismatch or not registered for this child."}, 
                           status=status.HTTP_403_FORBIDDEN)
        
        # Validate location-specific parts
        location_data = {
            'latitude': validated_input['latitude'],
            'longitude': validated_input['longitude'],
            'timestamp': validated_input['timestamp'],
        }
        if validated_input.get('accuracy') is not None:
            location_data['accuracy'] = validated_input['accuracy']
        
        location_serializer = LocationPointSerializer(data=location_data)
        if location_serializer.is_valid():
            # Create location point
            LocationPoint.objects.create(child=child, **location_serializer.validated_data)
            
            # Update child status
            if battery_status is not None:
                try:
                    child.battery_status = int(battery_status)
                except ValueError:
                    logger.warning(f"Invalid battery_status value for child {child.id}")
            child.last_seen_at = timezone.now()
            child.save(update_fields=['battery_status', 'last_seen_at'])
            
            # Notify parent via WebSocket
            channel_layer = get_channel_layer()
            parent_user_id = child.parent.id
            group_name = f'user_{parent_user_id}_notifications'
            
            location_data_for_ws = {
                'type': 'location_update',
                'child_id': child.id,
                'child_name': child.name,
                'latitude': float(location_serializer.validated_data['latitude']),
                'longitude': float(location_serializer.validated_data['longitude']),
                'timestamp': location_serializer.validated_data['timestamp'].isoformat(),
                'accuracy': float(location_serializer.validated_data.get('accuracy')) 
                            if location_serializer.validated_data.get('accuracy') is not None else None,
                'battery_status': child.battery_status
            }
            
            async_to_sync(channel_layer.group_send)(
                group_name, 
                {"type": "location.update", "payload": location_data_for_ws}
            )
            
            # Check safe zones
            parent_user = child.parent
            current_lat = location_serializer.validated_data['latitude']
            current_lon = location_serializer.validated_data['longitude']
            
            active_safe_zones = SafeZone.objects.filter(owner=parent_user, is_active=True)
            ALERT_COOLDOWN_MINUTES = 10
            
            for zone in active_safe_zones:
                distance_m = distance_in_meters(current_lat, current_lon, zone.latitude, zone.longitude)
                currently_inside = distance_m <= zone.radius
                
                # Get last alert for this zone
                last_alert = Alert.objects.filter(
                    recipient=parent_user, 
                    child=child, 
                    safe_zone_id=zone.id
                ).order_by('-timestamp').first()
                
                previous_inside = False
                alert_on_cooldown = False
                
                if last_alert:
                    if last_alert.alert_type == 'ENTERED_ZONE':
                        previous_inside = True
                    if (timezone.now() - last_alert.timestamp) < timedelta(minutes=ALERT_COOLDOWN_MINUTES):
                        alert_on_cooldown = True
                
                new_alert_type = None
                alert_message = ""
                
                if currently_inside and not previous_inside and not alert_on_cooldown:
                    new_alert_type = 'ENTERED_ZONE'
                    alert_message = f"{child.name} has entered {zone.name}."
                elif not currently_inside and previous_inside and not alert_on_cooldown:
                    new_alert_type = 'LEFT_ZONE'
                    alert_message = f"{child.name} has left {zone.name}."
                
                if new_alert_type:
                    alert = Alert.objects.create(
                        recipient=parent_user,
                        child=child,
                        alert_type=new_alert_type,
                        message=alert_message,
                        safe_zone_id=zone.id
                    )
                    
                    # Send FCM notification
                    push_title = f"Safe Zone Alert: {child.name}"
                    push_data = {
                        'alert_type': new_alert_type,
                        'child_id': str(child.id),
                        'child_name': child.name,
                        'zone_id': str(zone.id),
                        'zone_name': zone.name,
                        'alert_id': str(alert.id)
                    }
                    send_fcm_to_user(user=parent_user, title=push_title, body=alert_message, data=push_data)
                    
                    # Send WebSocket notification
                    ws_payload = {
                        'type': 'safezone_alert',
                        'alert_id': alert.id,
                        'child_id': child.id,
                        'child_name': child.name,
                        'zone_id': zone.id,
                        'zone_name': zone.name,
                        'alert_type': new_alert_type,
                        'message': alert_message,
                        'timestamp': alert.timestamp.isoformat()
                    }
                    async_to_sync(channel_layer.group_send)(
                        group_name, 
                        {"type": "send_notification", "message": ws_payload}
                    )
            
            # Check battery status
            LOW_BATTERY_THRESHOLD = 20
            LOW_BATTERY_ALERT_COOLDOWN_MINUTES = 60
            
            if battery_status is not None:
                try:
                    battery_level = int(battery_status)
                    if battery_level < LOW_BATTERY_THRESHOLD:
                        last_alert = Alert.objects.filter(
                            recipient=parent_user,
                            child=child,
                            alert_type='LOW_BATTERY'
                        ).order_by('-timestamp').first()
                        
                        send_alert = True
                        if last_alert:
                            if (timezone.now() - last_alert.timestamp) < timedelta(minutes=LOW_BATTERY_ALERT_COOLDOWN_MINUTES):
                                send_alert = False
                        
                        if send_alert:
                            alert_message = f"{child.name}'s phone battery is low: {battery_level}%."
                            alert = Alert.objects.create(
                                recipient=parent_user,
                                child=child,
                                alert_type='LOW_BATTERY',
                                message=alert_message
                            )
                            
                            # Send FCM notification
                            push_title = f"Low Battery Warning: {child.name}"
                            push_data = {
                                'alert_type': 'LOW_BATTERY',
                                'child_id': str(child.id),
                                'child_name': child.name,
                                'battery_level': str(battery_level),
                                'alert_id': str(alert.id)
                            }
                            send_fcm_to_user(user=parent_user, title=push_title, body=alert_message, data=push_data)
                            
                            # Send WebSocket notification
                            ws_payload = {
                                'type': 'low_battery_alert',
                                'alert_id': alert.id,
                                'child_id': child.id,
                                'child_name': child.name,
                                'battery_level': battery_level,
                                'message': alert_message,
                                'timestamp': alert.timestamp.isoformat()
                            }
                            async_to_sync(channel_layer.group_send)(
                                group_name, 
                                {"type": "send_notification", "message": ws_payload}
                            )
                except ValueError:
                    logger.warning(f"Invalid battery_status value for child {child.id}")
            
            return Response(
                {"message": "Location updated successfully. Safe zone and battery checks performed."},
                status=status.HTTP_201_CREATED
            )
        
        return Response(location_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ChildCurrentLocationView(generics.RetrieveAPIView):
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

class ChildLocationHistoryView(generics.ListAPIView):
    """
    Retrieves the location history for a specific child.
    """
    serializer_class = LocationPointSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination

    @extend_schema(
        summary="Retrieve Child Location History",
        parameters=[
            OpenApiParameter(
                name='start_timestamp', 
                type=OpenApiTypes.DATETIME, 
                location=OpenApiParameter.QUERY,
                required=False, 
                description='Filter history from this ISO 8601 timestamp'
            ),
            OpenApiParameter(
                name='end_timestamp', 
                type=OpenApiTypes.DATETIME, 
                location=OpenApiParameter.QUERY,
                required=False, 
                description='Filter history up to this ISO 8601 timestamp'
            )
        ]
    )
    def get_queryset(self):
        child_id = self.kwargs.get('child_id')
        child = get_object_or_404(Child, pk=child_id, parent=self.request.user)
        queryset = LocationPoint.objects.filter(child=child).order_by('timestamp')
        
        # Apply time filters
        start_timestamp = self.request.query_params.get('start_timestamp')
        end_timestamp = self.request.query_params.get('end_timestamp')
        
        if start_timestamp:
            try:
                start = parse_datetime(start_timestamp)
                if start:
                    if timezone.is_naive(start):
                        start = timezone.make_aware(start, timezone.get_default_timezone())
                    queryset = queryset.filter(timestamp__gte=start)
            except (ValueError, TypeError):
                pass
                
        if end_timestamp:
            try:
                end = parse_datetime(end_timestamp)
                if end:
                    if timezone.is_naive(end):
                        end = timezone.make_aware(end, timezone.get_default_timezone())
                    queryset = queryset.filter(timestamp__lte=end)
            except (ValueError, TypeError):
                pass
                
        return queryset

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

class SOSAlertView(APIView):
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
        serializer = SOSAlertSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        validated_data = serializer.validated_data
        child_id = validated_data.get('child_id')
        device_id = validated_data.get('device_id')
        latitude = validated_data.get('latitude')
        longitude = validated_data.get('longitude')
        
        try:
            child = get_object_or_404(Child, pk=child_id)
        except Http404:
            return Response({"error": "Child not found."}, status=status.HTTP_404_NOT_FOUND)
        
        if not child.device_id or child.device_id != device_id:
            return Response({"error": "Device ID mismatch or not registered for this child."}, 
                           status=status.HTTP_403_FORBIDDEN)
        
        parent_user = child.parent
        message_parts = [f"SOS triggered by {child.name}."]
        location_known = False
        
        if latitude is not None and longitude is not None:
            message_parts.append(f"Current location: lat {latitude}, lon {longitude}.")
            location_known = True
        else:
            last_location = LocationPoint.objects.filter(child=child).order_by('-timestamp').first()
            if last_location:
                message_parts.append(
                    f"Last known location (at {last_location.timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')}): "
                    f"lat {last_location.latitude}, lon {last_location.longitude}."
                )
                location_known = True
        
        if not location_known:
            message_parts.append("Current location not available.")
        
        sos_message = " ".join(message_parts)
        alert = Alert.objects.create(
            recipient=parent_user,
            child=child,
            alert_type='SOS',
            message=sos_message
        )
        
        # Send FCM notification
        push_title = f"SOS Alert: {child.name}"
        push_data = {
            'alert_type': 'SOS',
            'child_id': str(child.id),
            'child_name': child.name,
            'alert_id': str(alert.id)
        }
        
        if latitude is not None and longitude is not None:
            push_data['latitude'] = str(latitude)
            push_data['longitude'] = str(longitude)
        elif last_location:
            push_data['latitude'] = str(last_location.latitude)
            push_data['longitude'] = str(last_location.longitude)
            push_data['location_timestamp'] = last_location.timestamp.isoformat()
        
        send_fcm_to_user(user=parent_user, title=push_title, body=sos_message, data=push_data)
        
        return Response(
            {"message": "SOS alert successfully triggered, recorded, and notification sent."},
            status=status.HTTP_201_CREATED
        )

@extend_schema(summary="List User Alerts")
class AlertListView(generics.ListAPIView):
    """
    Lists alerts for the authenticated user.
    """
    serializer_class = AlertSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination
    
    def get_queryset(self): 
        return Alert.objects.filter(recipient=self.request.user).order_by('-timestamp')

class DeviceRegistrationView(APIView):
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
        serializer = DeviceRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            device_token = serializer.validated_data['device_token']
            device_type = serializer.validated_data.get('device_type')
            
            # Deactivate token for other users
            UserDevice.objects.filter(device_token=device_token).exclude(user=request.user).update(is_active=False)
            
            # Create or update device
            user_device, created = UserDevice.objects.update_or_create(
                user=request.user,
                device_token=device_token,
                defaults={'is_active': True, 'device_type': device_type}
            )
            
            if created:
                return Response(
                    {"message": "Device registered successfully."},
                    status=status.HTTP_201_CREATED
                )
            else:
                return Response(
                    {"message": "Device registration updated successfully."},
                    status=status.HTTP_200_OK
                )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ChildCheckInView(APIView):
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
        serializer = CheckInSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        validated_data = serializer.validated_data
        child_id = validated_data['child_id']
        device_id = validated_data['device_id']
        
        try:
            child = get_object_or_404(Child, pk=child_id, is_active=True)
        except Http404:
            return Response({"error": "Child not found or not active."}, status=status.HTTP_404_NOT_FOUND)
        
        if not child.device_id or child.device_id != device_id:
            return Response(
                {"error": "Device ID mismatch or not registered for this child."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        parent_user = child.parent
        
        # Create location point
        LocationPoint.objects.create(
            child=child,
            latitude=validated_data['latitude'],
            longitude=validated_data['longitude'],
            timestamp=validated_data['client_timestamp_iso']
        )
        
        # Create alert
        check_in_type = validated_data['check_in_type'].replace('_', ' ').title()
        location_desc = validated_data.get('location_name') or f"coordinates {validated_data['latitude']}, {validated_data['longitude']}"
        
        if validated_data.get('custom_message'):
            alert_message = f"{child.name} checked in from {location_desc}: \"{validated_data['custom_message']}\""
        else:
            alert_message = f"{child.name} {check_in_type} from {location_desc}."
        
        alert = Alert.objects.create(
            recipient=parent_user,
            child=child,
            alert_type='CHECK_IN',
            message=alert_message
        )
        
        # Send FCM notification
        push_title = f"Check-In: {child.name}"
        push_data = {
            'alert_type': 'CHECK_IN',
            'child_id': str(child.id),
            'child_name': child.name,
            'check_in_type': validated_data['check_in_type'],
            'message': alert_message,
            'latitude': str(validated_data['latitude']),
            'longitude': str(validated_data['longitude']),
            'location_name': validated_data.get('location_name', ''),
            'alert_id': str(alert.id),
            'timestamp': validated_data['client_timestamp_iso'].isoformat()
        }
        send_fcm_to_user(user=parent_user, title=push_title, body=alert_message, data=push_data)
        
        # Send WebSocket notification
        channel_layer = get_channel_layer()
        group_name = f'user_{parent_user.id}_notifications'
        ws_payload = {
            'type': 'child_check_in',
            'alert_id': str(alert.id),
            'data': push_data
        }
        async_to_sync(channel_layer.group_send)(
            group_name, 
            {"type": "send_notification", "message": ws_payload}
        )
        
        logger.info(f"Processed check-in for child {child.name}, parent {parent_user.username}")
        return Response(
            {"message": "Check-in processed successfully."},
            status=status.HTTP_201_CREATED
        )

class SendMessageView(APIView):
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
        serializer = MessageSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            receiver_id = serializer.validated_data['receiver_id']
            content = serializer.validated_data['content']
            
            try:
                receiver = User.objects.get(pk=receiver_id)
            except User.DoesNotExist:
                return Response({"error": "Recipient not found."}, status=status.HTTP_404_NOT_FOUND)
            
            # Create message
            message = Message.objects.create(
                sender=request.user,
                receiver=receiver,
                content=content
            )
            
            # Serialize for response
            response_serializer = MessageSerializer(message)
            
            # Send WebSocket notification
            channel_layer = get_channel_layer()
            recipient_group = f'user_{receiver.id}_notifications'
            ws_payload = {
                'type': 'new_message',
                'data': response_serializer.data
            }
            async_to_sync(channel_layer.group_send)(
                recipient_group, 
                {"type": "new.chat.message", "payload": ws_payload}
            )
            
            # Send FCM notification
            sender_name = request.user.get_full_name() or request.user.username
            preview = (content[:70] + '...') if len(content) > 70 else content
            fcm_data = {
                'type': 'new_message',
                'message_id': str(message.id),
                'sender_id': str(request.user.id),
                'sender_name': sender_name,
                'conversation_with_user_id': str(request.user.id),
                'content_preview': preview
            }
            send_fcm_to_user(
                user=receiver,
                title=f"New message from {sender_name}",
                body=preview,
                data=fcm_data
            )
            
            logger.info(f"Message from {request.user.username} to {receiver.username} sent")
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

class ConversationListView(APIView):
    """
    Lists recent conversations for the authenticated user.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(summary="List User Conversations", responses={200: OpenApiTypes.OBJECT})
    def get(self, request, *args, **kwargs):
        user = request.user
        
        # Get distinct users with whom the current user has exchanged messages
        sent_to = User.objects.filter(received_messages__sender=user).distinct()
        received_from = User.objects.filter(sent_messages__receiver=user).distinct()
        contacts = (sent_to | received_from).distinct()
        
        conversations = []
        for contact in contacts:
            last_message = Message.objects.filter(
                Q(sender=user, receiver=contact) | Q(sender=contact, receiver=user)
            ).order_by('-timestamp').first()
            
            if last_message:
                unread_count = Message.objects.filter(
                    sender=contact, 
                    receiver=user,
                    is_read=False
                ).count()
                
                conversations.append({
                    'contact_user_id': contact.id,
                    'contact_details': MessageUserSerializer(contact).data,
                    'last_message': MessageSerializer(last_message).data,
                    'unread_count': unread_count,
                    'last_message_timestamp': last_message.timestamp
                })
        
        # Sort by most recent message
        conversations.sort(key=lambda c: c['last_message_timestamp'], reverse=True)
        return Response(conversations, status=status.HTTP_200_OK)

@extend_schema(summary="Get Message History with User")
class MessageHistoryView(generics.ListAPIView):
    """
    Retrieves the message history between the authenticated user and another specified user.
    """
    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        other_user_id = self.kwargs.get('other_user_id')
        user = self.request.user
        
        if str(other_user_id) == str(user.id):
            return Message.objects.none()
        
        try:
            User.objects.get(pk=other_user_id)
        except User.DoesNotExist:
            return Message.objects.none()
        
        return Message.objects.filter(
            Q(sender=user, receiver_id=other_user_id) |
            Q(sender_id=other_user_id, receiver=user)
        ).order_by('timestamp')

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
        serializer = MarkMessagesAsReadRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        other_user_id = serializer.validated_data['other_user_id']
        
        try:
            other_user = User.objects.get(pk=other_user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        
        # Mark messages as read
        updated_count = Message.objects.filter(
            sender=other_user,
            receiver=request.user,
            is_read=False
        ).update(is_read=True)
        
        if updated_count > 0:
            # Send read receipt via WebSocket
            channel_layer = get_channel_layer()
            sender_group = f'user_{other_user.id}_notifications'
            receipt = {
                'type': 'messages_read',
                'reader_id': str(request.user.id),
                'conversation_with_user_id': str(request.user.id),
                'read_at_timestamp': timezone.now().isoformat()
            }
            async_to_sync(channel_layer.group_send)(
                sender_group, 
                {"type": "messages.read.receipt", "payload": receipt}
            )
            logger.info(f"Sent read receipt to user {other_user.username}")
        
        return Response(
            {"message": f"{updated_count} messages marked as read."},
            status=status.HTTP_200_OK
        )

class ChildSendMessageRequestSerializer(drf_serializers.Serializer):
    child_id = drf_serializers.IntegerField(help_text="ID of the child sending the message.")
    device_id = drf_serializers.CharField(max_length=255, help_text="Device ID for authentication.")
    content = drf_serializers.CharField(help_text="Text content of the message.")

class ChildSendMessageView(APIView):
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
        serializer = ChildSendMessageRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        validated_data = serializer.validated_data
        child_id = validated_data['child_id']
        device_id = validated_data['device_id']
        content = validated_data['content']
        
        if not content.strip():
            return Response({"error": "Message content cannot be empty."}, 
                           status=status.HTTP_400_BAD_REQUEST)
        
        try:
            child = get_object_or_404(Child, pk=child_id, is_active=True)
        except Http404:
            return Response({"error": "Child not found or not active."}, 
                           status=status.HTTP_404_NOT_FOUND)
        
        if not child.device_id or child.device_id != device_id:
            return Response(
                {"error": "Device ID mismatch or not registered."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if not child.proxy_user:
            logger.error(f"Child {child.id} has no proxy user")
            return Response(
                {"error": "Messaging not enabled for this child account."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        parent_user = child.parent
        sender_user = child.proxy_user
        
        # Create message
        message = Message.objects.create(
            sender=sender_user,
            receiver=parent_user,
            content=content
        )
        
        # Serialize for response
        response_serializer = MessageSerializer(message)
        
        # Send WebSocket notification
        channel_layer = get_channel_layer()
        parent_group = f'user_{parent_user.id}_notifications'
        ws_payload = {
            'type': 'new_message',
            'data': response_serializer.data
        }
        async_to_sync(channel_layer.group_send)(
            parent_group, 
            {"type": "new.chat.message", "payload": ws_payload}
        )
        
        # Send FCM notification
        preview = (content[:70] + '...') if len(content) > 70 else content
        fcm_data = {
            'type': 'new_message',
            'message_id': str(message.id),
            'sender_id': str(sender_user.id),
            'sender_name': child.name,
            'conversation_with_user_id': str(sender_user.id),
            'child_sender_actual_id': str(child.id),
            'content_preview': preview
        }
        send_fcm_to_user(
            user=parent_user,
            title=f"New message from {child.name}",
            body=preview,
            data=fcm_data
        )
        
        logger.info(f"Message from Child {child.name} to Parent {parent_user.username} sent")
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

@extend_schema(summary="Start ETA Share")
class StartEtaShareView(APIView):
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
        serializer = StartEtaShareSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        validated_data = serializer.validated_data
        sharer = request.user
        
        # Calculate ETA
        calculated_eta = None
        try:
            distance_m = distance_in_meters(
                validated_data['current_latitude'],
                validated_data['current_longitude'],
                validated_data['destination_latitude'],
                validated_data['destination_longitude']
            )
            
            speed_kmh = float(getattr(settings, 'DEFAULT_ETA_SPEED_KMH', 30))
            if speed_kmh <= 0:
                speed_kmh = 30
                
            duration_hours = (distance_m / 1000.0) / speed_kmh
            duration_seconds = duration_hours * 3600
            calculated_eta = timezone.now() + timedelta(seconds=duration_seconds)
        except Exception as e:
            logger.error(f"Error calculating ETA: {e}", exc_info=True)
        
        # Create ETA share
        eta_share = ActiveEtaShare.objects.create(
            sharer=sharer,
            destination_name=validated_data.get('destination_name'),
            destination_latitude=validated_data['destination_latitude'],
            destination_longitude=validated_data['destination_longitude'],
            current_latitude=validated_data['current_latitude'],
            current_longitude=validated_data['current_longitude'],
            calculated_eta=calculated_eta,
            status='ACTIVE'
        )
        
        # Add shared users
        if validated_data.get('shared_with_user_ids'):
            shared_users = User.objects.filter(pk__in=validated_data['shared_with_user_ids'])
            eta_share.shared_with.set(shared_users)
        
        # Serialize response
        output_serializer = ActiveEtaShareSerializer(eta_share, context={'request': request})
        response_data = output_serializer.data
        
        # Send notifications
        channel_layer = get_channel_layer()
        ws_payload = {
            'type': 'eta_started',
            'data': response_data
        }
        
        fcm_title = f"ETA Share Started by {sharer.get_full_name() or sharer.username}"
        fcm_body = f"Tracking {sharer.get_full_name() or sharer.username} to {validated_data.get('destination_name', 'destination')}. ETA: {calculated_eta.strftime('%I:%M %p') if calculated_eta else 'N/A'}"
        fcm_data = {
            'type': 'eta_started',
            'share_id': str(eta_share.id),
            'sharer_id': str(sharer.id),
            'sharer_name': sharer.get_full_name() or sharer.username,
            'destination_name': eta_share.destination_name,
            'eta': eta_share.calculated_eta.isoformat() if eta_share.calculated_eta else None
        }
        
        for user in eta_share.shared_with.all():
            # Send FCM
            send_fcm_to_user(user=user, title=fcm_title, body=fcm_body, data=fcm_data)
            
            # Send WebSocket
            user_group = f'user_{user.id}_notifications'
            async_to_sync(channel_layer.group_send)(
                user_group, 
                {"type": "send_notification", "message": ws_payload}
            )
        
        logger.info(f"ETA Share ID {eta_share.id} started by {sharer.username}")
        return Response(response_data, status=status.HTTP_201_CREATED)

@extend_schema(summary="Update ETA Location")
class UpdateEtaLocationView(APIView):
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
        try:
            eta_share = get_object_or_404(ActiveEtaShare, pk=share_id, status='ACTIVE')
        except Http404:
            return Response({"error": "Active ETA share not found."}, 
                           status=status.HTTP_404_NOT_FOUND)
        
        if eta_share.sharer != request.user:
            return Response(
                {"error": "You do not have permission to update this ETA share."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = UpdateEtaLocationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        validated_data = serializer.validated_data
        
        # Update location
        eta_share.current_latitude = validated_data['current_latitude']
        eta_share.current_longitude = validated_data['current_longitude']
        
        # Recalculate ETA
        try:
            distance_m = distance_in_meters(
                validated_data['current_latitude'],
                validated_data['current_longitude'],
                eta_share.destination_latitude,
                eta_share.destination_longitude
            )
            
            speed_kmh = float(getattr(settings, 'DEFAULT_ETA_SPEED_KMH', 30))
            if speed_kmh <= 0:
                speed_kmh = 30
                
            duration_hours = (distance_m / 1000.0) / speed_kmh
            duration_seconds = duration_hours * 3600
            eta_share.calculated_eta = timezone.now() + timedelta(seconds=duration_seconds)
        except Exception as e:
            logger.error(f"Error recalculating ETA: {e}", exc_info=True)
            eta_share.calculated_eta = None
        
        eta_share.save()
        
        # Serialize response
        output_serializer = ActiveEtaShareSerializer(eta_share, context={'request': request})
        response_data = output_serializer.data
        
        # Send notifications
        channel_layer = get_channel_layer()
        ws_payload = {
            'type': 'eta_updated',
            'data': response_data
        }
        
        # Notify sharer and all shared users
        users_to_notify = list(eta_share.shared_with.all()) + [eta_share.sharer]
        for user in users_to_notify:
            if user:
                user_group = f'user_{user.id}_notifications'
                async_to_sync(channel_layer.group_send)(
                    user_group, 
                    {"type": "send_notification", "message": ws_payload}
                )
        
        logger.info(f"ETA Share ID {eta_share.id} updated by {request.user.username}")
        return Response(response_data, status=status.HTTP_200_OK)

@extend_schema(summary="List Active ETA Shares")
class ListActiveEtaSharesView(generics.ListAPIView):
    """
    Lists active ETA shares relevant to the authenticated user.
    """
    serializer_class = ActiveEtaShareSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
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

    @extend_schema(responses={200: SimpleMessageResponseSerializer, 403: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT})
    def post(self, request, share_id, *args, **kwargs):
        try:
            eta_share = get_object_or_404(ActiveEtaShare, pk=share_id, status='ACTIVE')
        except Http404:
            return Response({"error": "Active ETA share not found."}, 
                           status=status.HTTP_404_NOT_FOUND)
        
        if eta_share.sharer != request.user:
            return Response(
                {"error": "Permission denied."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Update status
        eta_share.status = 'CANCELLED'
        eta_share.save(update_fields=['status', 'updated_at'])
        
        # Send notifications
        channel_layer = get_channel_layer()
        ws_payload = {
            'type': 'eta_cancelled',
            'data': ActiveEtaShareSerializer(eta_share, context={'request': request}).data
        }
        
        # Notify sharer and all shared users
        users_to_notify = list(eta_share.shared_with.all()) + [eta_share.sharer]
        for user in users_to_notify:
            if user:
                user_group = f'user_{user.id}_notifications'
                async_to_sync(channel_layer.group_send)(
                    user_group, 
                    {"type": "send_notification", "message": ws_payload}
                )
        
        logger.info(f"ETA Share ID {eta_share.id} cancelled by {request.user.username}")
        return Response(
            {"message": "ETA share cancelled successfully."},
            status=status.HTTP_200_OK
        )

@extend_schema(summary="Mark ETA Share as Arrived")
class ArrivedEtaShareView(APIView):
    """
    Allows the sharer to mark an active ETA share as 'ARRIVED'.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses={200: SimpleMessageResponseSerializer, 403: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT})
    def post(self, request, share_id, *args, **kwargs):
        try:
            eta_share = get_object_or_404(ActiveEtaShare, pk=share_id, status='ACTIVE')
        except Http404:
            return Response({"error": "Active ETA share not found."}, 
                           status=status.HTTP_404_NOT_FOUND)
        
        if eta_share.sharer != request.user:
            return Response(
                {"error": "Permission denied."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Update status
        eta_share.status = 'ARRIVED'
        eta_share.save(update_fields=['status', 'updated_at'])
        
        # Send notifications
        channel_layer = get_channel_layer()
        ws_payload = {
            'type': 'eta_arrived',
            'data': ActiveEtaShareSerializer(eta_share, context={'request': request}).data
        }
        
        # Notify sharer and all shared users
        users_to_notify = list(eta_share.shared_with.all()) + [eta_share.sharer]
        for user in users_to_notify:
            if user:
                user_group = f'user_{user.id}_notifications'
                async_to_sync(channel_layer.group_send)(
                    user_group, 
                    {"type": "send_notification", "message": ws_payload}
                )
        
        logger.info(f"ETA Share ID {eta_share.id} marked as arrived by {request.user.username}")
        return Response(
            {"message": "ETA share marked as arrived."},
            status=status.HTTP_200_OK
        )