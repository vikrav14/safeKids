class Alert:
    # alert_id (Primary Key)
    # user_id (Foreign Key to User model - who receives the alert)
    # child_id (Foreign Key to Child model - who is the alert about, optional)
    # alert_type (e.g., "SOS", "LeftSafeZone", "LowBattery")
    # message (details of the alert)
    # timestamp
    # is_read (boolean)
    pass
