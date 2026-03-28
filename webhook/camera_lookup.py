"""
In-memory cache of the camera_lookup BigQuery table.

Maps device_id -> {camera_name, camera_location}.  The table is small and
changes rarely (only when cameras are added/renamed), so it is loaded once
at startup with no automatic refresh.
"""

import logging
from typing import Optional

from google.cloud import bigquery

logger = logging.getLogger(__name__)

CAMERA_LOOKUP_TABLE = "camera_lookup"


class CameraLookup:
    """Loads camera_lookup into memory and provides O(1) lookups by device_id."""

    def __init__(self, project_id: str, dataset_id: str):
        self.project_id = project_id
        self.dataset_id = dataset_id
        self.bq = bigquery.Client(project=project_id)
        self._cameras: dict = {}
        self._load()

    def _load(self):
        try:
            table = f"`{self.project_id}.{self.dataset_id}.{CAMERA_LOOKUP_TABLE}`"
            rows = self.bq.query(
                f"SELECT device_id, camera_name, camera_location FROM {table}"
            ).result()
            self._cameras = {
                row.device_id: {
                    "camera_name": row.camera_name or "",
                    "camera_location": row.camera_location or "",
                }
                for row in rows
            }
            logger.info(f"Loaded {len(self._cameras)} cameras from camera_lookup")
        except Exception as e:
            logger.error(f"Failed to load camera_lookup: {e}")

    def get(self, device_id: str) -> Optional[dict]:
        """Return {camera_name, camera_location} for the given device_id, or None."""
        return self._cameras.get(device_id)

    def camera_name(self, device_id: str) -> str:
        entry = self._cameras.get(device_id)
        return entry["camera_name"] if entry else ""

    def camera_location(self, device_id: str) -> str:
        entry = self._cameras.get(device_id)
        return entry["camera_location"] if entry else ""
