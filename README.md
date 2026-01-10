# UniFi Protect License Plate Detection

A system for detecting and tracking license plates from UniFi Protect cameras, consisting of a webhook receiver (Cloud Function), a web-based map dashboard, and utility scripts.

## Features

- **Real-time Processing**: Receives webhooks from UniFi Protect immediately when license plates are detected
- **Multiple Webhook Formats**: Supports both alarm-based triggers and smart detection events
- **BigQuery Integration**: Stores detection data with full schema in BigQuery for analysis
- **Thumbnail Storage**: Optional image storage in Google Cloud Storage (full scene + cropped plates)
- **Web Dashboard**: Interactive map interface to view and search detections
- **Vehicle Attributes**: Extracts vehicle type and color when available
- **Health Monitoring**: Comprehensive health check endpoints with dependency status

## Architecture

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────┐
│  UniFi Protect  │────▶│  Webhook             │────▶│  BigQuery   │
│  Cameras        │     │  (Cloud Function)    │     │  (data)     │
└─────────────────┘     └──────────────────────┘     └─────────────┘
                                   │                        │
                                   ▼                        │
                        ┌─────────────────────┐            │
                        │  Cloud Storage      │            │
                        │  (thumbnails)       │            │
                        └─────────────────────┘            │
                                                           │
                        ┌─────────────────────┐            │
                        │  Webserver          │◀───────────┘
                        │  (Map Dashboard)    │
                        └─────────────────────┘
```

## Project Structure

```
protectmenlo/
├── README.md                   # This file
├── webhook/                    # Cloud Function - receives UniFi Protect webhooks
│   ├── main.py                 # Entry point & webhook handler
│   ├── config.py               # Configuration management
│   ├── bigquery_client.py      # BigQuery data storage
│   ├── gcs_client.py           # Cloud Storage for thumbnails
│   ├── unifi_protect_client.py # UniFi Protect API client
│   ├── deploy.sh               # Deployment script
│   ├── requirements.txt        # Python dependencies
│   ├── .env.template           # Environment variable template
│   └── .gcloudignore           # Files to exclude from deployment
├── webserver/                  # Flask web app - map dashboard & API
│   ├── main.py                 # Flask app with API endpoints
│   ├── templates/              # HTML templates
│   │   └── map.html            # Interactive map interface
│   ├── static/                 # Static assets (CSS, JS)
│   ├── deploy.sh               # Deployment script
│   └── requirements.txt        # Python dependencies
├── scripts/                    # Utility & maintenance scripts
│   ├── backfill_detections.py  # Backfill historical data
│   ├── create_camera_lookup.py # Camera location setup
│   ├── update_camera_lookup.py # Update camera metadata
│   ├── query_images.py         # Query stored images
│   ├── setup_env.py            # Environment setup helper
│   ├── test_*.py               # Test scripts
│   ├── debug_*.py              # Debug utilities
│   └── sql/                    # SQL scripts
└── docs/                       # Documentation
    ├── API_DOCUMENTATION.md    # Webhook API reference
    ├── CLI_COMMANDS_REFERENCE.md
    ├── IMAGE_URLS_GUIDE.md
    ├── README_BACKFILL.md
    └── THUMBNAIL_IMPLEMENTATION.md
```

## Components

### Webhook (Cloud Function)

Receives license plate detection events from UniFi Protect and stores them in BigQuery.

```bash
cd webhook
./deploy.sh production your-project-id
```

See [docs/API_DOCUMENTATION.md](docs/API_DOCUMENTATION.md) for webhook API details.

### Webserver (Map Dashboard)

Interactive web interface for viewing detections on a map, searching plates, and viewing statistics.

```bash
cd webserver
./deploy.sh production your-project-id
```

**Features:**
- Mapbox-powered interactive map
- Date range filtering
- Camera location filtering
- Plate search with autocomplete
- "Unknown vehicles" filter (plates seen < 20 times)
- Detection history per plate

### Scripts

Utility scripts for setup, maintenance, and debugging.

```bash
cd scripts
python backfill_detections.py  # Backfill historical data
python create_camera_lookup.py # Set up camera locations
```

## Quick Start

### 1. Configure Webhook

```bash
cd webhook
cp .env.template .env.development
# Edit .env.development with your values
```

### 2. Deploy Webhook

```bash
cd webhook
chmod +x deploy.sh
./deploy.sh production your-project-id
```

### 3. Configure UniFi Protect

Point your UniFi Protect webhook to:
```
https://<region>-<project-id>.cloudfunctions.net/license-plate-webhook
```

### 4. Deploy Webserver (Optional)

```bash
cd webserver
./deploy.sh production your-project-id
```

## Local Development

### Webhook

```bash
cd webhook
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export GCP_PROJECT_ID=your-project-id
python main.py
# Runs on http://localhost:8080
```

### Webserver

```bash
cd webserver
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export GCP_PROJECT_ID=your-project-id
export MAPBOX_ACCESS_TOKEN=your-token
python main.py
# Runs on http://localhost:8080
```

## Configuration

### Webhook Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GCP_PROJECT_ID` | Yes | - | Google Cloud project ID |
| `BIGQUERY_DATASET` | No | `license_plates` | BigQuery dataset name |
| `BIGQUERY_TABLE` | No | `detections` | BigQuery table name |
| `WEBHOOK_SECRET` | No | - | Webhook signature validation |
| `MIN_CONFIDENCE_THRESHOLD` | No | `0.7` | Minimum detection confidence |
| `STORE_IMAGES` | No | `false` | Enable thumbnail storage |
| `GCS_THUMBNAIL_BUCKET` | No | `menlo_oaks_thumbnails` | GCS bucket for images |

See [webhook/.env.template](webhook/.env.template) for full list.

### Webserver Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GCP_PROJECT_ID` | Yes | Google Cloud project ID |
| `BIGQUERY_DATASET` | No | BigQuery dataset (default: `license_plates`) |
| `MAPBOX_ACCESS_TOKEN` | Yes | Mapbox API token for map rendering |

## API Endpoints

### Webhook

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/` | POST | Receive webhook from UniFi Protect |

### Webserver

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Map interface |
| `/api/detections` | GET | Query detections with filters |
| `/api/cameras` | GET | List camera locations |
| `/api/plates/search` | GET | Search plates (autocomplete) |
| `/api/plates/<plate>/locations` | GET | Locations where plate was seen |
| `/api/plates/<plate>/detections` | GET | Detection history for plate |

## Monitoring

### Webhook Logs

```bash
gcloud functions logs read license-plate-webhook --region=us-central1
```

### Health Checks

```bash
# Webhook
curl https://<webhook-url>/health

# Webserver
curl https://<webserver-url>/health
```

## Documentation

- [API Documentation](docs/API_DOCUMENTATION.md) - Webhook request/response formats
- [Backfill Guide](docs/README_BACKFILL.md) - Backfilling historical data
- [Thumbnail Implementation](docs/THUMBNAIL_IMPLEMENTATION.md) - Image storage details
- [Image URLs Guide](docs/IMAGE_URLS_GUIDE.md) - Working with stored images
- [CLI Commands](docs/CLI_COMMANDS_REFERENCE.md) - Useful CLI commands

## License

Private - All rights reserved
