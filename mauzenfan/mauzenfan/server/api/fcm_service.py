import os
import json
import firebase_admin
from firebase_admin import credentials, messaging

# Initialize Firebase
fcm_key_json = os.environ.get('FCM_SERVICE_ACCOUNT_KEY')
if fcm_key_json:
    try:
        cred_dict = json.loads(fcm_key_json)
        cred = credentials.Certificate(cred_dict)
        firebase_app = firebase_admin.initialize_app(cred)
        print("Firebase initialized successfully")
    except Exception as e:
        print(f"Error initializing Firebase: {e}")
        firebase_app = None
else:
    print("FCM_SERVICE_ACCOUNT_KEY not set. Firebase not initialized.")
    firebase_app = None

def send_fcm_to_user(user_fcm_token, title, body, data=None):
    if not firebase_app:
        print("Firebase not initialized. Message not sent.")
        return None
        
    message = messaging.Message(
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        token=user_fcm_token,
        data=data,
    )
    
    try:
        response = messaging.send(message)
        print("Successfully sent message:", response)
        return response
    except Exception as e:
        print("Error sending message:", e)
        return None
