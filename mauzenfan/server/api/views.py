from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, viewsets, permissions, generics
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
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
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from rest_framework import serializers as drf_serializers

import logging

logger = logging.getLogger(__name__)

# ====== HEALTH CHECK VIEW ======
@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    return Response({
        "status": "ok",
        "service": "SafeKids API",
        "version": "1.0.0"
    })

# --- Schema-only Serializers ---
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

# --- Views ---
class RegistrationView(APIView):
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
            return Response({
                "message": "User registered successfully.",
                "user_id": user.id,
                "username": user.username
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@extend_schema(
    summary="Manage Child Profiles",
    description="Allows authenticated parents to manage child profiles"
)
class ChildViewSet(viewsets.ModelViewSet):
    serializer_class = ChildSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Child.objects.filter(parent=self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(parent=self.request.user)

class LocationUpdateView(APIView):
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
        child_id = validated_input.get('child_id')
        device_id = validated_input.get('device_id')
        
        try:
            child = get_object_or_404(Child, pk=child_id)
        except Http404:
            return Response({"error": "Child not found."}, status=status.HTTP_404_NOT_FOUND)
        
        if not child.device_id or child.device_id != device_id:
            return Response({"error": "Device ID mismatch or not registered."}, status=status.HTTP_403_FORBIDDEN)
        
        location_data = {
            'latitude': validated_input['latitude'],
            'longitude': validated_input['longitude'],
            'timestamp': validated_input['timestamp'],
        }
        if validated_input.get('accuracy') is not None:
            location_data['accuracy'] = validated_input['accuracy']
        
        location_serializer = LocationPointSerializer(data=location_data)
        if location_serializer.is_valid():
            LocationPoint.objects.create(child=child, **location_serializer.validated_data)
            
            # Update child status
            battery_status = validated_input.get('battery_status')
            if battery_status is not None:
                child.battery_status = battery_status
            child.last_seen_at = timezone.now()
            child.save(update_fields=['battery_status', 'last_seen_at'])
            
            # Notify via WebSocket
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
                'accuracy': float(location_serializer.validated_data.get('accuracy')) if location_serializer.validated_data.get('accuracy') is not None else None,
                'battery_status': child.battery_status
            }
            async_to_sync(channel_layer.group_send)(
                group_name,
                {"type": "location.update", "payload": location_data_for_ws}
            )
            
            # Safe zone checks
            parent_user = child.parent
            current_lat = location_serializer.validated_data['latitude']
            current_lon = location_serializer.validated_data['longitude']
            active_safe_zones = SafeZone.objects.filter(owner=parent_user, is_active=True)
            ALERT_COOLDOWN_MINUTES = 10
            
            for zone in active_safe_zones:
                distance_m = distance_in_meters(current_lat, current_lon, zone.latitude, zone.longitude)
                currently_inside = distance_m <= zone.radius
                
                last_alert = Alert.objects.filter(
                    recipient=parent_user,
                    child=child,
                    safe_zone_id=zone.id
                ).order_by('-timestamp').first()
                
                prev_status_inside = False
                alert_cooldown = False
                if last_alert:
                    if last_alert.alert_type == 'ENTERED_ZONE':
                        prev_status_inside = True
                    if (timezone.now() - last_alert.timestamp) < timedelta(minutes=ALERT_COOLDOWN_MINUTES):
                        alert_cooldown = True
                
                new_alert_type = None
                if currently_inside and not prev_status_inside and not alert_cooldown:
                    new_alert_type = 'ENTERED_ZONE'
                    alert_message = f"{child.name} has entered {zone.name}."
                elif not currently_inside and prev_status_inside and not alert_cooldown:
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
                    # Send FCM and WebSocket notifications
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
            
            # Battery check
            LOW_BATTERY_THRESHOLD = 20
            LOW_BATTERY_ALERT_COOLDOWN_MINUTES = 60
            if battery_status is not None and battery_status < LOW_BATTERY_THRESHOLD:
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
                    alert_message = f"{child.name}'s phone battery is low: {battery_status}%."
                    alert = Alert.objects.create(
                        recipient=parent_user,
                        child=child,
                        alert_type='LOW_BATTERY',
                        message=alert_message
                    )
                    push_title = f"Low Battery: {child.name}"
                    push_data = {
                        'alert_type': 'LOW_BATTERY',
                        'child_id': str(child.id),
                        'child_name': child.name,
                        'battery_level': str(battery_status),
                        'alert_id': str(alert.id)
                    }
                    send_fcm_to_user(user=parent_user, title=push_title, body=alert_message, data=push_data)
                    ws_payload = {
                        'type': 'low_battery_alert',
                        'alert_id': alert.id,
                        'child_id': child.id,
                        'child_name': child.name,
                        'battery_level': battery_status,
                        'message': alert_message,
                        'timestamp': alert.timestamp.isoformat()
                    }
                    async_to_sync(channel_layer.group_send)(
                        group_name,
                        {"type": "send_notification", "message": ws_payload}
                    )
            
            return Response({"message": "Location updated and checks performed."}, status=status.HTTP_201_CREATED)
        
        return Response(location_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ChildCurrentLocationView(generics.RetrieveAPIView):
    serializer_class = LocationPointSerializer
    permission_classes = [IsAuthenticated]
    
    def get_object(self):
        child_id = self.kwargs.get('child_id')
        child = get_object_or_404(Child, pk=child_id, parent=self.request.user)
        location = LocationPoint.objects.filter(child=child).order_by('-timestamp').first()
        if not location:
            raise Http404("No location data found")
        return location

class ChildLocationHistoryView(generics.ListAPIView):
    serializer_class = LocationPointSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination

    @extend_schema(
        parameters=[
            OpenApiParameter(name='start_timestamp', type=OpenApiTypes.DATETIME, required=False),
            OpenApiParameter(name='end_timestamp', type=OpenApiTypes.DATETIME, required=False)
        ]
    )
    def get_queryset(self):
        child_id = self.kwargs.get('child_id')
        child = get_object_or_404(Child, pk=child_id, parent=self.request.user)
        queryset = LocationPoint.objects.filter(child=child).order_by('timestamp')
        
        start = self.request.query_params.get('start_timestamp')
        end = self.request.query_params.get('end_timestamp')
        
        if start:
            try:
                start_dt = parse_datetime(start)
                if start_dt:
                    if timezone.is_naive(start_dt):
                        start_dt = timezone.make_aware(start_dt)
                    queryset = queryset.filter(timestamp__gte=start_dt)
            except (ValueError, TypeError):
                pass
        
        if end:
            try:
                end_dt = parse_datetime(end)
                if end_dt:
                    if timezone.is_naive(end_dt):
                        end_dt = timezone.make_aware(end_dt)
                    queryset = queryset.filter(timestamp__lte=end_dt)
            except (ValueError, TypeError):
                pass
        
        return queryset

@extend_schema(summary="Manage Safe Zones")
class SafeZoneViewSet(viewsets.ModelViewSet):
    serializer_class = SafeZoneSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return SafeZone.objects.filter(owner=self.request.user).order_by('-created_at')
    
    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

class SOSAlertView(APIView):
    permission_classes = [AllowAny]
    serializer_class = SOSAlertSerializer

    @extend_schema(
        request=SOSAlertSerializer,
        responses={201: SimpleMessageResponseSerializer, 400: OpenApiTypes.OBJECT, 403: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT}
    )
    def post(self, request, *args, **kwargs):
        serializer = SOSAlertSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        child_id = data['child_id']
        device_id = data['device_id']
        
        try:
            child = get_object_or_404(Child, pk=child_id)
        except Http404:
            return Response({"error": "Child not found"}, status=status.HTTP_404_NOT_FOUND)
        
        if not child.device_id or child.device_id != device_id:
            return Response({"error": "Device ID mismatch"}, status=status.HTTP_403_FORBIDDEN)
        
        parent = child.parent
        message = f"SOS triggered by {child.name}."
        location_info = ""
        
        if data.get('latitude') and data.get('longitude'):
            location_info = f" Current location: {data['latitude']}, {data['longitude']}"
        else:
            last_loc = LocationPoint.objects.filter(child=child).order_by('-timestamp').first()
            if last_loc:
                location_info = f" Last location: {last_loc.latitude}, {last_loc.longitude} ({last_loc.timestamp})"
        
        full_message = message + location_info
        alert = Alert.objects.create(
            recipient=parent,
            child=child,
            alert_type='SOS',
            message=full_message
        )
        
        push_title = f"SOS: {child.name}"
        push_data = {
            'alert_type': 'SOS',
            'child_id': str(child.id),
            'child_name': child.name,
            'alert_id': str(alert.id)
        }
        
        if data.get('latitude') and data.get('longitude'):
            push_data['latitude'] = str(data['latitude'])
            push_data['longitude'] = str(data['longitude'])
        
        send_fcm_to_user(user=parent, title=push_title, body=full_message, data=push_data)
        return Response({"message": "SOS alert processed"}, status=status.HTTP_201_CREATED)

@extend_schema(summary="List User Alerts")
class AlertListView(generics.ListAPIView):
    serializer_class = AlertSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination
    
    def get_queryset(self):
        return Alert.objects.filter(recipient=self.request.user).order_by('-timestamp')

class DeviceRegistrationView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = DeviceRegistrationSerializer

    @extend_schema(
        request=DeviceRegistrationSerializer,
        responses={200: SimpleMessageResponseSerializer, 201: SimpleMessageResponseSerializer, 400: OpenApiTypes.OBJECT}
    )
    def post(self, request, *args, **kwargs):
        serializer = DeviceRegistrationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        token = data['device_token']
        device_type = data.get('device_type')
        
        # Deactivate token for other users
        UserDevice.objects.filter(device_token=token).exclude(user=request.user).update(is_active=False)
        
        # Update or create for current user
        device, created = UserDevice.objects.update_or_create(
            user=request.user,
            device_token=token,
            defaults={'is_active': True, 'device_type': device_type}
        )
        
        status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        message = "Device registered" if created else "Device updated"
        return Response({"message": message}, status=status_code)

class ChildCheckInView(APIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = CheckInSerializer

    @extend_schema(
        request=CheckInSerializer,
        responses={201: SimpleMessageResponseSerializer, 400: OpenApiTypes.OBJECT, 403: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT}
    )
    def post(self, request, *args, **kwargs):
        serializer = CheckInSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        child_id = data['child_id']
        device_id = data['device_id']
        
        try:
            child = get_object_or_404(Child, pk=child_id, is_active=True)
        except Http404:
            return Response({"error": "Child not found"}, status=status.HTTP_404_NOT_FOUND)
        
        if not child.device_id or child.device_id != device_id:
            return Response({"error": "Device ID mismatch"}, status=status.HTTP_403_FORBIDDEN)
        
        # Create location point
        LocationPoint.objects.create(
            child=child,
            latitude=data['latitude'],
            longitude=data['longitude'],
            timestamp=data['client_timestamp_iso']
        )
        
        # Create alert
        checkin_type = data['check_in_type'].replace('_', ' ').title()
        location_name = data.get('location_name') or f"{data['latitude']}, {data['longitude']}"
        custom_msg = data.get('custom_message', '')
        
        if custom_msg:
            alert_msg = f"{child.name} checked in from {location_name}: \"{custom_msg}\""
        else:
            alert_msg = f"{child.name} {checkin_type} from {location_name}"
        
        alert = Alert.objects.create(
            recipient=child.parent,
            child=child,
            alert_type='CHECK_IN',
            message=alert_msg
        )
        
        # Send notifications
        push_title = f"Check-In: {child.name}"
        push_data = {
            'alert_type': 'CHECK_IN',
            'child_id': str(child.id),
            'child_name': child.name,
            'check_in_type': data['check_in_type'],
            'message': alert_msg,
            'latitude': str(data['latitude']),
            'longitude': str(data['longitude']),
            'location_name': data.get('location_name', ''),
            'alert_id': str(alert.id),
            'timestamp': data['client_timestamp_iso'].isoformat()
        }
        
        send_fcm_to_user(user=child.parent, title=push_title, body=alert_msg, data=push_data)
        
        channel_layer = get_channel_layer()
        group_name = f'user_{child.parent.id}_notifications'
        ws_payload = {'type': 'child_check_in', 'alert_id': alert.id, 'data': push_data}
        async_to_sync(channel_layer.group_send)(
            group_name,
            {"type": "send_notification", "message": ws_payload}
        )
        
        return Response({"message": "Check-in processed"}, status=status.HTTP_201_CREATED)

# ====== MESSAGING VIEWS ======
class SendMessageView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MessageSerializer

    @extend_schema(
        summary="Send Direct Message",
        request=MessageSerializer,
        responses={201: MessageSerializer, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT}
    )
    def post(self, request, *args, **kwargs):
        serializer = MessageSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        receiver_id = serializer.validated_data['receiver_id']
        content = serializer.validated_data['content']
        
        try:
            receiver = User.objects.get(pk=receiver_id)
        except User.DoesNotExist:
            return Response({"error": "Recipient not found"}, status=status.HTTP_404_NOT_FOUND)
        
        message = Message.objects.create(
            sender=request.user,
            receiver=receiver,
            content=content
        )
        
        # Serialize for response
        message_serializer = MessageSerializer(message)
        
        # Send WebSocket notification
        channel_layer = get_channel_layer()
        recipient_group = f'user_{receiver.id}_notifications'
        ws_payload = {
            'type': 'new_message',
            'data': message_serializer.data
        }
        async_to_sync(channel_layer.group_send)(
            recipient_group,
            {"type": "new.chat.message", "payload": ws_payload}
        )
        
        # Send FCM notification
        sender_name = request.user.get_full_name() or request.user.username
        preview = content[:70] + '...' if len(content) > 70 else content
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
        
        return Response(message_serializer.data, status=status.HTTP_201_CREATED)

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

class ConversationListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="List User Conversations",
        responses={200: OpenApiTypes.OBJECT}
    )
    def get(self, request, *args, **kwargs):
        user = request.user
        # Get users with whom the current user has exchanged messages
        sent_to = User.objects.filter(received_messages__sender=user).distinct()
        received_from = User.objects.filter(sent_messages__receiver=user).distinct()
        contacts = (sent_to | received_from).distinct()
        
        conversations = []
        for contact in contacts:
            last_message = Message.objects.filter(
                (Q(sender=user, receiver=contact) | Q(sender=contact, receiver=user))
            ).order_by('-timestamp').first()
            
            if last_message:
                unread_count = Message.objects.filter(
                    sender=contact, receiver=user, is_read=False
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
    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        other_user_id = self.kwargs.get('other_user_id')
        user = self.request.user
        return Message.objects.filter(
            (Q(sender=user, receiver_id=other_user_id) | 
             Q(sender_id=other_user_id, receiver=user))
        ).order_by('timestamp')

class MarkMessagesAsReadRequestSerializer(drf_serializers.Serializer):
    other_user_id = drf_serializers.IntegerField()

class MarkMessagesAsReadView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = MarkMessagesAsReadRequestSerializer

    @extend_schema(
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
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)
        
        # Mark messages as read
        updated = Message.objects.filter(
            sender=other_user, receiver=request.user, is_read=False
        ).update(is_read=True)
        
        # Notify sender about read receipt
        if updated > 0:
            channel_layer = get_channel_layer()
            sender_group = f'user_{other_user.id}_notifications'
            read_payload = {
                'type': 'messages_read',
                'reader_id': str(request.user.id),
                'conversation_with_user_id': str(request.user.id),
                'read_at_timestamp': timezone.now().isoformat()
            }
            async_to_sync(channel_layer.group_send)(
                sender_group,
                {"type": "messages.read.receipt", "payload": read_payload}
            )
        
        return Response({"message": f"{updated} messages marked as read"}, status=status.HTTP_200_OK)

class ChildSendMessageRequestSerializer(drf_serializers.Serializer):
    child_id = drf_serializers.IntegerField()
    device_id = drf_serializers.CharField()
    content = drf_serializers.CharField()

class ChildSendMessageView(APIView):
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
        
        data = serializer.validated_data
        child_id = data['child_id']
        device_id = data['device_id']
        content = data['content']
        
        try:
            child = get_object_or_404(Child, pk=child_id, is_active=True)
        except Http404:
            return Response({"error": "Child not found"}, status=status.HTTP_404_NOT_FOUND)
        
        if not child.device_id or child.device_id != device_id:
            return Response({"error": "Device ID mismatch"}, status=status.HTTP_403_FORBIDDEN)
        
        if not child.proxy_user:
            return Response({"error": "Child account not configured for messaging"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        parent = child.parent
        message = Message.objects.create(
            sender=child.proxy_user,
            receiver=parent,
            content=content
        )
        message_serializer = MessageSerializer(message)
        
        # Send WebSocket notification
        channel_layer = get_channel_layer()
        parent_group = f'user_{parent.id}_notifications'
        ws_payload = {
            'type': 'new_message',
            'data': message_serializer.data
        }
        async_to_sync(channel_layer.group_send)(
            parent_group,
            {"type": "new.chat.message", "payload": ws_payload}
        )
        
        # Send FCM notification
        preview = content[:70] + '...' if len(content) > 70 else content
        fcm_data = {
            'type': 'new_message',
            'message_id': str(message.id),
            'sender_id': str(child.proxy_user.id),
            'sender_name': child.name,
            'conversation_with_user_id': str(child.proxy_user.id),
            'child_sender_actual_id': str(child.id),
            'content_preview': preview
        }
        send_fcm_to_user(
            user=parent,
            title=f"New message from {child.name}",
            body=preview,
            data=fcm_data
        )
        
        return Response(message_serializer.data, status=status.HTTP_201_CREATED)

# ====== ETA VIEWS ======
@extend_schema(summary="Start ETA Share")
class StartEtaShareView(APIView):
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
        
        data = serializer.validated_data
        sharer = request.user
        
        # Calculate ETA
        calculated_eta = None
        try:
            distance_m = distance_in_meters(
                data['current_latitude'],
                data['current_longitude'],
                data['destination_latitude'],
                data['destination_longitude']
            )
            speed_kmh = float(getattr(settings, 'DEFAULT_ETA_SPEED_KMH', 30))
            duration_hours = (distance_m / 1000.0) / speed_kmh
            duration_seconds = duration_hours * 3600
            calculated_eta = timezone.now() + timedelta(seconds=duration_seconds)
        except Exception as e:
            logger.error(f"Error calculating ETA: {e}")
        
        # Create ETA share
        eta_share = ActiveEtaShare.objects.create(
            sharer=sharer,
            destination_name=data.get('destination_name'),
            destination_latitude=data['destination_latitude'],
            destination_longitude=data['destination_longitude'],
            current_latitude=data['current_latitude'],
            current_longitude=data['current_longitude'],
            calculated_eta=calculated_eta,
            status='ACTIVE'
        )
        
        # Add shared users
        if data.get('shared_with_user_ids'):
            shared_users = User.objects.filter(pk__in=data['shared_with_user_ids'])
            eta_share.shared_with.set(shared_users)
        
        # Send notifications
        output_serializer = ActiveEtaShareSerializer(eta_share, context={'request': request})
        channel_layer = get_channel_layer()
        ws_payload = {'type': 'eta_started', 'data': output_serializer.data}
        
        fcm_title = f"ETA Share Started by {sharer.get_full_name() or sharer.username}"
        fcm_body = f"Tracking to {data.get('destination_name', 'destination')}"
        if calculated_eta:
            fcm_body += f", ETA: {calculated_eta.strftime('%I:%M %p')}"
        
        for user in eta_share.shared_with.all():
            async_to_sync(channel_layer.group_send)(
                f'user_{user.id}_notifications',
                {"type": "send_notification", "message": ws_payload}
            )
            send_fcm_to_user(
                user=user,
                title=fcm_title,
                body=fcm_body,
                data={'type': 'eta_started', 'share_id': str(eta_share.id)}
            )
        
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)

@extend_schema(summary="Update ETA Location")
class UpdateEtaLocationView(APIView):
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
            return Response({"error": "Active ETA share not found"}, status=status.HTTP_404_NOT_FOUND)
        
        if eta_share.sharer != request.user:
            return Response({"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)
        
        serializer = UpdateEtaLocationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        eta_share.current_latitude = data['current_latitude']
        eta_share.current_longitude = data['current_longitude']
        
        # Recalculate ETA
        new_eta = None
        try:
            distance_m = distance_in_meters(
                data['current_latitude'],
                data['current_longitude'],
                eta_share.destination_latitude,
                eta_share.destination_longitude
            )
            speed_kmh = float(getattr(settings, 'DEFAULT_ETA_SPEED_KMH', 30))
            duration_hours = (distance_m / 1000.0) / speed_kmh
            duration_seconds = duration_hours * 3600
            new_eta = timezone.now() + timedelta(seconds=duration_seconds)
            eta_share.calculated_eta = new_eta
        except Exception as e:
            logger.error(f"Error recalculating ETA: {e}")
        
        eta_share.save()
        
        # Send notifications
        output_serializer = ActiveEtaShareSerializer(eta_share, context={'request': request})
        channel_layer = get_channel_layer()
        ws_payload = {'type': 'eta_updated', 'data': output_serializer.data}
        
        # Notify sharer and all shared users
        users_to_notify = [eta_share.sharer] + list(eta_share.shared_with.all())
        for user in users_to_notify:
            async_to_sync(channel_layer.group_send)(
                f'user_{user.id}_notifications',
                {"type": "send_notification", "message": ws_payload}
            )
        
        return Response(output_serializer.data, status=status.HTTP_200_OK)

@extend_schema(summary="List Active ETA Shares")
class ListActiveEtaSharesView(generics.ListAPIView):
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
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses={200: SimpleMessageResponseSerializer, 403: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT})
    def post(self, request, share_id, *args, **kwargs):
        try:
            eta_share = get_object_or_404(ActiveEtaShare, pk=share_id, status='ACTIVE')
        except Http404:
            return Response({"error": "Active ETA share not found"}, status=status.HTTP_404_NOT_FOUND)
        
        if eta_share.sharer != request.user:
            return Response({"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)
        
        eta_share.status = 'CANCELLED'
        eta_share.save()
        
        # Send notifications
        output_serializer = ActiveEtaShareSerializer(eta_share, context={'request': request})
        channel_layer = get_channel_layer()
        ws_payload = {'type': 'eta_cancelled', 'data': output_serializer.data}
        
        # Notify sharer and all shared users
        users_to_notify = [eta_share.sharer] + list(eta_share.shared_with.all())
        for user in users_to_notify:
            async_to_sync(channel_layer.group_send)(
                f'user_{user.id}_notifications',
                {"type": "send_notification", "message": ws_payload}
            )
        
        return Response({"message": "ETA share cancelled"}, status=status.HTTP_200_OK)

@extend_schema(summary="Mark ETA Share as Arrived")
class ArrivedEtaShareView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses={200: SimpleMessageResponseSerializer, 403: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT})
    def post(self, request, share_id, *args, **kwargs):
        try:
            eta_share = get_object_or_404(ActiveEtaShare, pk=share_id, status='ACTIVE')
        except Http404:
            return Response({"error": "Active ETA share not found"}, status=status.HTTP_404_NOT_FOUND)
        
        if eta_share.sharer != request.user:
            return Response({"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)
        
        eta_share.status = 'ARRIVED'
        eta_share.save()
        
        # Send notifications
        output_serializer = ActiveEtaShareSerializer(eta_share, context={'request': request})
        channel_layer = get_channel_layer()
        ws_payload = {'type': 'eta_arrived', 'data': output_serializer.data}
        
        # Notify sharer and all shared users
        users_to_notify = [eta_share.sharer] + list(eta_share.shared_with.all())
        for user in users_to_notify:
            async_to_sync(channel_layer.group_send)(
                f'user_{user.id}_notifications',
                {"type": "send_notification", "message": ws_payload}
            )
        
        return Response({"message": "ETA share marked as arrived"}, status=status.HTTP_200_OK)