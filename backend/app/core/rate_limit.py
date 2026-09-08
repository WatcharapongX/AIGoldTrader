"""Rate limiting พื้นฐานแบบ in-memory sliding window (PHASE 1 baseline).

PHASE 12 จะย้ายไป Redis-based เพื่อรองรับหลาย instance.
"""

import time
from collections import defaultdict, deque

from app.core.errors import RateLimitedError


class RateLimiter:
    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        """raise RateLimitedError เมื่อเกินโควตาภายใน 60 วินาทีล่าสุด."""
        now = time.monotonic()
        window = self._hits[key]
        while window and now - window[0] > 60.0:
            window.popleft()
        if len(window) >= self.per_minute:
            raise RateLimitedError("Too many requests, try again later")
        window.append(now)

    def reset(self, key: str | None = None) -> None:
        if key is None:
            self._hits.clear()
        else:
            self._hits.pop(key, None)
