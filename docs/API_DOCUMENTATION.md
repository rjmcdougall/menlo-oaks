# Menlo Oaks Security System — API Documentation

## Webhook Cloud Function

**Base URL:** `https://license-plate-webhook-66u7a42rhq-uc.a.run.app`

---

### POST /
Receive LPR alarm webhook from UniFi Protect. Stores detection in BigQuery, uploads thumbnail to GCS, checks for stolen/unknown plates, sends Telegram alerts.

**Request body:** UniFi Protect alarm webhook payload (JSON)

**Response 200:**
```json
{
  "status": "success",
  "message": "License plate data stored successfully",
  "plate_number": "ABC1234",
  "record_id": "uuid"
}
```

---

### POST /face
Receive face detection webhook from UniFi Protect. Downloads thumbnail from NVR, uploads to Google Photos, stores record in BigQuery.

---

### GET /health
Health check with dependency status (BigQuery, config, caches).

**Response 200:**
```json
{
  "status": "healthy",
  "bigquery": {"status": "healthy"},
  "stolen_plates": {"count": 3, "last_refresh": "..."},
  "known_plates": {"count": 1240, "last_refresh": "..."}
}
```

---

### GET /api
Machine-readable description of all endpoints (used by automation).

---

### POST /stolen
Add a plate to the stolen registry.

**Request body:**
```json
{"plate_number": "ABC1234"}
```

**Response 200:**
```json
{"status": "success", "plate_number": "ABC1234", "message": "Plate added to stolen registry"}
```

---

### GET /stolen
List all plates in the stolen registry.

**Response 200:**
```json
{
  "status": "success",
  "plates": [
    {"plate_number": "ABC1234", "inserted_at": "2026-01-15T10:30:00"}
  ],
  "count": 1
}
```

---

### DELETE /stolen
Remove a plate from the stolen registry.

**Request body:**
```json
{"plate_number": "ABC1234"}
```

**Response 200:**
```json
{"status": "success", "plate_number": "ABC1234", "message": "Plate removed from stolen registry"}
```

---

## Alert Logic

Every LPR detection runs through:

1. **Store** — thumbnail → GCS; detection record → BigQuery `detections`
2. **Camera lookup** — `device_id` resolved to `camera_name`/`camera_location` from `camera_lookup` table
3. **Stolen check** — plate looked up in `stolenplates` (15-min in-memory cache). If stolen → Telegram 🚨
4. **Unknown check** — plate checked against `known_plates` cache (plates seen on <20 distinct days = unknown). If unknown → rolling 10-min window counter incremented. If count >10 in 10 min → Telegram 🔍

---

## Webserver (Map Dashboard)

**Base URL:** `https://detection-map-66u7a42rhq-uc.a.run.app`

---

### GET /api/detections
Query detection records with optional filters.

**Query params:**
- `start_date` — ISO date string
- `end_date` — ISO date string
- `camera` — camera name filter
- `unknown_only` — `true` to filter unknown plates only
- `limit` — max records (default 1000)

---

### GET /api/cameras
All camera locations with detection counts.

---

### GET /api/plates/search
Autocomplete search for plate numbers.

**Query params:** `q` — partial plate string

---

### GET /api/plates/\<plate\>/locations
All camera locations where the plate was detected.

---

### GET /api/plates/\<plate\>/detections
Full detection history for a plate.

---

### GET /api/unknown-activity
Unknown plates with >10 detections in any 10-min window, over the past 24 hours.

**Response:**
```json
[
  {
    "plate_number": "XYZ123",
    "camera_name": "Entrada Gate",
    "camera_location": "Entrada Dr",
    "latitude": 37.44,
    "longitude": -122.18,
    "max_detections_in_10min": 14,
    "detection_count": 22,
    "first_seen": "2026-03-28T10:00:00",
    "last_seen": "2026-03-28T10:45:00",
    "is_recent": true
  }
]
```

`is_recent` is `true` if `last_seen` is within the past 10 minutes.

---

### GET /api/camera-lookup
All rows from `camera_lookup` table plus any device_ids in `detections` that are not registered.

**Response:**
```json
[
  {
    "device_id": "abc123",
    "camera_name": "Entrada Gate",
    "camera_location": "Entrada Dr",
    "latitude": 37.44,
    "longitude": -122.18,
    "camera_model": "UVC-G4-Pro",
    "is_active": true,
    "notes": null,
    "installation_date": null,
    "registered": true,
    "detection_count": 45231
  }
]
```

Unregistered entries have `registered: false` and `camera_name: null`.

---

### POST /api/camera-lookup
Add a new camera_lookup row.

**Request body:**
```json
{
  "device_id": "abc123",
  "camera_name": "New Camera",
  "camera_location": "Oak Ave",
  "latitude": 37.44,
  "longitude": -122.18,
  "camera_model": "UVC-G4-Pro",
  "is_active": true,
  "notes": "Installed March 2026",
  "installation_date": "2026-03-01"
}
```

---

### PUT /api/camera-lookup/\<device_id\>
Update an existing camera_lookup row (partial update supported).

---

### DELETE /api/camera-lookup/\<device_id\>
Delete a camera_lookup row.

---

## BigQuery Tables (`menlo-oaks.license_plates`)

| Table | Description |
|-------|-------------|
| `detections` | All LPR events (~2.3M rows as of Mar 2026). `detection_timestamp` is DATETIME. |
| `facedetection` | Face detection events, partitioned by day |
| `stolenplates` | Stolen plate registry (`plate_number`, `inserted_at`) |
| `camera_lookup` | Camera metadata (`device_id`, `camera_name`, `camera_location`, `latitude`, `longitude`, `camera_model`, `is_active`, `notes`, `installation_date`, `camera_id`, `created_at`, `updated_at`) |
| `detections_with_camera_info` | View joining `detections` + `camera_lookup` on `device_id` |

---

## Environment Variables

### Webhook Function

| Variable | Description |
|----------|-------------|
| `GCP_PROJECT_ID` | `menlo-oaks` |
| `BIGQUERY_DATASET` | `license_plates` |
| `BIGQUERY_TABLE` | `detections` |
| `GCS_BUCKET` | GCS bucket for thumbnails |
| `UNIFI_PROTECT_HOST` | NVR host (`10.0.9.70`) |
| `UNIFI_PROTECT_PORT` | NVR port (`443`) |
| `UNIFI_PROTECT_TOKEN` | NVR API token |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Telegram channel ID (`-1003697610260`) |
| `GOOGLE_PHOTOS_TOKEN` | Google Photos OAuth token |

### Webserver Function

| Variable | Description |
|----------|-------------|
| `GCP_PROJECT_ID` | `menlo-oaks` |
| `BIGQUERY_DATASET` | `license_plates` |
| `MAPBOX_ACCESS_TOKEN` | Mapbox GL JS token |
