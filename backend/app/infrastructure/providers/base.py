from __future__ import annotations

import time
from collections import deque
from threading import Lock


class RateLimiter:
    """Token-bucket simple para respetar 10 req/min de los planes gratuitos."""

    def __init__(self, max_per_minute: int = 8):
        self.max_per_minute = max_per_minute
        self._hits: deque[float] = deque()
        self._lock = Lock()

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            while self._hits and now - self._hits[0] > 60:
                self._hits.popleft()
            if len(self._hits) >= self.max_per_minute:
                sleep_for = 60 - (now - self._hits[0]) + 0.05
                time.sleep(max(0.0, sleep_for))
            self._hits.append(time.monotonic())
