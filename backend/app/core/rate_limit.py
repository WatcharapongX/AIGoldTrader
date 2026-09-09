"""Bounded single-process sliding windows; Redis remains optional."""

import time
from collections import OrderedDict, deque
from collections.abc import Callable
from threading import Lock

from app.core.errors import RateLimitedError


class RateLimiter:
    def __init__(
        self, per_minute: int, *, max_keys: int = 10000, clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if per_minute < 1 or max_keys < 1:
            raise ValueError("Rate limiter bounds must be positive")
        self.per_minute = per_minute
        self.max_keys = max_keys
        self._clock = clock
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = Lock()

    def _cleanup(self, now: float) -> None:
        # Ordered by last accepted hit; expired identities cannot accumulate.
        while self._hits:
            key = next(iter(self._hits))
            if self._hits[key][-1] > now - 60:
                break
            self._hits.popitem(last=False)

    def cleanup(self) -> None:
        with self._lock:
            self._cleanup(self._clock())

    def check(self, *keys: str) -> None:
        """Atomically enforce every budget; never evict active protection at capacity."""
        with self._lock:
            now = self._clock()
            self._cleanup(now)
            unique_keys = tuple(dict.fromkeys(keys))
            if len(self._hits) + sum(key not in self._hits for key in unique_keys) > self.max_keys:
                raise RateLimitedError("Too many requests, try again later")
            for key in unique_keys:
                window = self._hits.get(key)
                if window is not None:
                    while window and window[0] <= now - 60:
                        window.popleft()
                    if len(window) >= self.per_minute:
                        raise RateLimitedError("Too many requests, try again later")
            for key in unique_keys:
                window = self._hits.setdefault(key, deque())
                window.append(now)
                self._hits.move_to_end(key)

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)
