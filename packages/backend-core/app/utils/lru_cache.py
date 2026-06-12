from __future__ import annotations
import time
from collections import OrderedDict
from threading import Lock
from typing import Any, Optional


class LocalLRUCache:
    """Thread-safe, process-local in-memory LRU cache with optional per-entry TTL."""

    def __init__(self, maxsize: int = 1000, ttl: Optional[float] = None):
        self.maxsize = maxsize
        self.ttl = ttl
        self.cache: OrderedDict[Any, Any] = OrderedDict()
        self.timestamps: OrderedDict[Any, float] = OrderedDict()
        self.lock = Lock()

    def get(self, key: Any) -> Optional[Any]:
        """Retrieve an item from the cache. Returns None if expired or missing."""
        with self.lock:
            if key not in self.cache:
                return None
            if (
                self.ttl is not None
                and time.monotonic() - self.timestamps[key] > self.ttl
            ):
                del self.cache[key]
                del self.timestamps[key]
                return None
            self.cache.move_to_end(key)
            self.timestamps.move_to_end(key)
            return self.cache[key]

    def set(self, key: Any, value: Any) -> None:
        """Store an item in the cache. Evicts least recently used items if maxsize is exceeded."""
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                self.timestamps.move_to_end(key)
            self.cache[key] = value
            self.timestamps[key] = time.monotonic()
            if len(self.cache) > self.maxsize:
                self.cache.popitem(last=False)
                self.timestamps.popitem(last=False)

    def delete(self, key: Any) -> bool:
        """Remove a specific key from the cache. Returns True if key existed."""
        with self.lock:
            if key in self.cache:
                del self.cache[key]
                del self.timestamps[key]
                return True
            return False

    def clear(self) -> None:
        """Clear all entries from the cache."""
        with self.lock:
            self.cache.clear()
            self.timestamps.clear()
