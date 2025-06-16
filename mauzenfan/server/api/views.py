from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, viewsets, permissions, generics
from rest_framework.permissions import AllowAny, IsAuthenticated # Ensure IsAuthenticated is imported
from .serializers import (
    UserRegistrationSerializer,
    ChildSerializer,
    LocationPointSerializer,
    SafeZoneSerializer,
    SOSAlertSerializer,
    AlertSerializer,
    DeviceRegistrationSerializer # Added DeviceRegistrationSerializer
)
from .models import Child, LocationPoint, SafeZone, Alert, UserDevice
from .fcm_service import send_fcm_to_user
from .geolocation_utils import distance_in_meters # Import distance calculation
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import timedelta # Import timedelta
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.http import Http404
from django.utils.dateparse import parse_datetime

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
             return Response(
                 {"error": "child_id and device_id are required."},
                 status=status.HTTP_400_BAD_REQUEST
             )

        try:
            child = get_object_or_404(Child, pk=child_id_from_req)
        except ValueError:
            return Response({"error": "Invalid child_id format."}, status=status.HTTP_400_BAD_REQUEST)

        if not child.device_id or child.device_id != device_id_from_request:
            return Response(
                {"error": "Device ID mismatch or not registered for this child."},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = LocationPointSerializer(data=request.data)
        if serializer.is_valid():
            LocationPoint.objects.create(
                child=child,
                latitude=serializer.validated_data['latitude'],
                longitude=serializer.validated_data['longitude'],
                timestamp=serializer.validated_data['timestamp'],
                accuracy=serializer.validated_data.get('accuracy')
            )

            if battery_status_from_req is not None:
                try:
                    child.battery_status = int(battery_status_from_req)
                except ValueError:
                    pass
            child.last_seen_at = timezone.now()
            child.save(update_fields=['battery_status', 'last_seen_at'])

            channel_layer = get_channel_layer()
            parent_user_id = child.parent.id
            group_name = f'user_{parent_user_id}_notifications'

            location_data_for_ws = {
                'child_id': child.id,
                'child_name': child.name,
                'latitude': float(serializer.validated_data['latitude']),
                'longitude': float(serializer.validated_data['longitude']),
                'timestamp': serializer.validated_data['timestamp'].isoformat(),
                'accuracy': float(serializer.validated_data.get('accuracy')) if serializer.validated_data.get('accuracy') is not None else None,
                'battery_status': child.battery_status
            }

            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    "type": "location.update",
                    "payload": location_data_for_ws
                }
            )

            # --- Safe Zone Breach Detection ---
            parent_user = child.parent
            current_location_lat = serializer.validated_data['latitude']
            current_location_lon = serializer.validated_data['longitude']

            active_safe_zones = SafeZone.objects.filter(owner=parent_user, is_active=True)
            ALERT_COOLDOWN_MINUTES = 10

            for zone in active_safe_zones:
                distance_to_zone_center_m = distance_in_meters(
                    current_location_lat,
                    current_location_lon,
                    zone.latitude,
                    zone.longitude
                )

                currently_inside_zone = distance_to_zone_center_m <= zone.radius

                # Fetch the last relevant alert for this child and this specific zone
                last_alert_for_zone = Alert.objects.filter(
                    recipient=parent_user,
                    child=child,
                    safe_zone_id=zone.id # Check against the specific zone
                ).order_by('-timestamp').first()

                previous_status_was_inside = False
                alert_on_cooldown = False

                if last_alert_for_zone:
                    if last_alert_for_zone.alert_type == 'ENTERED_ZONE':
                        previous_status_was_inside = True
                    # if alert_type == 'LEFT_ZONE', previous_status_was_inside remains False

                    if (timezone.now() - last_alert_for_zone.timestamp) < timedelta(minutes=ALERT_COOLDOWN_MINUTES):
                        alert_on_cooldown = True

                new_alert_type = None
                alert_message = ""

                if currently_inside_zone and not previous_status_was_inside and not alert_on_cooldown:
                    new_alert_type = 'ENTERED_ZONE'
                    alert_message = f"{child.name} has entered {zone.name}."
                elif not currently_inside_zone and previous_status_was_inside and not alert_on_cooldown:
                    new_alert_type = 'LEFT_ZONE'
                    alert_message = f"{child.name} has left {zone.name}."

                if new_alert_type:
                    created_breach_alert = Alert.objects.create(
                        recipient=parent_user,
                        child=child,
                        alert_type=new_alert_type,
                        message=alert_message,
                        safe_zone_id=zone.id # Link alert to the specific zone
                    )

                    push_title = f"Safe Zone Alert: {child.name}"
                    push_data = {
                        'alert_type': new_alert_type,
                        'child_id': str(child.id),
                        'child_name': child.name,
                        'zone_id': str(zone.id),
                        'zone_name': zone.name,
                        'alert_id': str(created_breach_alert.id)
                    }
                    send_fcm_to_user(user=parent_user, title=push_title, body=alert_message, data=push_data)

                    ws_message_payload = {
                        'type': 'safezone_alert',
                        'alert_id': created_breach_alert.id,
                        'child_id': child.id,
                        'child_name': child.name,
                        'zone_id': zone.id,
                        'zone_name': zone.name,
                        'alert_type': new_alert_type,
                        'message': alert_message,
                        'timestamp': created_breach_alert.timestamp.isoformat()
                    }
                    async_to_sync(channel_layer.group_send)(
                        group_name, # Re-use group_name from location update WS
                        {
                            "type": "send_notification", # Consumer's generic handler
                            "message": ws_message_payload
                        }
                    )
            # --- End Safe Zone Breach Detection ---

            return Response(
                {"message": "Location updated successfully. Safe zone check performed."}, # Updated message
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ChildCurrentLocationView(generics.RetrieveAPIView):
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
    serializer_class = LocationPointSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        child_id = self.kwargs.get('child_id')
        child = get_object_or_404(Child, pk=child_id, parent=self.request.user)

        queryset = LocationPoint.objects.filter(child=child).order_by('-timestamp')

        start_timestamp_str = self.request.query_params.get('start_timestamp')
        end_timestamp_str = self.request.query_params.get('end_timestamp')

        if start_timestamp_str:
            try:
                start_timestamp = parse_datetime(start_timestamp_str)
                if start_timestamp:
                    if timezone.is_naive(start_timestamp):
                        start_timestamp = timezone.make_aware(start_timestamp, timezone.get_default_timezone())
                    queryset = queryset.filter(timestamp__gte=start_timestamp)
            except (ValueError, TypeError):
                pass

        if end_timestamp_str:
            try:
                end_timestamp = parse_datetime(end_timestamp_str)
                if end_timestamp:
                    if timezone.is_naive(end_timestamp):
                        end_timestamp = timezone.make_aware(end_timestamp, timezone.get_default_timezone())
                    queryset = queryset.filter(timestamp__lte=end_timestamp)
            except (ValueError, TypeError):
                pass

        return queryset

class SafeZoneViewSet(viewsets.ModelViewSet):
    serializer_class = SafeZoneSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return SafeZone.objects.filter(owner=self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

class SOSAlertView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = SOSAlertSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated_data = serializer.validated_data
        child_id = validated_data.get('child_id')
        device_id_from_request = validated_data.get('device_id')
        latitude = validated_data.get('latitude')
        longitude = validated_data.get('longitude')

        try:
            child = get_object_or_404(Child, pk=child_id)
        except Http404:
            return Response({"error": "Child not found."}, status=status.HTTP_404_NOT_FOUND)

        if not child.device_id or child.device_id != device_id_from_request:
            return Response(
                {"error": "Device ID mismatch or not registered for this child."},
                status=status.HTTP_403_FORBIDDEN
            )

        parent_user = child.parent

        message_parts = [f"SOS triggered by {child.name}."]
        location_known = False
        if latitude is not None and longitude is not None:
            message_parts.append(f"Current location: lat {latitude}, lon {longitude}.")
            location_known = True
        else:
            last_location = LocationPoint.objects.filter(child=child).order_by('-timestamp').first()
            if last_location:
                message_parts.append(f"Last known location (at {last_location.timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')}): lat {last_location.latitude}, lon {last_location.longitude}.")
                location_known = True

        if not location_known:
            message_parts.append("Current location not available.")

        sos_message = " ".join(message_parts)

        Alert.objects.create(
            recipient=parent_user,
            child=child,
            alert_type='SOS',
            message=sos_message
        )

        # Send FCM notification to the parent
        push_title = f"SOS Alert: {child.name}"
        push_data = {
            'alert_type': 'SOS',
            'child_id': str(child.id),
            'child_name': child.name,
            # 'alert_id': str(created_alert.id) # If you capture the created_alert instance
        }
        if latitude is not None and longitude is not None:
            push_data['latitude'] = str(latitude)
            push_data['longitude'] = str(longitude)
        elif 'last_location' in locals() and last_location: # Check if last_location was defined and found
            push_data['latitude'] = str(last_location.latitude)
            push_data['longitude'] = str(last_location.longitude)
            push_data['location_timestamp'] = last_location.timestamp.isoformat()

        send_fcm_to_user(user=parent_user, title=push_title, body=sos_message, data=push_data)

        return Response(
            {"message": "SOS alert successfully triggered, recorded, and notification sent."},
            status=status.HTTP_201_CREATED
        )

class AlertListView(generics.ListAPIView):
    serializer_class = AlertSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Alert.objects.filter(recipient=self.request.user).order_by('-timestamp')

class DeviceRegistrationView(APIView):
    permission_classes = [IsAuthenticated] # Changed from permissions.IsAuthenticated

    def post(self, request, *args, **kwargs):
        serializer = DeviceRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            device_token = serializer.validated_data['device_token']
            device_type = serializer.validated_data.get('device_type')

            # Deactivate any other UserDevice entries with the same token but different user
            UserDevice.objects.filter(device_token=device_token).exclude(user=request.user).update(is_active=False)

            # Create or update the device for the current user
            user_device, created = UserDevice.objects.update_or_create(
                user=request.user,
                device_token=device_token,
                defaults={'is_active': True, 'device_type': device_type}
            )

            if created:
                return Response({"message": "Device registered successfully."}, status=status.HTTP_201_CREATED)
            else:
                return Response({"message": "Device registration updated successfully."}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
