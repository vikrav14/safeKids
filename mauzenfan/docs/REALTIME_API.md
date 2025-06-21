# MauZenfan Real-time api_app. Documentation

This document outlines the WebSocket and Firebase Cloud Messaging (FCM) payloads used for real-time communication between the MauZenfan server and client applications.

## 1. WebSocket api_app..


### 1.1. Endpoint URL

The WebSocket endpoint is typically available at:

```
ws://<your_server_address>/ws/notifications/
```
(e.g., `ws://localhost:8000/ws/notifications/` in development)

### 1.2. Authentication & Connection

- Authentication is handled via the standard Django session/token authentication used for the rest of the api_app.. The WebSocket connection request should include necessary authentication headers (e.g., cookies or a token in the query string if using `channels.auth.AuthMiddlewareStack` with custom token handling).
- Upon successful connection, the server automatically subscribes the client to a user-specific notification group (e.g., `user_{user_id}_notifications`). Clients do not need to send explicit subscribe messages.

### 1.3. General Message Format (Server-to-Client)

All messages sent from the server to the client via WebSocket are JSON objects with a top-level `type` field, which indicates the kind of notification or data being sent.

```json
{
  "type": "event_type_identifier",
  "payload": {
    // ...event-specific data...
  }
}
```
For some events, the structure might be slightly different if a generic `send_notification` consumer handler is used, where the `payload` itself becomes the top-level object and contains its own `type`. This will be noted for specific messages.

### 1.4. WebSocket Message Types & Payloads

#### 1.4.1. New Chat Message

- **`type`**: `new.chat.message` (when handled by `new.chat.message` consumer type) or `new_message` (if sent via generic `send_notification`)
- **`payload`**: Contains the serialized `Message` object.

```json
{
  "type": "new.chat.message", // or "new_message" if generic
  "payload": { // or "data" if generic and type="new_message"
    "id": 101,
    "sender": {
      "id": 2,
      "display_name": "Child One", // Child's name if sender is a child's proxy_user
      "username": "child_one_proxy"
    },
    "receiver": {
      "id": 1,
      "display_name": "Parent User",
      "username": "parentuser"
    },
    "content": "Hello Dad!",
    "timestamp": "2023-10-27T10:30:00Z",
    "is_read": false
  }
}
```

#### 1.4.2. Location Update (Child Tracking)

- **`type`**: `location.update` (when handled by `location.update` consumer type) or `location_update` (if sent via generic `send_notification`)
- **`payload`**: Contains live location data for a child.

```json
{
  "type": "location.update", // or "location_update" if generic
  "payload": { // or "data" if generic and type="location_update"
    "child_id": 15,
    "child_name": "Child One",
    "latitude": 34.052235,
    "longitude": -118.243683,
    "timestamp": "2023-10-27T10:35:00Z",
    "accuracy": 10.5, // in meters, optional
    "battery_status": 85 // percentage, optional
  }
}
```

#### 1.4.3. ETA Share Started

- **`type`**: `eta_started` (typically sent via generic `send_notification`)
- **`message`** (if generic): Contains the full `ActiveEtaShareSerializer` data.

```json
{
  "type": "send_notification", // Wrapper type if generic consumer used
  "message": { // This is the actual payload
    "type": "eta_started",
    "data": { // Content of ActiveEtaShareSerializer
      "id": 5,
      "sharer": { "id": 1, "display_name": "Parent User", "username": "parentuser" },
      "destination_name": "School",
      "destination_latitude": 34.078900,
      "destination_longitude": -118.291200,
      "current_latitude": 34.052235,
      "current_longitude": -118.243683,
      "calculated_eta": "2023-10-27T11:00:00Z",
      "status": "ACTIVE",
      "shared_with": [
        { "id": 3, "display_name": "Other Parent", "username": "otherparent" }
      ],
      "created_at": "2023-10-27T10:30:00Z",
      "updated_at": "2023-10-27T10:30:00Z"
    }
  }
}
```

#### 1.4.4. ETA Share Updated

- **`type`**: `eta_updated` (typically sent via generic `send_notification`)
- **`message`** (if generic): Contains the full `ActiveEtaShareSerializer` data.

```json
{
  "type": "send_notification",
  "message": {
    "type": "eta_updated",
    "data": { // Content of ActiveEtaShareSerializer (updated fields)
      "id": 5,
      "sharer": { "id": 1, "display_name": "Parent User", "username": "parentuser" },
      "destination_name": "School",
      "destination_latitude": 34.078900,
      "destination_longitude": -118.291200,
      "current_latitude": 34.065500,   // Updated
      "current_longitude": -118.278800, // Updated
      "calculated_eta": "2023-10-27T10:55:00Z", // Recalculated
      "status": "ACTIVE",
      "shared_with": [
        { "id": 3, "display_name": "Other Parent", "username": "otherparent" }
      ],
      "created_at": "2023-10-27T10:30:00Z",
      "updated_at": "2023-10-27T10:45:00Z" // Updated
    }
  }
}
```

#### 1.4.5. ETA Share Cancelled

- **`type`**: `eta_cancelled` (typically sent via generic `send_notification`)
- **`message`** (if generic): Contains the full `ActiveEtaShareSerializer` data with status 'CANCELLED'.

```json
{
  "type": "send_notification",
  "message": {
    "type": "eta_cancelled",
    "data": { // Content of ActiveEtaShareSerializer (status changed)
      "id": 5,
      "sharer": { "id": 1, "display_name": "Parent User", "username": "parentuser" },
      // ... other fields ...
      "status": "CANCELLED",
      "updated_at": "2023-10-27T10:50:00Z"
    }
  }
}
```

#### 1.4.6. ETA Share Arrived

- **`type`**: `eta_arrived` (typically sent via generic `send_notification`)
- **`message`** (if generic): Contains the full `ActiveEtaShareSerializer` data with status 'ARRIVED'.

```json
{
  "type": "send_notification",
  "message": {
    "type": "eta_arrived",
    "data": { // Content of ActiveEtaShareSerializer (status changed)
      "id": 5,
      "sharer": { "id": 1, "display_name": "Parent User", "username": "parentuser" },
      // ... other fields ...
      "status": "ARRIVED",
      "updated_at": "2023-10-27T10:58:00Z"
    }
  }
}
```

#### 1.4.7. Messages Read Receipt

- **`type`**: `messages.read.receipt` (when handled by `messages.read.receipt` consumer type) or `messages_read` (if generic)
- **`payload`**: Indicates that messages from a specific user were read.

```json
{
  "type": "messages.read.receipt", // or "messages_read" if generic
  "payload": { // or "data" if generic and type="messages_read"
    "reader_id": 1, // User who read the messages
    "conversation_with_user_id": 2, // User whose messages were read by reader_id
    "read_at_timestamp": "2023-10-27T11:15:00Z"
  }
}
```

#### 1.4.8. Contextual Weather Alert

- **`type`**: `contextual_weather_alert` (typically sent via generic `send_notification`)
- **`message`** (if generic): Contains details of the weather alert.

```json
{
  "type": "send_notification",
  "message": {
    "type": "contextual_weather_alert",
    "alert_id": 77, // ID of the created Alert object in the database
    "child_id": 15,
    "child_name": "Child One",
    "message": "Heavy rain expected for Child One's area soon. National Weather Service: Flash Flood Warning.",
    "severity": "Warning", // e.g., "Warning", "Watch", "Advisory" or OWM specific
    "alert_source": "National Weather Service", // Example
    "details_url": "http://example.com/weather_alert_details", // Optional
    "timestamp": "2023-10-27T12:00:00Z"
  }
}
```

#### 1.4.9. Safe Zone Alert

- **`type`**: `safezone_alert` (typically sent via generic `send_notification`)
- **`message`** (if generic): Details about entering or leaving a safe zone.

```json
{
  "type": "send_notification",
  "message": {
    "type": "safezone_alert",
    "alert_id": 78, // ID of the created Alert object
    "child_id": 15,
    "child_name": "Child One",
    "zone_id": 3,
    "zone_name": "Home",
    "alert_type": "LEFT_ZONE", // or "ENTERED_ZONE"
    "message": "Child One has left Home.",
    "timestamp": "2023-10-27T12:05:00Z"
  }
}
```

#### 1.4.10. Low Battery Alert

- **`type`**: `low_battery_alert` (typically sent via generic `send_notification`)
- **`message`** (if generic): Warning about a child's device battery.

```json
{
  "type": "send_notification",
  "message": {
    "type": "low_battery_alert",
    "alert_id": 79, // ID of the created Alert object
    "child_id": 15,
    "child_name": "Child One",
    "battery_level": 18, // Percentage
    "message": "Child One's phone battery is low: 18%.",
    "timestamp": "2023-10-27T12:10:00Z"
  }
}
```

#### 1.4.11. Child Check-In

- **`type`**: `child_check_in` (typically sent via generic `send_notification`)
- **`message`** (if generic): Contains data from the child's check-in.

```json
{
  "type": "send_notification",
  "message": {
    "type": "child_check_in",
    "alert_id": 80, // ID of the created Alert object
    "data": { // Corresponds to FCM push_data for check-in
      "child_id": "15",
      "child_name": "Child One",
      "check_in_type": "ARRIVED_SAFELY", // e.g., "ARRIVED_SAFELY", "NEED_HELP_SOON", "CUSTOM"
      "message": "Child One Arrived Safely from School.",
      "latitude": "34.078900",
      "longitude": "-118.291200",
      "location_name": "School", // Optional
      "alert_id": "80", // Stringified alert_id
      "timestamp": "2023-10-27T12:15:00Z" // client_timestamp_iso
    }
  }
}
```

#### 1.4.12. Unusual Route Alert (Conceptual)

- **`type`**: `unusual_route_alert` (typically sent via generic `send_notification`)
- **`message`** (if generic): Details about a detected route anomaly.

```json
{
  "type": "send_notification",
  "message": {
    "type": "unusual_route_alert",
    "alert_id": 81, // ID of the created Alert object
    "child_id": 15,
    "child_name": "Child One",
    "message": "Child One seems to be taking an unusual route from School. Deviation detected from learned routine 'School Run'.",
    "routine_name": "School Run", // Optional: name of the learned routine
    "deviation_type": "PATH", // or "TIME", "BOTH"
    "current_latitude": 34.070000,
    "current_longitude": -118.280000,
    "timestamp": "2023-10-27T12:20:00Z"
    // May include more details like expected vs actual path snippet if feasible
  }
}
```

## 2. Firebase Cloud Messaging (FCM) Data Payloads

FCM messages are sent to notify users of important events when the app might be in the background or closed. The `data` payload of an FCM message is a JSON object containing key-value pairs. The client app uses these keys to determine how to handle the notification.

All FCM data payloads will include a `type` field to help the client app identify the nature of the alert.

### Common FCM Data Fields:
- `type`: (String) The type of notification (e.g., `new_message`, `sos_alert`).
- `alert_id`: (String) The ID of the corresponding `Alert` object in the database, if applicable.
- `child_id`: (String) The ID of the relevant child, if applicable.
- `child_name`: (String) The name of the relevant child, if applicable.

### 2.1. New Message

- **`title`**: "New message from {Sender Name}"
- **`body`**: "{Message Preview}"
- **`data` payload**:
  ```json
  {
    "type": "new_message",
    "message_id": "101",
    "sender_id": "2", // User ID of the sender
    "sender_name": "Child One", // Display name of sender
    "conversation_with_user_id": "2", // User ID of the other participant in conversation (the sender in this case)
    "child_sender_actual_id": "15", // Optional: Actual Child ID if sender is a child's proxy_user
    "content_preview": "Hello Dad!"
  }
  ```

### 2.2. SOS Alert

- **`title`**: "SOS Alert: {Child Name}"
- **`body`**: "{SOS Message Content, e.g., SOS triggered by Child One. Current location...}"
- **`data` payload**:
  ```json
  {
    "type": "sos_alert",
    "alert_id": "75",
    "child_id": "15",
    "child_name": "Child One",
    "latitude": "34.052235", // Optional, if location available
    "longitude": "-118.243683", // Optional
    "location_timestamp": "2023-10-27T10:40:00Z" // Optional, timestamp of provided/last known location
  }
  ```

### 2.3. Safe Zone Alert

- **`title`**: "Safe Zone Alert: {Child Name}"
- **`body`**: "{Child Name} has {entered/left} {Zone Name}."
- **`data` payload**:
  ```json
  {
    "type": "safezone_alert", // Could be 'ENTERED_ZONE' or 'LEFT_ZONE' for more specificity if preferred
    "alert_id": "78",
    "child_id": "15",
    "child_name": "Child One",
    "zone_id": "3",
    "zone_name": "Home",
    "alert_trigger_type": "LEFT_ZONE" // Explicitly "ENTERED_ZONE" or "LEFT_ZONE"
  }
  ```

### 2.4. Low Battery Alert

- **`title`**: "Low Battery Warning: {Child Name}"
- **`body`**: "{Child Name}'s phone battery is low: {Battery Level}%."
- **`data` payload**:
  ```json
  {
    "type": "low_battery_alert",
    "alert_id": "79",
    "child_id": "15",
    "child_name": "Child One",
    "battery_level": "18" // Stringified
  }
  ```

### 2.5. Contextual Weather Alert

- **`title`**: "Weather Alert for {Child Name}" or specific summary
- **`body`**: "{Alert Message, e.g., Heavy rain expected for Child One's area. National Weather Service: Flash Flood Warning.}"
- **`data` payload**:
  ```json
  {
    "type": "contextual_weather_alert",
    "alert_id": "77",
    "child_id": "15",
    "child_name": "Child One",
    "severity": "Warning", // Or other severity indicator
    "alert_source": "National Weather Service",
    "details_url": "http://example.com/weather_alert_details" // Optional
  }
  ```

### 2.6. Unusual Route Alert

- **`title`**: "Unusual Route Detected: {Child Name}"
- **`body`**: "{Alert Message, e.g., Child One seems to be taking an unusual route from School.}"
- **`data` payload**:
  ```json
  {
    "type": "unusual_route_alert",
    "alert_id": "81",
    "child_id": "15",
    "child_name": "Child One",
    "routine_name": "School Run", // Optional
    "deviation_type": "PATH", // Optional: "PATH", "TIME", "BOTH"
    "current_latitude": "34.070000", // Optional
    "current_longitude": "-118.280000" // Optional
  }
  ```

### 2.7. Child Check-In

- **`title`**: "Check-In: {Child Name}"
- **`body`**: "{Check-in message, e.g., Child One Arrived Safely from School.}"
- **`data` payload**:
  ```json
  {
    "type": "child_check_in",
    "alert_id": "80",
    "child_id": "15",
    "child_name": "Child One",
    "check_in_type": "ARRIVED_SAFELY", // e.g., "ARRIVED_SAFELY", "NEED_HELP_SOON", "CUSTOM"
    "message": "Child One Arrived Safely from School.", // Full message
    "latitude": "34.078900",
    "longitude": "-118.291200",
    "location_name": "School", // Optional
    "timestamp": "2023-10-27T12:15:00Z" // client_timestamp_iso
  }
  ```

### 2.8. ETA Started (Shared with a User)

- **`title`**: "ETA Share Started by {Sharer Name}"
- **`body`**: "Tracking {Sharer Name} to {Destination Name}. ETA: {ETA Time}"
- **`data` payload**:
  ```json
  {
    "type": "eta_started",
    "share_id": "5", // ID of the ActiveEtaShare object
    "sharer_id": "1",
    "sharer_name": "Parent User",
    "destination_name": "School",
    "eta": "2023-10-27T11:00:00Z" // ISO 8601 format ETA
    // Note: ETA updates, cancellations, arrivals for existing shares are typically handled via WebSocket only
    // to avoid excessive FCM notifications, unless a specific design choice is made to also push these.
  }
  ```

This documentation should provide a good overview for client developers integrating with the MauZenfan real-time features.
