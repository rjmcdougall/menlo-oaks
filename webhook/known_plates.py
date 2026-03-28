"""
Known plate registry backed by BigQuery with an in-memory cache.

A plate is "known" if it has been seen on at least MIN_DAYS separate calendar
days.  The inverse — a plate NOT in the known set — is considered "unknown"
and triggers a Telegram alert.

The cache is rebuilt from BigQuery on first use and then every CACHE_TTL.
Because the known set grows slowly (a plate needs 20 distinct days before it
graduates), a 1-hour TTL is a reasonable balance between freshness and cost.
"""

import logging
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional

from google.cloud import bigquery

logger = logging.getLogger(__name__)

CACHE_TTL = timedelta(hours=1)
DEFAULT_MIN_DAYS = 20


class KnownPlatesChecker:
    """
    Maintains an in-memory set of "known" plates — those seen on at least
    min_days separate calendar days — built from the detections BigQuery table.

    Thread-safe: a lock guards cache reads/writes.
    """

    def __init__(self, project_id: str, dataset_id: str, min_days: int = DEFAULT_MIN_DAYS):
        self.project_id = project_id
        self.dataset_id = dataset_id
        self.min_days = min_days
        self.bq = bigquery.Client(project=project_id)
        self._known: set = set()
        self._last_loaded: Optional[datetime] = None
        self._lock = threading.Lock()
        self._refresh()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _detections_table(self) -> str:
        return f"`{self.project_id}.{self.dataset_id}.detections`"

    def _refresh(self):
        """Reload the known-plate set from BigQuery."""
        try:
            query = f"""
                SELECT plate_number
                FROM {self._detections_table()}
                GROUP BY plate_number
                HAVING COUNT(DISTINCT DATE(detection_timestamp)) >= {self.min_days}
            """
            rows = self.bq.query(query).result()
            with self._lock:
                self._known = {row.plate_number.upper().strip() for row in rows}
                self._last_loaded = datetime.now(tz=timezone.utc)
            logger.info(f"Loaded {len(self._known)} known plates into cache (min_days={self.min_days})")
        except Exception as e:
            logger.error(f"Failed to refresh known plates cache: {e}")

    def _refresh_if_stale(self):
        with self._lock:
            stale = (
                self._last_loaded is None
                or datetime.now(tz=timezone.utc) - self._last_loaded > CACHE_TTL
            )
        if stale:
            self._refresh()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def is_known(self, plate_number: str) -> bool:
        """Return True if the plate has been seen on >= min_days separate days."""
        self._refresh_if_stale()
        with self._lock:
            return plate_number.upper().strip() in self._known

    def is_unknown(self, plate_number: str) -> bool:
        """Return True if the plate has NOT yet been seen on >= min_days separate days."""
        return not self.is_known(plate_number)

    @property
    def known_count(self) -> int:
        with self._lock:
            return len(self._known)
