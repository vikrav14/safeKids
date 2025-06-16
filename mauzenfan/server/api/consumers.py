import json
from channels.generic.websocket import AsyncWebsocketConsumer
import logging # Added logging

logger = logging.getLogger(__name__)

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # self.room_name = self.scope['url_route']['kwargs'].get('room_name', 'default_room')
        # self.room_group_name = f'notifications_{self.room_name}'

        # For now, a generic group for testing or a user-specific group
        # In a real app, you'd likely use user ID for authenticated users
        self.user = self.scope.get("user") # Get user from scope (if AuthMiddlewareStack is used)
        if self.user and self.user.is_authenticated:
            self.room_group_name = f'user_{self.user.id}_notifications'
        else:
            # Fallback or reject connection for unauthenticated users if needed
            # For now, let's reject unauthenticated users for this example
            # await self.close()
            # return
            self.room_group_name = 'public_notifications' # Example, or handle unauthenticated access

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()
        await self.send(text_data=json.dumps({
            'type': 'connection_established', # Use a type for client-side handling
            'message': f'Connected to notification channel. Group: {self.room_group_name}!'
        }))

    async def disconnect(self, close_code):
        # Leave room group
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    # Receive message from WebSocket (client) - not typically used for server-to-client notifications
    async def receive(self, text_data):
        # text_data_json = json.loads(text_data)
        # message = text_data_json.get('message', '')
        # For now, we don't expect clients to send messages here for this notification consumer
        # If client messages were needed, this is where they'd be handled.
        await self.send(text_data=json.dumps({
            'type': 'info',
            'message': 'This channel is primarily for server-to-client notifications.'
        }))
        pass

    # Receive message from room group (e.g., from Django view via channel_layer.group_send)
    async def send_notification(self, event):
        message_content = event['message'] # Expect 'message' key in the event dict

        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'notification', # Client can use this type to identify notification messages
            'payload': message_content # The actual notification data
        }))

    async def location_update(self, event):
        # The event dictionary itself contains the 'payload' key from group_send
        await self.send(text_data=json.dumps({
            'type': 'location_update', # For client-side differentiation
            'payload': event['payload']
        }))

    async def new_chat_message(self, event):
        # event dict contains: {'type': 'new.chat.message', 'payload': ws_message_payload}
        # ws_message_payload (from SendMessageView) is: {'type': 'new_message', 'data': broadcast_serializer.data}
        # This sends the ws_message_payload directly to the client.
        await self.send(text_data=json.dumps(event['payload']))

    async def messages_read_receipt(self, event):
        """
        Handles the 'messages.read.receipt' event from the channel layer
        and sends a 'messages_read' WebSocket message to the client.
        """
        payload_to_send_to_client = event['payload']

        await self.send(text_data=json.dumps(payload_to_send_to_client))
        # Safely access user ID for logging
        user_id_for_log = "UnknownUser"
        if self.scope.get("user") and self.scope["user"].is_authenticated:
            user_id_for_log = self.scope["user"].id
        logger.info(f"Relayed messages_read_receipt to client for user {user_id_for_log}: {payload_to_send_to_client}")


    # Example of a specific type handler if you use different 'type' in group_send
    # async def specific_alert_type(self, event):
    #     data = event['data']
    #     await self.send(text_data=json.dumps({
    #         'type': 'specific_alert',
    #         'payload': data
    #     }))
