from __future__ import annotations

import asyncio
import logging
import time

from app.utils.circuit_breaker import get_redis

logger = logging.getLogger("app.rate_limiter")


class RedisRateLimiter:
    """
    Simple Redis-based rate limiter using a sliding window (fixed window blocks).
    Shared across all workers to ensure global project-level quotas aren't exceeded.
    """

    def __init__(self, name: str, limit: int, window: int = 60):
        self.name = name
        self.limit = limit
        self.window = window

    async def wait(self) -> None:
        """
        Wait until we are within the rate limit.
        Politely blocks the coroutine using asyncio.sleep.
        """
        r = get_redis()
        incremented_key = None
        while True:
            now = int(time.time())
            # Use fixed window slots (e.g. per minute)
            key = f"rate_limit:{self.name}:{now // self.window}"

            try:
                if incremented_key == key:
                    val_str = await r.get(key)
                    count = int(val_str) if val_str else 0
                else:
                    count = await r.incr(key)
                    if count == 1:
                        # First caller in this window sets expiry
                        await r.expire(key, self.window + 5)  # Buffer for clock skew
                    incremented_key = key

                if count <= self.limit:
                    # Within limit, proceed
                    return

                # Limit exceeded. Calculate time to next window
                sleep_time = self.window - (now % self.window) + 0.1
                # Don't sleep too long in one go to keep things responsive and allow for retries
                sleep_time = min(sleep_time, 2.0)

                if count == self.limit + 1:
                    # Only log once per window overflow
                    logger.warning(
                        f"Rate limit '{self.name}' exceeded ({self.limit}/{self.window}s). Throttling callers..."
                    )

                await asyncio.sleep(sleep_time)
            except Exception as e:
                # If Redis fails, we fall back to a small sleep to avoid tight-loop hammering
                logger.error(f"Rate limiter Redis error: {e}")
                await asyncio.sleep(1.0)
                return  # Fail open to avoid blocking everything if Redis is down
