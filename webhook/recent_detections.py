"""
In-memory rolling-window detection counter.

Tracks how many times each plate has been seen within a trailing time window.
Used to suppress unknown-plate Telegram alerts for plates that appear only
briefly — only plates seen more than a threshold number of times within the
window are considered worth alerting on.
"""

import threading
from collections import defaultdict, deque
from datetime import datetime, timezone, timedelta
from typing import List, Optional


class RecentDetectionTracker:
    """
    Thread-safe per-plate detection counter over a rolling time window.

    On each call to record() the current timestamp is appended to that plate's
    deque.  Stale entries (older than window_minutes) are pruned lazily on
    every record() or count() call so memory stays bounded.
    """

    def __init__(self, window_minutes: int = 10, threshold: int = 10):
        self.window = timedelta(minutes=window_minutes)
        self.threshold = threshold
        self._detections: dict = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, plate: str, now: datetime):
        """Remove entries outside the rolling window (must hold lock)."""
        cutoff = now - self.window
        dq = self._detections[plate]
        while dq and dq[0]["ts"] < cutoff:
            dq.popleft()

    def record(
        self,
        plate_number: str,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        camera_name: Optional[str] = None,
    ) -> int:
        """
        Record a detection for plate_number.
        Returns the current count within the window after recording.
        """
        now = datetime.now(tz=timezone.utc)
        plate = plate_number.upper().strip()
        with self._lock:
            self._detections[plate].append(
                {"ts": now, "lat": lat, "lng": lng, "camera_name": camera_name}
            )
            self._prune(plate, now)
            return len(self._detections[plate])

    def count(self, plate_number: str) -> int:
        """Return how many times plate_number has been seen within the window."""
        now = datetime.now(tz=timezone.utc)
        plate = plate_number.upper().strip()
        with self._lock:
            self._prune(plate, now)
            return len(self._detections[plate])

    def exceeds_threshold(self, plate_number: str) -> bool:
        """Return True if the plate has been seen more than threshold times in the window."""
        return self.count(plate_number) > self.threshold

    def get_locations(self, plate_number: str) -> List[dict]:
        """
        Return unique camera locations seen for this plate within the current window.
        Each entry is a dict with keys: lat, lng, camera_name.
        Locations without valid coordinates are excluded.
        """
        now = datetime.now(tz=timezone.utc)
        plate = plate_number.upper().strip()
        with self._lock:
            self._prune(plate, now)
            seen: dict = {}
            for entry in self._detections[plate]:
                if entry["lat"] is not None and entry["lng"] is not None:
                    key = (entry["lat"], entry["lng"])
                    if key not in seen:
                        seen[key] = entry["camera_name"]
        return [
            {"lat": lat, "lng": lng, "camera_name": name}
            for (lat, lng), name in seen.items()
        ]
