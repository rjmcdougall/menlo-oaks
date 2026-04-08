"""
Burglar alarm webhook handler for UniFi Protect.
Processes burglar alarm payloads, stores records to BigQuery,
uploads thumbnails to GCS, and sends Telegram alerts.
"""

import base64
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from google.cloud import bigquery
from google.cloud.exceptions import Forbidden, NotFound

logger = logging.getLogger(__name__)

BURGLAR_DETECTION_TYPES = {"burglar"}
BURGLAR_TABLE = "burglar_alarms"

SCHEMA = [
    bigquery.SchemaField("record_id",            "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("detection_timestamp",  "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("event_id",             "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("detection_type",       "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("device_id",            "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("camera_name",          "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("camera_location",      "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("thumbnail_url",        "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("created_at",           "TIMESTAMP", mode="REQUIRED"),
]


class BurglarAlarmHandler:
    """Handles burglar alarm webhook events."""

    def __init__(self, project_id: str, dataset_id: str, gcs_client=None,
                 camera_lookup=None, telegram_client=None, mapbox_token: str = ""):
        self.project_id = project_id
        self.dataset_id = dataset_id
        self.gcs_client = gcs_client
        self.camera_lookup = camera_lookup
        self.telegram_client = telegram_client
        self.mapbox_token = mapbox_token
        self.bq = bigquery.Client(project=project_id)
        self._ensure_table_exists()

    def _table_ref(self):
        return self.bq.dataset(self.dataset_id).table(BURGLAR_TABLE)

    def _ensure_table_exists(self):
        ref = self._table_ref()
        try:
            self.bq.get_table(ref)
            logger.info(f"Table {BURGLAR_TABLE} exists")
        except Forbidden:
            logger.info(f"No permission to inspect table {BURGLAR_TABLE}, assuming it exists")
        except NotFound:
            logger.info(f"Creating table {BURGLAR_TABLE}")
            table = bigquery.Table(ref, schema=SCHEMA)
            table.time_partitioning = bigquery.TimePartitioning(
                type_=bigquery.TimePartitioningType.DAY,
                field="detection_timestamp",
            )
            self.bq.create_table(table)
            logger.info(f"Created table {BURGLAR_TABLE}")

    def extract_detections(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract burglar alarm records from a UniFi Protect alarm payload."""
        alarm = payload.get("alarm", {})
        triggers = alarm.get("triggers", [])
        thumbnail_data_url = alarm.get("thumbnail")
        webhook_timestamp_ms = payload.get("timestamp")

        all_keys = [t.get("key", "") for t in triggers]
        logger.info(f"Burglar webhook trigger keys: {all_keys}")

        detections = []
        for trigger in triggers:
            key = trigger.get("key", "")
            if key not in BURGLAR_DETECTION_TYPES:
                logger.info(f"Skipping trigger key: {key!r}")
                continue

            ts_ms = trigger.get("timestamp") or webhook_timestamp_ms
            detection_timestamp = (
                datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()
                if ts_ms else datetime.now(tz=timezone.utc).isoformat()
            )

            device_id = trigger.get("device", "")
            camera_name = ""
            camera_location = ""
            lat = None
            lng = None
            if self.camera_lookup and device_id:
                camera_name = self.camera_lookup.camera_name(device_id)
                camera_location = self.camera_lookup.camera_location(device_id)
                lat = self.camera_lookup.camera_lat(device_id)
                lng = self.camera_lookup.camera_lng(device_id)

            detections.append({
                "event_id":            trigger.get("eventId", ""),
                "detection_type":      key,
                "device_id":           device_id,
                "camera_name":         camera_name,
                "camera_location":     camera_location,
                "lat":                 lat,
                "lng":                 lng,
                "detection_timestamp": detection_timestamp,
                "thumbnail_data_url":  thumbnail_data_url,
            })

        return detections

    def process(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process a burglar alarm webhook payload."""
        detections = self.extract_detections(payload)

        if not detections:
            logger.info("No burglar alarm triggers found in payload")
            return {"processed": 0, "skipped": 1}

        processed = 0
        errors = []

        for detection in detections:
            try:
                record_id = str(uuid.uuid4())
                now = datetime.now(tz=timezone.utc).isoformat()

                # Upload thumbnail to GCS
                thumbnail_url = None
                if self.gcs_client and detection.get("thumbnail_data_url"):
                    try:
                        data_url = detection["thumbnail_data_url"]
                        if "," in data_url:
                            data_url = data_url.split(",", 1)[1]
                        image_bytes = base64.b64decode(data_url)
                        result = self.gcs_client.upload_thumbnail(
                            image_bytes,
                            plate_number="burglar_alarm",
                            detection_timestamp=detection["detection_timestamp"],
                            event_id=detection["event_id"] or "",
                            image_type="alarm_thumbnail",
                        )
                        if result.get("success"):
                            thumbnail_url = result.get("public_url")
                    except Exception as e:
                        logger.warning(f"Thumbnail upload failed: {e}")

                row = {
                    "record_id":           record_id,
                    "detection_timestamp": detection["detection_timestamp"],
                    "event_id":            detection["event_id"] or None,
                    "detection_type":      detection["detection_type"],
                    "device_id":           detection["device_id"] or None,
                    "camera_name":         detection["camera_name"] or None,
                    "camera_location":     detection["camera_location"] or None,
                    "thumbnail_url":       thumbnail_url,
                    "created_at":          now,
                }

                bq_errors = self.bq.insert_rows_json(self._table_ref(), [row])
                if bq_errors:
                    raise RuntimeError(f"BigQuery insert errors: {bq_errors}")

                logger.info(
                    f"Stored burglar alarm: camera={detection['camera_name']} record_id={record_id}"
                )

                # Always send Telegram alert for burglar alarms
                if self.telegram_client:
                    self._send_alert(detection, thumbnail_url)

                processed += 1

            except Exception as e:
                logger.error(f"Error processing burglar alarm: {e}", exc_info=True)
                errors.append(str(e))

        return {"processed": processed, "errors": errors}

    def _send_alert(self, detection: Dict[str, Any], thumbnail_url: Optional[str]):
        ts = detection["detection_timestamp"]
        camera = detection["camera_name"] or detection["device_id"] or "unknown"
        location = detection["camera_location"] or ""

        lines = ["🚨 <b>BURGLAR ALARM</b>", ""]
        if camera:
            lines.append(f"Camera: {camera}")
        if location:
            lines.append(f"Location: {location}")
        lines.append(f"Time: {ts}")

        caption = "\n".join(lines)

        # Send thumbnail photo if available, otherwise send text
        if thumbnail_url:
            self.telegram_client.send_photo(thumbnail_url, caption=caption)
        else:
            self.telegram_client.send_message(caption)

        # Follow up with a map pinning the camera location
        if self.mapbox_token and detection.get("lat") and detection.get("lng"):
            map_url = self.telegram_client.build_static_map_url(
                [{"lat": detection["lat"], "lng": detection["lng"],
                  "camera_name": camera}],
                self.mapbox_token,
            )
            if map_url:
                self.telegram_client.send_photo(
                    map_url,
                    caption=f"📍 {location or camera}",
                )
