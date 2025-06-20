import os
import json
import firebase_admin
from firebase_admin import credentials
from django.conf import settings

# Initialize Firebase
fcm_key_json = os.environ.get('FCM_SERVICE_ACCOUNT_KEY')
if fcm_key_json:
    try:
        cred_dict = json.loads(fcm_key_json)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        print("Firebase initialized successfully")
    except Exception as e:
        print(f"Error initializing Firebase: {e}")
else:
    print("FCM_SERVICE_ACCOUNT_KEY not set. Firebase not initialized.")