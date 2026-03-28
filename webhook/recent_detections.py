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
        self._timestamps: dict = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, plate: str, now: datetime):
        """Remove timestamps outside the rolling window (must hold lock)."""
        cutoff = now - self.window
        dq = self._timestamps[plate]
        while dq and dq[0] < cutoff:
            dq.popleft()

    def record(self, plate_number: str) -> int:
        """
        Record a detection for plate_number.
        Returns the current count within the window after recording.
        """
        now = datetime.now(tz=timezone.utc)
        plate = plate_number.upper().strip()
        with self._lock:
            self._timestamps[plate].append(now)
            self._prune(plate, now)
            return len(self._timestamps[plate])

    def count(self, plate_number: str) -> int:
        """Return how many times plate_number has been seen within the window."""
        now = datetime.now(tz=timezone.utc)
        plate = plate_number.upper().strip()
        with self._lock:
            self._prune(plate, now)
            return len(self._timestamps[plate])

    def exceeds_threshold(self, plate_number: str) -> bool:
        """Return True if the plate has been seen more than threshold times in the window."""
        return self.count(plate_number) > self.threshold
