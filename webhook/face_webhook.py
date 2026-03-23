"""
Face detection webhook handler for UniFi Protect.
Processes face detection alarm payloads and stores records to BigQuery,
uploading thumbnails to Google Photos.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from google.cloud import bigquery
from google.cloud.exceptions import Forbidden, NotFound

logger = logging.getLogger(__name__)

FACE_DETECTION_TYPES = {"face_known", "face_unknown", "face_of_interest"}
FACE_TABLE = "facedetection"

SCHEMA = [
    bigquery.SchemaField("record_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("detection_timestamp", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("event_id", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("person_name", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("detection_type", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("device_id", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("thumbnail_url", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
]


class FaceDetectionHandler:
    """Handles face detection webhook events."""

    def __init__(self, project_id: str, dataset_id: str, photos_client=None):
        self.project_id = project_id
        self.dataset_id = dataset_id
        self.photos_client = photos_client
        self.bq = bigquery.Client(project=project_id)
        self._ensure_table_exists()

    # ------------------------------------------------------------------
    # BigQuery setup
    # ------------------------------------------------------------------

    def _table_ref(self):
        return self.bq.dataset(self.dataset_id).table(FACE_TABLE)

    def _ensure_table_exists(self):
        ref = self._table_ref()
        try:
            self.bq.get_table(ref)
            logger.info(f"Table {FACE_TABLE} exists")
        except Forbidden:
            logger.info(f"No permission to inspect table {FACE_TABLE}, assuming it exists")
        except NotFound:
            logger.info(f"Creating table {FACE_TABLE}")
            table = bigquery.Table(ref, schema=SCHEMA)
            table.time_partitioning = bigquery.TimePartitioning(
                type_=bigquery.TimePartitioningType.DAY,
                field="detection_timestamp",
            )
            self.bq.create_table(table)
            logger.info(f"Created table {FACE_TABLE}")

    # ------------------------------------------------------------------
    # Payload parsing
    # ------------------------------------------------------------------

    def extract_face_detections(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract face detection records from a UniFi Protect alarm payload."""
        alarm = payload.get("alarm", {})
        triggers = alarm.get("triggers", [])
        thumbnail_data_url = alarm.get("thumbnail")
        webhook_timestamp_ms = payload.get("timestamp")

        detections = []
        for trigger in triggers:
            key = trigger.get("key", "")
            if key not in FACE_DETECTION_TYPES:
                continue

            ts_ms = trigger.get("timestamp") or webhook_timestamp_ms
            if ts_ms:
                detection_timestamp = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()
            else:
                detection_timestamp = datetime.now(tz=timezone.utc).isoformat()

            detections.append({
                "event_id": trigger.get("eventId", ""),
                "person_name": trigger.get("value") or None,
                "detection_type": key,
                "device_id": trigger.get("device", ""),
                "detection_timestamp": detection_timestamp,
                "thumbnail_data_url": thumbnail_data_url,
            })

        return detections

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------

    def process(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a face detection webhook payload.

        Returns a summary dict with counts and any errors.
        """
        detections = self.extract_face_detections(payload)

        if not detections:
            logger.info("No face detection triggers found in payload")
            return {"processed": 0, "skipped": 1}

        processed = 0
        errors = []

        for detection in detections:
            try:
                record_id = str(uuid.uuid4())
                now = datetime.now(tz=timezone.utc).isoformat()

                # Upload thumbnail to Google Photos if available
                thumbnail_url = None
                if self.photos_client and detection.get("thumbnail_data_url"):
                    person = detection["person_name"] or "unknown"
                    date_str = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
                    filename = f"face_{person.replace(' ', '_')}_{date_str}.jpg"
                    description = f"{detection['detection_type']} – {person}"
                    thumbnail_url = self.photos_client.upload_base64_thumbnail(
                        detection["thumbnail_data_url"],
                        filename=filename,
                        description=description,
                    )

                row = {
                    "record_id": record_id,
                    "detection_timestamp": detection["detection_timestamp"],
                    "event_id": detection["event_id"] or None,
                    "person_name": detection["person_name"],
                    "detection_type": detection["detection_type"],
                    "device_id": detection["device_id"] or None,
                    "thumbnail_url": thumbnail_url,
                    "created_at": now,
                }

                errors_bq = self.bq.insert_rows_json(self._table_ref(), [row])
                if errors_bq:
                    raise RuntimeError(f"BigQuery insert errors: {errors_bq}")

                logger.info(
                    f"Stored face detection: {detection['detection_type']} "
                    f"person={detection['person_name']} record_id={record_id}"
                )
                processed += 1

            except Exception as e:
                logger.error(f"Error processing face detection: {e}", exc_info=True)
                errors.append(str(e))

        return {"processed": processed, "errors": errors}
