# mauzenfan/server/api/fcm_service.py
import firebase_admin
from firebase_admin import credentials, messaging
from django.conf import settings # To potentially get FCM credential path
import os
import logging # Using logging is better than print for server applications

logger = logging.getLogger(__name__)

# --- Firebase Admin SDK Initialization ---
# IMPORTANT: The service account key JSON file should NOT be in version control.
# Its path should be loaded from an environment variable or secure config.
FCM_CREDENTIAL_PATH = getattr(settings, 'FCM_SERVICE_ACCOUNT_KEY_PATH', None)

# Check if Firebase app is already initialized to prevent re-initialization error
if not firebase_admin._apps:
    if FCM_CREDENTIAL_PATH and os.path.exists(FCM_CREDENTIAL_PATH):
        try:
            cred = credentials.Certificate(FCM_CREDENTIAL_PATH)
            firebase_admin.initialize_app(cred)
            logger.info("Firebase Admin SDK initialized successfully.")
        except Exception as e:
            logger.error(f"Error initializing Firebase Admin SDK: {e}. FCM notifications will not work.")
    else:
        # This indicates a setup issue if FCM is expected to work.
        logger.warning("FCM_SERVICE_ACCOUNT_KEY_PATH not set or file not found. FCM notifications will not work. App will run, but sending messages will fail.")
        # For testing/CI environments without credentials, this allows the app to run without crashing.

def send_fcm_notification(registration_tokens, title, body, data=None):
    """
    Sends an FCM push notification to one or more devices.

    :param registration_tokens: A list of device registration tokens.
    :param title: The title of the notification.
    :param body: The body/message of the notification.
    :param data: Optional dictionary of key-value pairs to send as data payload.
                 All values in data payload must be strings.
    :return: Boolean indicating if at least one message was sent successfully.
    """
    if not firebase_admin._apps:
        logger.error("Firebase Admin SDK not initialized. Cannot send FCM message.")
        return False

    if not registration_tokens:
        logger.warning("No registration tokens provided for FCM notification.")
        return False

    # Ensure data payload values are strings if data is provided
    stringified_data = None
    if data:
        stringified_data = {str(k): str(v) for k, v in data.items()}

    message = messaging.MulticastMessage(
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        data=stringified_data, # Use stringified data
        tokens=registration_tokens,
    )

    try:
        response = messaging.send_multicast(message)
        logger.info(f'Successfully sent FCM message: {response.success_count} successes, {response.failure_count} failures.')
        if response.failure_count > 0:
            for i, send_response in enumerate(response.responses):
                if not send_response.success:
                    logger.error(f'Failed to send to token {registration_tokens[i]}: {send_response.exception}')
                    # Optionally, handle dead/invalid tokens here (e.g., mark UserDevice as inactive)
                    # Consider also checking for specific error codes like 'UNREGISTERED'
                    # if send_response.exception.code == 'messaging/registration-token-not-registered':
                    #     # Logic to deactivate token
                    #     pass
        return response.success_count > 0
    except Exception as e:
        logger.error(f'Error sending FCM message: {e}')
        return False

def send_fcm_to_user(user, title, body, data=None):
    """
    Sends an FCM notification to all active devices of a given user.
    """
    # Local import to avoid circular dependency issues if models.py ever tried to import from this service directly at module level.
    # It's generally safer inside functions or methods.
    from .models import UserDevice

    active_devices = UserDevice.objects.filter(user=user, is_active=True)
    tokens = [device.device_token for device in active_devices]

    if not tokens:
        logger.info(f"No active devices found for user {user.username} to send FCM notification '{title}'.")
        return False

    logger.info(f"Attempting to send FCM to user {user.username} (tokens: {len(tokens)}) with title: {title}")
    return send_fcm_notification(tokens, title, body, data)
