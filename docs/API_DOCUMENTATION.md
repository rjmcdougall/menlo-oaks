# UniFi Protect License Plate Detector - API Documentation

## Overview

This Google Cloud Function receives license plate detection webhooks from UniFi Protect cameras and stores the data in BigQuery. It also provides a health check endpoint for monitoring.

**Base URL:** `https://<region>-<project-id>.cloudfunctions.net/<function-name>`

---

## Endpoints

### 1. Health Check

Check the health and status of the Cloud Function and its dependencies.

**Endpoint:** `GET /health` or `GET /`

**Method:** `GET`

**Authentication:** None required

#### Success Response (200 OK)

```json
{
  "status": "healthy",
  "service": "unifi-protect-license-plate-detector",
  "version": "2.0.0",
  "timestamp": "2024-01-15T10:30:00.000000",
  "environment": {
    "function_name": "license-plate-detector",
    "gcp_project": "your-project-id",
    "region": "us-central1"
  },
  "configuration": {
    "status": "healthy",
    "warnings": [],
    "bigquery_dataset": "license_plates",
    "bigquery_table": "detections",
    "webhook_auth": true,
    "unifi_protect_configured": true
  },
  "bigquery": {
    "status": "healthy",
    "dataset_location": "US",
    "table_created": "2024-01-01T00:00:00",
    "table_rows": 12345,
    "last_check": "2024-01-15T10:30:00.000000"
  }
}
```

#### Degraded Response (200 OK)

Returned when the function is operational but some non-critical components have issues:

```json
{
  "status": "degraded",
  "service": "unifi-protect-license-plate-detector",
  "timestamp": "2024-01-15T10:30:00.000000",
  "bigquery": {
    "status": "warning",
    "message": "Could not verify BigQuery connectivity",
    "error": "Connection timeout"
  }
}
```

#### Unhealthy Response (503 Service Unavailable)

```json
{
  "status": "unhealthy",
  "service": "unifi-protect-license-plate-detector",
  "timestamp": "2024-01-15T10:30:00.000000",
  "configuration": {
    "status": "unhealthy",
    "issues": ["Missing GCP_PROJECT_ID"],
    "warnings": []
  }
}
```

#### Error Response (405 Method Not Allowed)

```json
{
  "status": "error",
  "message": "Health check only supports GET method",
  "timestamp": "2024-01-15T10:30:00.000000"
}
```

---

### 2. License Plate Webhook

Receive and process license plate detection events from UniFi Protect.

**Endpoint:** `POST /`

**Method:** `POST`

**Content-Type:** `application/json`

**Authentication:** Optional webhook signature via `X-UniFi-Signature` header (if `WEBHOOK_SECRET` is configured)

#### Request Body

The function accepts two webhook formats:

##### Format 1: Alarm-Based (Triggers)

```json
{
  "alarm": {
    "triggers": [
      {
        "key": "license_plate_unknown",
        "value": "ABC1234",
        "timestamp": "2024-01-15T10:30:00.000Z",
        "device": "camera-device-id",
        "eventId": "event-uuid",
        "zones": {},
        "group": {
          "name": "Group Name"
        }
      }
    ],
    "thumbnail": "data:image/jpeg;base64,/9j/4AAQSkZJRg..."
  },
  "camera": {
    "id": "camera-id",
    "name": "Front Entrance Camera",
    "location": "Main Gate"
  },
  "event": {
    "id": "event-uuid",
    "start": "2024-01-15T10:30:00.000Z"
  },
  "snapshot": {
    "url": "https://...",
    "width": 1920,
    "height": 1080
  },
  "location": {
    "lat": 37.4419,
    "lng": -122.1430
  }
}
```

**Trigger Key Types:**
- `license_plate_unknown` - Unrecognized plate detected
- `license_plate_known` - Known/registered plate detected
- `license_plate` - Generic plate detection
- `vehicle` - Vehicle detected (may contain embedded plate data)

##### Format 2: Smart Detection (Legacy)

```json
{
  "type": "smart_detection",
  "metadata": {
    "detected_thumbnails": [
      {
        "type": "vehicle",
        "name": "ABC1234",
        "clock_best_wall": "2024-01-15T10:30:00.000Z",
        "cropped_id": "cropped-thumbnail-id",
        "attributes": {
          "vehicle_type": {
            "val": "car",
            "confidence": 0.95
          },
          "color": {
            "val": "blue",
            "confidence": 0.87
          }
        }
      }
    ]
  }
}
```

#### Success Response (200 OK)

```json
{
  "status": "success",
  "message": "License plate data stored successfully",
  "plate_number": "ABC1234",
  "record_id": "uuid-of-record"
}
```

For multiple plates detected in a single event:

```json
{
  "status": "success",
  "message": "License plate data stored successfully",
  "plate_number": "ABC1234, XYZ5678",
  "record_id": "uuid-of-first-record",
  "total_plates": 2,
  "all_record_ids": ["uuid-1", "uuid-2"]
}
```

#### Error Responses

**400 Bad Request** - Invalid request format:

```json
{
  "error": "Request must be JSON"
}
```

```json
{
  "error": "Empty request body"
}
```

**401 Unauthorized** - Invalid webhook signature:

```json
{
  "error": "Invalid signature"
}
```

**405 Method Not Allowed** - Wrong HTTP method:

```json
{
  "error": "Only POST requests are allowed for webhooks"
}
```

**404 Not Found** - Invalid endpoint:

```json
{
  "error": "Invalid endpoint",
  "message": "Use POST for webhooks or GET /health for health checks",
  "received": {
    "method": "PUT",
    "path": "/invalid"
  }
}
```

**500 Internal Server Error** - Processing failure:

```json
{
  "status": "error",
  "message": "No valid license plate data found"
}
```

```json
{
  "status": "error",
  "message": "Internal server error"
}
```

---

## Data Storage

### BigQuery Schema

Detection records are stored in BigQuery with the following fields:

| Field | Type | Description |
|-------|------|-------------|
| `record_id` | STRING | Unique identifier for the detection |
| `plate_number` | STRING | Detected license plate number |
| `confidence` | FLOAT | Detection confidence score (0-1) |
| `detection_timestamp` | TIMESTAMP | When the detection occurred |
| `plate_detection_timestamp` | TIMESTAMP | Original timestamp from webhook |
| `vehicle_type` | STRING | Type of vehicle (car, truck, etc.) |
| `vehicle_type_confidence` | FLOAT | Vehicle type confidence |
| `vehicle_color` | STRING | Vehicle color |
| `vehicle_color_confidence` | FLOAT | Color confidence |
| `camera_id` | STRING | UniFi camera device ID |
| `camera_name` | STRING | Camera display name |
| `camera_location` | STRING | Camera location description |
| `event_id` | STRING | UniFi Protect event ID |
| `event_timestamp` | TIMESTAMP | Event start time |
| `detection_type` | STRING | Type of detection trigger |
| `thumbnail_public_url` | STRING | URL to stored thumbnail image |
| `cropped_thumbnail_public_url` | STRING | URL to cropped plate image |
| `snapshot_url` | STRING | Original snapshot URL |
| `latitude` | FLOAT | Camera latitude |
| `longitude` | FLOAT | Camera longitude |
| `raw_detection_data` | STRING | Full webhook payload (JSON) |

### Thumbnail Storage (Google Cloud Storage)

When image storage is enabled (`STORE_IMAGES=true`), thumbnails are uploaded to GCS:

- **Alarm thumbnails**: Full scene images from detection events
- **Cropped thumbnails**: Cropped license plate images (requires `STORE_CROPPED_THUMBNAILS=true`)
- **Event snapshots**: High-resolution snapshots (requires `STORE_EVENT_SNAPSHOTS=true`)

---

## Configuration

### Required Environment Variables

| Variable | Description |
|----------|-------------|
| `GCP_PROJECT_ID` | Google Cloud project ID |
| `BIGQUERY_DATASET` | BigQuery dataset name |
| `BIGQUERY_TABLE` | BigQuery table name |

### Optional Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WEBHOOK_SECRET` | - | Secret for webhook signature validation |
| `STORE_IMAGES` | `false` | Enable thumbnail storage to GCS |
| `STORE_CROPPED_THUMBNAILS` | `false` | Store cropped plate images |
| `STORE_EVENT_SNAPSHOTS` | `false` | Store full event snapshots |
| `UNIFI_PROTECT_HOST` | - | UniFi Protect controller hostname |
| `UNIFI_PROTECT_PORT` | `443` | UniFi Protect controller port |

---

## Local Development

Run the function locally:

```bash
python main.py
```

The server starts on `http://0.0.0.0:8080` with:
- Health check: `GET http://localhost:8080/health`
- Webhooks: `POST http://localhost:8080/`

### Example Webhook Test

```bash
curl -X POST http://localhost:8080/ \
  -H "Content-Type: application/json" \
  -d '{
    "alarm": {
      "triggers": [
        {
          "key": "license_plate_unknown",
          "value": "TEST123",
          "device": "test-camera",
          "eventId": "test-event-1"
        }
      ]
    }
  }'
```

### Example Health Check

```bash
curl http://localhost:8080/health
```
