"""
Detection cooldown manager to avoid duplicate plate processing.
Keeps per-plate/per-camera timestamps and throttles rapid repeats.
"""
from __future__ import annotations

from threading import Lock
from typing import Dict, Tuple
import time


class DetectionCooldown:
    """In-memory cooldown tracker for plate detections."""

    def __init__(self, cooldown_seconds: float = 10.0):
        self.cooldown_seconds = cooldown_seconds
        self._last_seen: Dict[Tuple[str, str], float] = {}
        self._lock = Lock()

    def allow(self, plate: str, camera: str) -> bool:
        """Return True if detection should be processed now."""
        normalized_plate = plate.strip().upper()
        key = (normalized_plate, camera)
        now = time.monotonic()

        with self._lock:
            last_time = self._last_seen.get(key, 0.0)
            if now - last_time >= self.cooldown_seconds:
                self._last_seen[key] = now
                return True
            return False

    def touch(self, plate: str, camera: str) -> None:
        """Update detection timestamp without checking cooldown."""
        normalized_plate = plate.strip().upper()
        key = (normalized_plate, camera)
        with self._lock:
            self._last_seen[key] = time.monotonic()

    def set_cooldown(self, cooldown_seconds: float) -> None:
        """Adjust cooldown window dynamically."""
        with self._lock:
            self.cooldown_seconds = cooldown_seconds


# Singleton instance
_detection_cooldown: DetectionCooldown | None = None


def get_detection_cooldown(cooldown_seconds: float = 10.0) -> DetectionCooldown:
    """Get or create detection cooldown singleton."""
    global _detection_cooldown
    if _detection_cooldown is None:
        _detection_cooldown = DetectionCooldown(cooldown_seconds)
    else:
        _detection_cooldown.set_cooldown(cooldown_seconds)
    return _detection_cooldown
