from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")


class CircuitBreakerOpen(Exception):
    pass


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 1
    cooling_period: float = 0.0  # Grace period after initialization (seconds)


class CircuitBreaker:
    def __init__(self, name: str, config: CircuitBreakerConfig | None = None) -> None:
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = "closed"
        self._failure_count = 0
        self._opened_at = 0.0
        self._half_open_in_flight = 0
        self._lock = asyncio.Lock()
        self._initialized_at = time.monotonic()  # Track when circuit breaker was created

    @property
    def is_open(self) -> bool:
        return self._state == "open"

    def _in_cooling_period(self) -> bool:
        """Check if we're still in the cooling/grace period after initialization."""
        if self.config.cooling_period <= 0:
            return False
        elapsed = time.monotonic() - self._initialized_at
        return elapsed < self.config.cooling_period

    async def _allow_call(self) -> bool:
        now = time.monotonic()
        async with self._lock:
            if self._state == "open":
                if now - self._opened_at >= self.config.recovery_timeout:
                    self._state = "half_open"
                    self._half_open_in_flight = 0
                else:
                    return False

            if self._state == "half_open":
                if self._half_open_in_flight >= self.config.half_open_max_calls:
                    return False
                self._half_open_in_flight += 1

            return True

    async def _on_success(self) -> None:
        async with self._lock:
            self._failure_count = 0
            if self._state in ("open", "half_open"):
                self._state = "closed"
            self._half_open_in_flight = 0

    async def _on_failure(self) -> None:
        async with self._lock:
            # Skip failure tracking during cooling period
            if self._in_cooling_period():
                return

            self._failure_count += 1
            if self._state == "half_open" or self._failure_count >= self.config.failure_threshold:
                self._state = "open"
                self._opened_at = time.monotonic()
                self._half_open_in_flight = 0

    async def call(self, fn: Callable[..., Awaitable[T]], *args, **kwargs) -> T:
        allowed = await self._allow_call()
        if not allowed:
            raise CircuitBreakerOpen(f"Circuit breaker '{self.name}' is open")

        try:
            result = await fn(*args, **kwargs)
        except Exception:
            await self._on_failure()
            raise
        await self._on_success()
        return result
