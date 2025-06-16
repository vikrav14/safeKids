from django.db import models
from django.contrib.auth.models import User # For linking UserProfile and for other ForeignKeys
# from django.utils.translation import gettext_lazy as _ # Optional, for choices text

# UserProfile model extends the default Django User model
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    account_tier = models.CharField(max_length=50, default='free') # e.g., 'free', 'premium'
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.user.username

class Child(models.Model):
    parent = models.ForeignKey(User, on_delete=models.CASCADE, related_name='children')
    name = models.CharField(max_length=100)
    device_id = models.CharField(max_length=255, unique=True, blank=True, null=True) # Unique ID for the child's device
    battery_status = models.IntegerField(blank=True, null=True) # Percentage
    last_seen_at = models.DateTimeField(blank=True, null=True)
    is_active = models.BooleanField(default=True, help_text="Is the child's profile/tracking active?")
    proxy_user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='messaging_child_profile',
        help_text="Proxy User account for this child for messaging purposes."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class LocationPoint(models.Model):
    child = models.ForeignKey(Child, on_delete=models.CASCADE, related_name='location_points')
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    timestamp = models.DateTimeField()
    accuracy = models.FloatField(blank=True, null=True) # In meters

    def __str__(self):
        return f"{self.child.name} at {self.timestamp}"

    class Meta:
        ordering = ['-timestamp']

class SafeZone(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='safe_zones')
    name = models.CharField(max_length=100) # e.g., "Lekol", "Lakaz"
    latitude = models.DecimalField(max_digits=9, decimal_places=6) # Center
    longitude = models.DecimalField(max_digits=9, decimal_places=6) # Center
    radius = models.FloatField() # In meters
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class Alert(models.Model):
    ALERT_TYPES = [
        ('SOS', 'SOS Panic'),
        ('LEFT_ZONE', 'Left Safe Zone'),
        ('ENTERED_ZONE', 'Entered Safe Zone'),
        ('LOW_BATTERY', 'Low Battery'),
        ('UNUSUAL_ROUTE', 'Unusual Route Detected'),
        ('CONTEXTUAL_WEATHER', 'Contextual Weather Alert'),
        ('CHECK_IN', 'Child Check-In'),
    ]
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='alerts')
    child = models.ForeignKey(Child, on_delete=models.CASCADE, related_name='alerts', blank=True, null=True)
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPES)
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    safe_zone = models.ForeignKey(SafeZone, on_delete=models.SET_NULL, blank=True, null=True, related_name='breach_alerts')

    def __str__(self):
        return f"{self.get_alert_type_display()} for {self.recipient.username}"

    class Meta:
        ordering = ['-timestamp']

class Message(models.Model):
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_messages')
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    def __str__(self):
        return f"From {self.sender.username} to {self.receiver.username} at {self.timestamp}"

    class Meta:
        ordering = ['-timestamp']

class UserDevice(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='devices')
    device_token = models.TextField(unique=True)
    device_type = models.CharField(max_length=10, blank=True, null=True, choices=[('android', 'Android'), ('ios', 'iOS'), ('web', 'Web')])
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        token_preview = self.device_token[:20] + "..." if self.device_token and len(self.device_token) > 20 else self.device_token
        return f"{self.user.username} - {self.device_type or 'UnknownType'} ({token_preview})"

    class Meta:
        ordering = ['-created_at']

class LearnedRoutine(models.Model):
    child = models.ForeignKey(Child, on_delete=models.CASCADE, related_name='learned_routines')
    name = models.CharField(max_length=100, blank=True, help_text="e.g., 'School Run', 'Visit to Park'")

    start_location_name = models.CharField(max_length=150, blank=True, null=True)
    start_latitude_approx = models.FloatField(blank=True, null=True)
    start_longitude_approx = models.FloatField(blank=True, null=True)

    end_location_name = models.CharField(max_length=150, blank=True, null=True)
    end_latitude_approx = models.FloatField(blank=True, null=True)
    end_longitude_approx = models.FloatField(blank=True, null=True)

    typical_days_of_week = models.CharField(max_length=15, blank=True, null=True, help_text="Comma-separated days (0=Mon, 6=Sun)")

    typical_time_window_start_min = models.TimeField(blank=True, null=True, help_text="Earliest typical start time")
    typical_time_window_start_max = models.TimeField(blank=True, null=True, help_text="Latest typical start time")

    route_path_approximation_json = models.JSONField(blank=True, null=True, help_text="JSON list of [lat, lon] waypoints")

    last_calculated_at = models.DateTimeField(auto_now_add=True)
    confidence_score = models.FloatField(default=0.0, help_text="Confidence in this learned routine (0.0 to 1.0)")
    is_active = models.BooleanField(default=True, help_text="Is this routine currently considered valid?")

    def __str__(self):
        return f"{self.name} for {self.child.name}" if self.name else f"Routine for {self.child.name}"

    class Meta:
        ordering = ['child', '-confidence_score', '-last_calculated_at']

class ActiveEtaShare(models.Model):
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('ARRIVED', 'Arrived'),
        ('CANCELLED', 'Cancelled'),
    ]

    sharer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='eta_shares_started'
    )
    destination_name = models.CharField(max_length=255, blank=True, null=True)
    destination_latitude = models.FloatField()
    destination_longitude = models.FloatField()

    current_latitude = models.FloatField(blank=True, null=True)
    current_longitude = models.FloatField(blank=True, null=True)

    calculated_eta = models.DateTimeField(blank=True, null=True)

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='ACTIVE'
    )

    shared_with = models.ManyToManyField(
        User,
        related_name='eta_shares_received',
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"ETA Share by {self.sharer.username} to {self.destination_name or 'Unnamed Destination'}"

    class Meta:
        ordering = ['-updated_at']
        verbose_name = "Active ETA Share"
        verbose_name_plural = "Active ETA Shares"
