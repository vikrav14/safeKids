from django.contrib import admin
from .models import UserProfile, Child, LocationPoint, SafeZone, Alert, Message, UserDevice # Added UserDevice

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone_number', 'account_tier', 'updated_at')
    search_fields = ('user__username', 'phone_number')

@admin.register(Child)
class ChildAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent', 'device_id', 'battery_status', 'updated_at')
    search_fields = ('name', 'parent__username', 'device_id')
    list_filter = ('parent',)

@admin.register(LocationPoint)
class LocationPointAdmin(admin.ModelAdmin):
    list_display = ('child', 'timestamp', 'latitude', 'longitude', 'accuracy')
    search_fields = ('child__name',)
    list_filter = ('child', 'timestamp')
    date_hierarchy = 'timestamp'

@admin.register(SafeZone)
class SafeZoneAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'latitude', 'longitude', 'radius')
    search_fields = ('name', 'owner__username')
    list_filter = ('owner',)

@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'child', 'alert_type', 'timestamp', 'is_read')
    search_fields = ('recipient__username', 'child__name', 'message')
    list_filter = ('alert_type', 'is_read', 'timestamp')
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
    list_filter = ('device_type', 'is_active', 'user') # Added user to list_filter
    search_fields = ('user__username', 'device_token')
    readonly_fields = ('created_at',)

    def device_token_short(self, obj):
        # Ensure token is not None and is a string before slicing
        if obj.device_token and isinstance(obj.device_token, str):
            return obj.device_token[:50] + "..." if len(obj.device_token) > 50 else obj.device_token
        return ""
    device_token_short.short_description = "Device Token (Short)"
