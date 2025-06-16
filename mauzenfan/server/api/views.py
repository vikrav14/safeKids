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

import logging

logger = logging.getLogger(__name__)

class RegistrationView(APIView):
    permission_classes = [AllowAny]
    def post(self, request, *args, **kwargs):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response({"message": "User registered successfully.", "user_id": user.id, "username": user.username}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ChildViewSet(viewsets.ModelViewSet):
    serializer_class = ChildSerializer
    permission_classes = [IsAuthenticated]
    def get_queryset(self):
        return Child.objects.filter(parent=self.request.user).order_by('-created_at')
    def perform_create(self, serializer):
        serializer.save(parent=self.request.user)

class LocationUpdateView(APIView):
    permission_classes = [AllowAny]
    def post(self, request, *args, **kwargs):
        child_id_from_req = request.data.get('child_id')
        device_id_from_request = request.data.get('device_id')
        battery_status_from_req = request.data.get('battery_status')
        if not all([child_id_from_req, device_id_from_request]):
             return Response( {"error": "child_id and device_id are required."}, status=status.HTTP_400_BAD_REQUEST )
        try: child = get_object_or_404(Child, pk=child_id_from_req)
        except ValueError: return Response({"error": "Invalid child_id format."}, status=status.HTTP_400_BAD_REQUEST)
        if not child.device_id or child.device_id != device_id_from_request:
            return Response( {"error": "Device ID mismatch or not registered for this child."}, status=status.HTTP_403_FORBIDDEN )
        serializer = LocationPointSerializer(data=request.data)
        if serializer.is_valid():
            LocationPoint.objects.create( child=child, latitude=serializer.validated_data['latitude'], longitude=serializer.validated_data['longitude'], timestamp=serializer.validated_data['timestamp'], accuracy=serializer.validated_data.get('accuracy') )
            if battery_status_from_req is not None:
                try: child.battery_status = int(battery_status_from_req)
                except ValueError: pass
            child.last_seen_at = timezone.now(); child.save(update_fields=['battery_status', 'last_seen_at'])
            channel_layer = get_channel_layer(); parent_user_id = child.parent.id; group_name = f'user_{parent_user_id}_notifications'
            location_data_for_ws = { 'child_id': child.id, 'child_name': child.name, 'latitude': float(serializer.validated_data['latitude']), 'longitude': float(serializer.validated_data['longitude']), 'timestamp': serializer.validated_data['timestamp'].isoformat(), 'accuracy': float(serializer.validated_data.get('accuracy')) if serializer.validated_data.get('accuracy') is not None else None, 'battery_status': child.battery_status }
            async_to_sync(channel_layer.group_send)( group_name, { "type": "location.update", "payload": location_data_for_ws } )
            parent_user = child.parent; current_location_lat = serializer.validated_data['latitude']; current_location_lon = serializer.validated_data['longitude']
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
            if battery_status_from_req is not None:
                try:
                    current_battery_level = int(battery_status_from_req)
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
                except ValueError: logger.warning(f"Invalid battery_status value received: {battery_status_from_req} for child {child.id}"); pass
            return Response( {"message": "Location updated successfully. Safe zone and battery checks performed."}, status=status.HTTP_201_CREATED )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ChildCurrentLocationView(generics.RetrieveAPIView):
    serializer_class = LocationPointSerializer; permission_classes = [IsAuthenticated]
    def get_object(self):
        child_id = self.kwargs.get('child_id'); child = get_object_or_404(Child, pk=child_id, parent=self.request.user)
        location_point = LocationPoint.objects.filter(child=child).order_by('-timestamp').first()
        if not location_point: raise Http404("No location data found for this child.")
        return location_point

class ChildLocationHistoryView(generics.ListAPIView):
    serializer_class = LocationPointSerializer; permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination
    def get_queryset(self):
        other_user_id = self.kwargs.get('other_user_id', None)
        child_id = self.kwargs.get('child_id', other_user_id)
        child = get_object_or_404(Child, pk=child_id, parent=self.request.user)
        queryset = LocationPoint.objects.filter(child=child).order_by('-timestamp')
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

class SafeZoneViewSet(viewsets.ModelViewSet):
    serializer_class = SafeZoneSerializer; permission_classes = [IsAuthenticated]
    def get_queryset(self): return SafeZone.objects.filter(owner=self.request.user).order_by('-created_at')
    def perform_create(self, serializer): serializer.save(owner=self.request.user)

class SOSAlertView(APIView):
    permission_classes = [AllowAny]
    def post(self, request, *args, **kwargs):
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

class AlertListView(generics.ListAPIView):
    serializer_class = AlertSerializer; permission_classes = [IsAuthenticated]
    def get_queryset(self): return Alert.objects.filter(recipient=self.request.user).order_by('-timestamp')

class DeviceRegistrationView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request, *args, **kwargs):
        serializer = DeviceRegistrationSerializer(data=request.data);
        if serializer.is_valid():
            device_token = serializer.validated_data['device_token']; device_type = serializer.validated_data.get('device_type')
            UserDevice.objects.filter(device_token=device_token).exclude(user=request.user).update(is_active=False)
            user_device, created = UserDevice.objects.update_or_create( user=request.user, device_token=device_token, defaults={'is_active': True, 'device_type': device_type} )
            if created: return Response({"message": "Device registered successfully."}, status=status.HTTP_201_CREATED)
            else: return Response({"message": "Device registration updated successfully."}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ChildCheckInView(APIView):
    permission_classes = [permissions.AllowAny]
    def post(self, request, *args, **kwargs):
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
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, *args, **kwargs):
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
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request, *args, **kwargs):
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

class MessageHistoryView(generics.ListAPIView):
    serializer_class = MessageSerializer; permission_classes = [IsAuthenticated]; pagination_class = StandardResultsSetPagination
    def get_queryset(self):
        other_user_id = self.kwargs.get('other_user_id'); user = self.request.user
        if str(other_user_id) == str(user.id): return Message.objects.none()
        try: User.objects.get(pk=other_user_id)
        except User.DoesNotExist: return Message.objects.none()
        queryset = Message.objects.filter( (Q(sender=user, receiver_id=other_user_id) | Q(sender_id=other_user_id, receiver=user)) ).select_related('sender', 'receiver').order_by('timestamp')
        return queryset

class MarkMessagesAsReadView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, *args, **kwargs):
        other_user_id = request.data.get('other_user_id')
        if not other_user_id: return Response({"error": "other_user_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        try: other_user = User.objects.get(pk=other_user_id)
        except User.DoesNotExist: return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        messages_updated_count = Message.objects.filter( sender=other_user, receiver=request.user, is_read=False ).update(is_read=True)
        if messages_updated_count > 0 and other_user:
            channel_layer = get_channel_layer(); sender_notification_group_name = f'user_{other_user.id}_notifications'
            read_receipt_payload = { 'type': 'messages_read', 'reader_id': str(request.user.id), 'conversation_with_user_id': str(request.user.id), 'read_at_timestamp': timezone.now().isoformat() }
            async_to_sync(channel_layer.group_send)( sender_notification_group_name, { "type": "messages.read.receipt", "payload": read_receipt_payload } )
            logger.info(f"Sent read receipt to user {other_user.username} for conversation with {request.user.username}")
        return Response({"message": f"{messages_updated_count} messages marked as read."}, status=status.HTTP_200_OK)

class ChildSendMessageView(APIView):
    permission_classes = [permissions.AllowAny]
    def post(self, request, *args, **kwargs):
        child_id = request.data.get('child_id'); device_id_from_request = request.data.get('device_id'); content = request.data.get('content')
        if not all([child_id, device_id_from_request, content]): return Response( {"error": "child_id, device_id, and content are required."}, status=status.HTTP_400_BAD_REQUEST )
        if not content.strip(): return Response({"error": "Message content cannot be empty."}, status=status.HTTP_400_BAD_REQUEST)
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

class StartEtaShareView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, *args, **kwargs):
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

class UpdateEtaLocationView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, share_id, *args, **kwargs):
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

class ListActiveEtaSharesView(generics.ListAPIView):
    serializer_class = ActiveEtaShareSerializer
    permission_classes = [permissions.IsAuthenticated]
    # pagination_class = StandardResultsSetPagination # Add if pagination is desired

    def get_queryset(self):
        user = self.request.user
        return ActiveEtaShare.objects.filter(
            Q(status='ACTIVE'),
            Q(sharer=user) | Q(shared_with=user)
        ).distinct().order_by('-updated_at')

class CancelEtaShareView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, share_id, *args, **kwargs):
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

class ArrivedEtaShareView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, share_id, *args, **kwargs):
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
