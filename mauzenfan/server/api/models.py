from django.db import models
from django.contrib.auth.models import User # For linking UserProfile and for other ForeignKeys

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
        # Add other types as needed
    ]
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='alerts')
    child = models.ForeignKey(Child, on_delete=models.CASCADE, related_name='alerts', blank=True, null=True)
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPES)
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.get_alert_type_display()} for {self.recipient.username}"

    class Meta:
        ordering = ['-timestamp']

class Message(models.Model):
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    # For simplicity, receiver is also a User. Could be a group chat ID later.
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_messages')
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    def __str__(self):
        return f"From {self.sender.username} to {self.receiver.username} at {self.timestamp}"

    class Meta:
        ordering = ['-timestamp']
