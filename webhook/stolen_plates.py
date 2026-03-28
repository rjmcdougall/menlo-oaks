"""
Stolen plate registry backed by BigQuery with an in-memory cache.

The cache is populated on first use and refreshed every CACHE_TTL seconds.
When a plate is added via the webhook it is immediately written to the cache
so subsequent checks on the same instance reflect the new plate without
waiting for the next refresh cycle.
"""

import logging
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional

from google.cloud import bigquery
from google.cloud.exceptions import Forbidden, NotFound

logger = logging.getLogger(__name__)

STOLEN_TABLE = "stolenplates"
CACHE_TTL = timedelta(minutes=15)

SCHEMA = [
    bigquery.SchemaField("plate_number", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("inserted_at", "TIMESTAMP", mode="REQUIRED"),
]


class StolenPlatesChecker:
    """
    Manages the stolenplates BigQuery table and an in-memory plate cache.

    Thread-safe: a lock guards cache reads/writes so concurrent Cloud Function
    invocations sharing the same instance don't race during a refresh.
    """

    def __init__(self, project_id: str, dataset_id: str):
        self.project_id = project_id
        self.dataset_id = dataset_id
        self.bq = bigquery.Client(project=project_id)
        self._plates: set = set()
        self._last_loaded: Optional[datetime] = None
        self._lock = threading.Lock()
        self._ensure_table_exists()
        self._refresh()

    # ------------------------------------------------------------------
    # BigQuery setup
    # ------------------------------------------------------------------

    def _table_ref(self):
        return self.bq.dataset(self.dataset_id).table(STOLEN_TABLE)

    def _full_table_id(self) -> str:
        return f"{self.project_id}.{self.dataset_id}.{STOLEN_TABLE}"

    def _ensure_table_exists(self):
        ref = self._table_ref()
        try:
            self.bq.get_table(ref)
            logger.info(f"Table {STOLEN_TABLE} exists")
        except Forbidden:
            logger.info(f"No permission to inspect {STOLEN_TABLE}, assuming it exists")
        except NotFound:
            table = bigquery.Table(ref, schema=SCHEMA)
            self.bq.create_table(table)
            logger.info(f"Created table {STOLEN_TABLE}")

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def _refresh(self):
        """Load all stolen plate numbers from BigQuery into the in-memory set."""
        try:
            rows = self.bq.query(
                f"SELECT plate_number FROM `{self._full_table_id()}`"
            ).result()
            with self._lock:
                self._plates = {row.plate_number.upper().strip() for row in rows}
                self._last_loaded = datetime.now(tz=timezone.utc)
            logger.info(f"Loaded {len(self._plates)} stolen plates into cache")
        except Exception as e:
            logger.error(f"Failed to refresh stolen plates cache: {e}")

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

    def is_stolen(self, plate_number: str) -> bool:
        """Return True if the plate is in the stolen registry."""
        self._refresh_if_stale()
        with self._lock:
            return plate_number.upper().strip() in self._plates

    def add_plate(self, plate_number: str) -> bool:
        """
        Insert a plate into BigQuery and the in-memory cache.

        Returns True if inserted, False if the plate was already present.
        """
        normalized = plate_number.upper().strip()

        with self._lock:
            if normalized in self._plates:
                logger.info(f"Plate {normalized} already in stolen registry")
                return False

        now = datetime.now(tz=timezone.utc).isoformat()
        errors = self.bq.insert_rows_json(
            self._table_ref(),
            [{"plate_number": normalized, "inserted_at": now}],
        )
        if errors:
            raise RuntimeError(f"BigQuery insert errors: {errors}")

        with self._lock:
            self._plates.add(normalized)

        logger.info(f"Added {normalized} to stolen plates registry")
        return True

    def list_plates(self) -> list:
        """Return all stolen plates as a list of dicts (plate_number, inserted_at)."""
        try:
            rows = self.bq.query(
                f"SELECT plate_number, inserted_at FROM `{self._full_table_id()}` ORDER BY inserted_at DESC"
            ).result()
            return [{"plate_number": row.plate_number, "inserted_at": str(row.inserted_at)} for row in rows]
        except Exception as e:
            logger.error(f"Failed to list stolen plates: {e}")
            return []

    def remove_plate(self, plate_number: str) -> bool:
        """Remove a plate from the registry. Returns True if it existed."""
        normalized = plate_number.upper().strip()
        try:
            self.bq.query(
                f"DELETE FROM `{self._full_table_id()}` WHERE plate_number = '{normalized}'"
            ).result()
            with self._lock:
                existed = normalized in self._plates
                self._plates.discard(normalized)
            logger.info(f"Removed {normalized} from stolen plates registry")
            return existed
        except Exception as e:
            logger.error(f"Failed to remove plate {normalized}: {e}")
            return False
