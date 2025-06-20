import os
import json
import firebase_admin
from firebase_admin import credentials, messaging  # Add messaging import
from django.conf import settings

# Initialize Firebase
fcm_key_json = os.environ.get('FCM_SERVICE_ACCOUNT_KEY')
if fcm_key_json:
    try:
        cred_dict = json.loads(fcm_key_json)
        cred = credentials.Certificate(cred_dict)
        firebase_app = firebase_admin.initialize_app(cred)  # Store the app instance
        print("Firebase initialized successfully")
    except Exception as e:
        print(f"Error initializing Firebase: {e}")
        firebase_app = None  # Set to None if initialization fails
else:
    print("FCM_SERVICE_ACCOUNT_KEY not set. Firebase not initialized.")
    firebase_app = None  # Set to None if no key

# Add the missing function implementation
def send_fcm_to_user(user_fcm_token, title, body, data=None):
    """
    Send FCM notification to a specific user device
    :param user_fcm_token: Device registration token
    :param title: Notification title
    :param body: Notification body
    :param data: Additional data payload (dict)
    :return: Message ID if successful, None otherwise
    """
    # Check if Firebase was initialized
    if not firebase_app:
        print("Firebase not initialized. Message not sent.")
        return None
        
    # Create the message
    message = messaging.Message(
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        token=user_fcm_token,
        data=data,  # Optional data payload
    )
    
    try:
        # Send the message
        response = messaging.send(message)
        print(f"Successfully sent FCM message: {response}")
        return response
    except Exception as e:
        print(f"Error sending FCM message: {e}")
        return None