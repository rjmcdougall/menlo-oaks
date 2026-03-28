# Webserver Project Summary

## Overview
Flask-based Google Cloud Function serving the Menlo Oaks security map dashboard. Displays license plate detections on an interactive Mapbox map with real-time unknown activity alerts.

**Deployed URL:** `https://detection-map-66u7a42rhq-uc.a.run.app`

## Architecture
- **Backend**: Python Flask app deployed as Google Cloud Function (Gen2)
- **Database**: Google BigQuery (`menlo-oaks.license_plates`)
- **Frontend**: Mapbox GL JS single-page app (all CSS/JS inline in `map.html`)
- **Deployment**: `./deploy.sh` (requires `GCP_PROJECT_ID`, `BIGQUERY_DATASET`, `MAPBOX_ACCESS_TOKEN`)

## Key Files
- `main.py` — Flask app with all API endpoints and Cloud Function entry point
- `templates/map.html` — Single-page app: map, stats, plate search, settings tab, unknown activity overlay
- `requirements.txt` — Dependencies: Flask, functions-framework, google-cloud-bigquery
- `deploy.sh` — Deployment script

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `GET /` | GET | Main map interface |
| `GET /api/detections` | GET | Query detections (date range, camera, unknown_only) |
| `GET /api/cameras` | GET | Camera list with detection counts |
| `GET /api/plates/search` | GET | Plate number autocomplete |
| `GET /api/plates/<plate>/locations` | GET | All camera locations for a plate |
| `GET /api/plates/<plate>/detections` | GET | Detection history for a plate |
| `GET /api/unknown-activity` | GET | Unknown plates with >10 detections in any 10-min window (past 24h) |
| `GET /api/camera-lookup` | GET | All camera_lookup rows + unregistered device_ids from detections |
| `POST /api/camera-lookup` | POST | Add a camera_lookup row |
| `PUT /api/camera-lookup/<device_id>` | PUT | Update a camera_lookup row |
| `DELETE /api/camera-lookup/<device_id>` | DELETE | Delete a camera_lookup row |

## Data Model

Queries `detections_with_camera_info` view (join of `detections` + `camera_lookup`):
- Detection: `record_id`, `plate_number`, `confidence`, `detection_timestamp`, `device_id`
- Vehicle: `vehicle_type`, `vehicle_color`
- Camera: `camera_name`, `camera_location`, `latitude`, `longitude`, `camera_model`, `is_active`
- Media: `thumbnail_public_url`, `cropped_thumbnail_public_url`

`detection_timestamp` is **DATETIME** type (not TIMESTAMP) — use `DATETIME_SUB(CURRENT_DATETIME(), ...)` not `TIMESTAMP_SUB`.

The `unknown-activity` endpoint uses a BigQuery window function:
```sql
COUNT(*) OVER (
    PARTITION BY plate_number
    ORDER BY UNIX_SECONDS(TIMESTAMP(detection_timestamp))
    RANGE BETWEEN 600 PRECEDING AND CURRENT ROW
) AS detections_in_10min
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `GCP_PROJECT_ID` | Google Cloud project ID (`menlo-oaks`) |
| `BIGQUERY_DATASET` | BigQuery dataset (`license_plates`) |
| `MAPBOX_ACCESS_TOKEN` | Mapbox API token |

## Features

- **Interactive Mapbox map** with detection markers and thumbnail popups
- **Unknown Activity overlay** — car markers (🚗) per unknown plate that exceeded 10 detections in 10 min, one color per plate with legend; pulsing red ring for plates active in past 10 min; on by default
- **Date/camera/plate filtering** with autocomplete
- **Stats dashboard** — totals, active cameras, unique plates
- **Settings tab** — full CRUD editor for `camera_lookup` table; unregistered device_ids (in detections but not camera_lookup) highlighted amber with detection counts

## Local Development

```bash
GCP_PROJECT_ID=menlo-oaks BIGQUERY_DATASET=license_plates MAPBOX_ACCESS_TOKEN=<token> python main.py
```
Serves on `http://localhost:8080`.
