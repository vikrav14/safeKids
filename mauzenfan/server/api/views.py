from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, viewsets, permissions, generics
from rest_framework.permissions import AllowAny
from .serializers import (
    UserRegistrationSerializer,
    ChildSerializer,
    LocationPointSerializer,
    SafeZoneSerializer,
    SOSAlertSerializer,
    AlertSerializer # Added AlertSerializer
)
from .models import Child, LocationPoint, SafeZone, Alert
from django.shortcuts import get_object_or_404
from django.utils import timezone
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
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Child.objects.filter(parent=self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(parent=self.request.user)

class LocationUpdateView(APIView):
    permission_classes = [permissions.AllowAny]

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

            return Response(
                {"message": "Location updated successfully."},
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ChildCurrentLocationView(generics.RetrieveAPIView):
    serializer_class = LocationPointSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        child_id = self.kwargs.get('child_id')
        child = get_object_or_404(Child, pk=child_id, parent=self.request.user)

        location_point = LocationPoint.objects.filter(child=child).order_by('-timestamp').first()
        if not location_point:
            raise Http404("No location data found for this child.")
        return location_point

class ChildLocationHistoryView(generics.ListAPIView):
    serializer_class = LocationPointSerializer
    permission_classes = [permissions.IsAuthenticated]

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
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return SafeZone.objects.filter(owner=self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

class SOSAlertView(APIView):
    permission_classes = [permissions.AllowAny]

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

        return Response(
            {"message": "SOS alert successfully triggered and recorded."},
            status=status.HTTP_201_CREATED
        )

class AlertListView(generics.ListAPIView):
    serializer_class = AlertSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Users can only see alerts addressed to them, ordered by newest first.
        return Alert.objects.filter(recipient=self.request.user).order_by('-timestamp')
