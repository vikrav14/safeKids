from django.contrib import admin
from .models import (
    UserProfile, Child, LocationPoint, SafeZone,
    Alert, Message, UserDevice, LearnedRoutine
)
from .tasks import analyze_trip_task # Import the Celery task
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
# import json # Not strictly needed in admin.py for this action

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone_number', 'account_tier', 'updated_at')
    search_fields = ('user__username', 'phone_number')

@admin.register(Child)
class ChildAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent', 'device_id', 'battery_status', 'is_active', 'updated_at') # Added is_active
    search_fields = ('name', 'parent__username', 'device_id')
    list_filter = ('parent', 'is_active') # Added is_active
    actions = ['analyze_recent_activity_action']

    @admin.action(description='Analyze recent activity (last 3 hours) for unusual routes')
    def analyze_recent_activity_action(modeladmin, request, queryset):
        processed_children = 0
        for child in queryset:
            three_hours_ago = timezone.now() - timedelta(hours=3)
            recent_locations = LocationPoint.objects.filter(
                child=child,
                timestamp__gte=three_hours_ago
            ).order_by('timestamp')

            # Using MIN_TRIP_POINTS from tasks.py, or define a local constant
            # For simplicity, let's use a local constant or hardcode for the admin action
            MIN_POINTS_FOR_ANALYSIS = 5

            if recent_locations.count() >= MIN_POINTS_FOR_ANALYSIS:
                trip_points_data = [
                    {
                        'lat': float(lp.latitude),
                        'lon': float(lp.longitude),
                        'ts': lp.timestamp.isoformat()
                    }
                    for lp in recent_locations
                ]

                analyze_trip_task.delay(child.id, trip_points_data)
                processed_children += 1
            else:
                modeladmin.message_user(request, f"Not enough recent location data for {child.name} (found {recent_locations.count()} points, need {MIN_POINTS_FOR_ANALYSIS}).", messages.WARNING)

        if processed_children > 0:
            modeladmin.message_user(request, f"Analysis task queued for {processed_children} children. Check Celery logs for progress.", messages.SUCCESS)
        elif not queryset.exists(): # Should not happen if action is selected
            pass
        else: # No children processed due to insufficient data for all selected
            modeladmin.message_user(request, "No selected children had sufficient recent data for analysis.", messages.INFO)

@admin.register(LocationPoint)
class LocationPointAdmin(admin.ModelAdmin):
    list_display = ('child', 'timestamp', 'latitude', 'longitude', 'accuracy')
    search_fields = ('child__name',)
    list_filter = ('child', 'timestamp')
    date_hierarchy = 'timestamp'

@admin.register(SafeZone)
class SafeZoneAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'latitude', 'longitude', 'radius', 'is_active') # Added is_active
    search_fields = ('name', 'owner__username')
    list_filter = ('owner', 'is_active') # Added is_active

@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'child', 'alert_type', 'safe_zone', 'timestamp', 'is_read') # Added safe_zone
    search_fields = ('recipient__username', 'child__name', 'message', 'safe_zone__name') # Added safe_zone__name
    list_filter = ('alert_type', 'is_read', 'timestamp', 'child', 'safe_zone') # Added child, safe_zone
    date_hierarchy = 'timestamp'

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('sender', 'receiver', 'timestamp', 'is_read')
    search_fields = ('sender__username', 'receiver__username', 'content')
    list_filter = ('is_read', 'timestamp')
    date_hierarchy = 'timestamp'

@admin.register(UserDevice)
class UserDeviceAdmin(admin.ModelAdmin):
    list_display = ('user', 'device_type', 'device_token_short', 'created_at', 'is_active')
    list_filter = ('device_type', 'is_active', 'user')
    search_fields = ('user__username', 'device_token')
    readonly_fields = ('created_at',)

    def device_token_short(self, obj):
        if obj.device_token and isinstance(obj.device_token, str):
            return obj.device_token[:50] + "..." if len(obj.device_token) > 50 else obj.device_token
        return ""
    device_token_short.short_description = "Device Token (Short)"

@admin.register(LearnedRoutine)
class LearnedRoutineAdmin(admin.ModelAdmin):
    list_display = ('name', 'child', 'start_location_name', 'end_location_name', 'confidence_score', 'is_active', 'last_calculated_at')
    list_filter = ('child', 'is_active', 'typical_days_of_week', 'confidence_score')
    search_fields = ('name', 'child__name', 'start_location_name', 'end_location_name')
    readonly_fields = ('last_calculated_at',)
    # Consider using a custom form/widget for route_path_approximation_json if editing is needed
    fieldsets = (
        (None, {
            'fields': ('child', 'name', 'is_active')
        }),
        ('Route Details', {
            'classes': ('collapse',),
            'fields': (
                'start_location_name', 'start_latitude_approx', 'start_longitude_approx',
                'end_location_name', 'end_latitude_approx', 'end_longitude_approx',
                'route_path_approximation_json'
            ),
        }),
        ('Timing and Recurrence', {
            'classes': ('collapse',),
            'fields': ('typical_days_of_week', 'typical_time_window_start_min', 'typical_time_window_start_max'),
        }),
        ('Calculation Meta', {
            'classes': ('collapse',),
            'fields': ('last_calculated_at', 'confidence_score'),
        }),
    )
