# Webserver Project Summary

## Overview
This is a **License Plate Detection Map** web application for "Protect Menlo". It's a Flask-based Google Cloud Function that displays license plate detection events on an interactive Mapbox map.

## Architecture
- **Backend**: Python Flask app deployed as a Google Cloud Function
- **Database**: Google BigQuery for storing detection data
- **Frontend**: Mapbox GL JS interactive map with responsive UI
- **Deployment**: Google Cloud Functions via `deploy.sh`

## Key Files
- `main.py` - Flask application with API endpoints and Cloud Function entry point
- `templates/map.html` - Single-page app with map interface, stats dashboard
- `requirements.txt` - Dependencies: Flask, functions-framework, google-cloud-bigquery

## API Endpoints
| Endpoint | Description |
|----------|-------------|
| `GET /` | Main map interface |
| `GET /api/detections` | Query detections with filters (date range, camera, unknown_only) |
| `GET /api/cameras` | List all camera locations with detection counts |
| `GET /api/plates/search` | Autocomplete search for plate numbers |
| `GET /api/plates/<plate>/locations` | Get all locations where a plate was detected |
| `GET /api/plates/<plate>/detections` | Detailed detection history for a plate |

## Data Model
Queries a BigQuery view `detections_with_camera_info` containing:
- Detection info: `record_id`, `plate_number`, `confidence`, `detection_timestamp`
- Vehicle info: `vehicle_type`, `vehicle_color`
- Camera info: `camera_name`, `camera_location`, `latitude`, `longitude`, `camera_model`, `camera_active`
- Media: `thumbnail_public_url`, `cropped_thumbnail_public_url`

## Environment Variables
- `GCP_PROJECT_ID` - Google Cloud project ID
- `BIGQUERY_DATASET` - BigQuery dataset name (default: `license_plates`)
- `MAPBOX_ACCESS_TOKEN` - Mapbox API token for map rendering

## Features
- Interactive map with detection markers
- Date range filtering
- Camera location filtering
- "Unknown only" filter (plates seen < 20 times)
- Plate search with autocomplete
- Detection history per plate
- Stats dashboard
- Thumbnail images in popups

## Local Development
Run with: `python main.py` (serves on port 8080)
