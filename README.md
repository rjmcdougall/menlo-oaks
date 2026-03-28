# Menlo Oaks — License Plate & Security Detection System

A production system for detecting and tracking license plates from UniFi Protect cameras, with real-time stolen/unknown vehicle alerting, a face detection pipeline, and a web map dashboard.

**Deployed on:** Google Cloud (project `menlo-oaks`, region `us-central1`)

---

## Architecture

```
┌─────────────────────┐     ┌──────────────────────────────┐     ┌──────────────────┐
│  UniFi Protect NVR  │────▶│  Webhook (Cloud Function)    │────▶│  BigQuery        │
│  Cameras / LPR      │     │  license-plate-webhook       │     │  license_plates  │
└─────────────────────┘     └──────────────────────────────┘     └──────────────────┘
                                          │                               │
                             ┌────────────┼────────────┐                 │
                             ▼            ▼            ▼                 │
                        ┌─────────┐  ┌────────┐  ┌──────────┐           │
                        │   GCS   │  │Telegram│  │ Google   │           │
                        │thumbnails│  │ Alerts │  │ Photos   │           │
                        └─────────┘  └────────┘  └──────────┘           │
                                                                         │
                             ┌───────────────────────────┐               │
                             │  Webserver (Cloud Function)│◀─────────────┘
                             │  detection-map             │
                             └───────────────────────────┘
```

### BigQuery Tables (`license_plates` dataset)

| Table | Description |
|---|---|
| `detections` | All LPR events (~2.3M rows as of Mar 2026) |
| `facedetection` | Face detection events, partitioned by day |
| `stolenplates` | Stolen plate registry (`plate_number`, `inserted_at`) |
| `camera_lookup` | Camera metadata (`device_id`, name, location, lat/lng, model) |
| `detections_with_camera_info` | View joining detections + camera_lookup |

---

## Project Structure

```
protectmenlo/
├── README.md
├── webhook/                        # Cloud Function — receives UniFi Protect webhooks
│   ├── main.py                     # Router + all webhook handlers
│   ├── config.py                   # Configuration from environment variables
│   ├── bigquery_client.py          # LPR detection storage
│   ├── gcs_client.py               # Thumbnail storage (GCS)
│   ├── face_webhook.py             # Face detection webhook handler
│   ├── photos_client.py            # Google Photos upload (face thumbnails)
│   ├── stolen_plates.py            # Stolen plate registry (BQ + in-memory cache)
│   ├── known_plates.py             # Known plate cache (seen ≥20 distinct days)
│   ├── recent_detections.py        # Rolling 10-min detection counter (in-memory)
│   ├── camera_lookup.py            # Camera name/location lookup from BQ
│   ├── telegram_client.py          # Telegram Bot API alerts
│   ├── deploy.sh                   # Deployment script (preserves secrets)
│   └── requirements.txt
├── webserver/                      # Cloud Function — map dashboard
│   ├── main.py                     # Flask app + API endpoints
│   ├── templates/map.html          # Single-page app (map, stats, controls, settings)
│   ├── deploy.sh
│   └── requirements.txt
├── scripts/                        # Utility & maintenance scripts
│   ├── backfill_face_photos.py     # Batch-upload historical face thumbnails to Google Photos
│   ├── backfill_detections.py      # Backfill historical LPR data
│   ├── create_camera_lookup.py     # Initial camera_lookup table setup
│   ├── update_camera_lookup.py     # Update camera metadata
│   └── sql/                        # BigQuery SQL queries
└── docs/                           # Additional documentation
```

---

## Webhook Cloud Function

**URL:** `https://license-plate-webhook-66u7a42rhq-uc.a.run.app`

### Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/` | POST | LPR alarm webhook from UniFi Protect |
| `/face` | POST | Face detection webhook from UniFi Protect |
| `/stolen` | POST | Add a plate to the stolen registry |
| `/stolen` | GET | List all stolen plates |
| `/stolen` | DELETE | Remove a plate from the stolen registry |
| `/health` | GET | Health check with dependency status |
| `/api` | GET | Machine-readable API description (used by automation) |

### Real-time Alert Logic

Every LPR detection runs through this pipeline:

1. **Store** — thumbnail downloaded from NVR → GCS; detection record → BigQuery
2. **Camera lookup** — `device_id` resolved to `camera_name`/`camera_location` from `camera_lookup` table
3. **Stolen check** — plate looked up in `stolenplates` BQ table (15-min in-memory cache). If stolen → Telegram alert 🚨
4. **Unknown check** — plate checked against `known_plates` cache (seen on <20 distinct days = unknown). If unknown → rolling 10-min window counter incremented. If count >10 in 10 min → Telegram alert 🔍

### In-memory Caches (per Cloud Function instance)

| Cache | TTL | Source |
|---|---|---|
| Stolen plates | 15 min | `license_plates.stolenplates` |
| Known plates | 1 hour | `license_plates.detections` (HAVING COUNT(DISTINCT DATE) ≥ 20) |
| Recent detections | Rolling 10-min deque | In-memory only |
| Camera lookup | Cold-start only | `license_plates.camera_lookup` |

### Deploy

```bash
cd webhook
./deploy.sh production menlo-oaks
```

The deploy script preserves sensitive env vars (Telegram, Google Photos, GCS, UniFi) across redeploys. See `/Users/rmc/docs/menlooaks/runtime-config.md` for all secret values (local only, never committed).

---

## Webserver (Map Dashboard)

**URL:** `https://detection-map-66u7a42rhq-uc.a.run.app`

### Features

- **Interactive Mapbox map** of all LPR detections with thumbnails
- **Unknown Activity overlay** (on by default) — car markers per unknown plate that exceeded 10 detections in a 10-min window over the past 24h; live plates pulse red
- **Date/camera/plate filtering** with autocomplete
- **Stats dashboard** — totals, active cameras, unique plates
- **Settings tab** — full CRUD editor for the `camera_lookup` table; shows all device IDs seen in detections (unregistered ones highlighted in amber with detection counts)

### API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/detections` | GET | Query detections (date range, camera, unknown_only) |
| `/api/cameras` | GET | Camera list with detection counts |
| `/api/plates/search` | GET | Plate number autocomplete |
| `/api/plates/<plate>/locations` | GET | All camera locations for a plate |
| `/api/plates/<plate>/detections` | GET | Detection history for a plate |
| `/api/unknown-activity` | GET | Unknown plates with >10 detections in any 10-min window (past 24h) |
| `/api/camera-lookup` | GET | All camera_lookup rows + unregistered device_ids from detections |
| `/api/camera-lookup` | POST | Add a camera_lookup row |
| `/api/camera-lookup/<device_id>` | PUT | Update a camera_lookup row |
| `/api/camera-lookup/<device_id>` | DELETE | Delete a camera_lookup row |

### Deploy

```bash
cd webserver
GCP_PROJECT_ID=menlo-oaks BIGQUERY_DATASET=license_plates MAPBOX_ACCESS_TOKEN=<token> ./deploy.sh
```

---

## Telegram Alerts

Alerts go to the **Menlo Oaks Security Bot** channel (`-1003697610260`).

| Alert | Trigger |
|---|---|
| 🚨 STOLEN PLATE DETECTED | Plate matches `stolenplates` table |
| 🔍 UNKNOWN PLATE DETECTED | Unknown plate seen >10 times in 10 min |

---

## Face Detection Pipeline

UniFi Protect sends face detection events to `POST /face`. The handler:
1. Downloads thumbnail from NVR (`/proxy/protect/api/events/{id}/thumbnail`)
2. Uploads to Google Photos album (`facedetection`)
3. Stores event record in `license_plates.facedetection`

**Backfill historical face events:**
```bash
cd scripts
python backfill_face_photos.py \
  --token <NVR_TOKEN> --csrf <CSRF_TOKEN> \
  --all --project menlo-oaks
```

---

## Monitoring

```bash
# Webhook logs
gcloud functions logs read license-plate-webhook --region=us-central1 --project=menlo-oaks

# Webserver logs
gcloud functions logs read detection-map --region=us-central1 --project=menlo-oaks

# Health checks
curl https://license-plate-webhook-66u7a42rhq-uc.a.run.app/health
curl https://license-plate-webhook-66u7a42rhq-uc.a.run.app/api
```

---

## Configuration & Secrets

Runtime secrets (Telegram, Google Photos OAuth, NVR host, etc.) are documented locally at:
```
/Users/rmc/docs/menlooaks/runtime-config.md
```
This file is **never committed to git**.
