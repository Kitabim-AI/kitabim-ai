from __future__ import annotations
import json
import logging
from typing import Any, Optional

from redis.asyncio import Redis
from pydantic import BaseModel
from app.core.config import settings
from app.utils.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, get_redis

logger = logging.getLogger("app.cache")

class CacheService:
    """Redis cache service with graceful degradation.
    
    Uses the existing Redis-backed CircuitBreaker so that failure state persists 
    across pod restarts and is shared across all workers.
    """

    def __init__(self):
        self._circuit_breaker = CircuitBreaker(
            name="cache",
            config=CircuitBreakerConfig(
                failure_threshold=5,
                recovery_timeout=30.0,
            )
        )

    @property
    def redis(self) -> Redis:
        """Lazy Redis client from the shared factory."""
        return get_redis()

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache with fallback."""
        if not settings.redis_cache_enabled:
            return None

        if await self._circuit_breaker.is_open():
            return None

        try:
            full_key = f"{settings.redis_cache_key_prefix}{key}"
            data = await self.redis.get(full_key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.warning(f"Cache get failed for {key}: {e}")
            await self._circuit_breaker._on_failure()
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> bool:
        """Set value in cache."""
        if not settings.redis_cache_enabled:
            return False

        if await self._circuit_breaker.is_open():
            return False

        try:
            full_key = f"{settings.redis_cache_key_prefix}{key}"
            ttl = ttl or settings.redis_cache_default_ttl

            # Convert Pydantic models to dicts before serialization
            if isinstance(value, BaseModel):
                serialized_value = value.model_dump()
            elif isinstance(value, dict):
                # Recursively convert nested Pydantic models
                serialized_value = self._serialize_value(value)
            else:
                serialized_value = value

            await self.redis.setex(
                full_key,
                ttl,
                json.dumps(serialized_value)
            )
            await self._circuit_breaker._on_success()
            return True
        except Exception as e:
            logger.warning(f"Cache set failed for {key}: {e}")
            await self._circuit_breaker._on_failure()
            return False

    def _serialize_value(self, value: Any) -> Any:
        """Recursively convert Pydantic models to dictionaries."""
        if isinstance(value, BaseModel):
            return value.model_dump()
        elif isinstance(value, dict):
            return {k: self._serialize_value(v) for k, v in value.items()}
        elif isinstance(value, (list, tuple)):
            return [self._serialize_value(item) for item in value]
        else:
            return value

    async def delete(self, key: str) -> bool:
        """Delete a single key from cache."""
        try:
            full_key = f"{settings.redis_cache_key_prefix}{key}"
            await self.redis.delete(full_key)
            return True
        except Exception as e:
            logger.warning(f"Cache delete failed for {key}: {e}")
            return False

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern using non-blocking SCAN."""
        full_pattern = f"{settings.redis_cache_key_prefix}{pattern}"
        deleted = 0
        cursor = 0
        try:
            while True:
                cursor, keys = await self.redis.scan(
                    cursor, match=full_pattern, count=100
                )
                if keys:
                    await self.redis.delete(*keys)
                    deleted += len(keys)
                if cursor == 0:
                    break
        except Exception as e:
            logger.warning(f"Cache delete_pattern failed for '{pattern}': {e}")
        return deleted

    async def get_stats(self) -> dict:
        """Return basic cache statistics."""
        try:
            info = await self.redis.info()
            used_mem = info.get("used_memory", 0)
            max_mem = info.get("maxmemory", 0)
            # Guard against maxmemory=0 (often the default in local/unconfigured redis)
            used_memory_percent = (used_mem / max_mem * 100) if max_mem > 0 else 0
            
            return {
                "enabled": settings.redis_cache_enabled,
                "circuit_breaker_state": (await self._circuit_breaker.get_info()).get("state"),
                "used_memory_human": info.get("used_memory_human", "0B"),
                "used_memory_percent": round(used_memory_percent, 2),
                "total_keys": info.get("db0", {}).get("keys", 0),
                "hits": info.get("keyspace_hits", 0),
                "misses": info.get("keyspace_misses", 0),
            }
        except Exception as e:
            return {"enabled": settings.redis_cache_enabled, "error": str(e)}

    async def get_client(self) -> Optional[Redis]:
        """Expose the raw redis client for advanced operations (e.g. Eval)."""
        if await self._circuit_breaker.is_open():
            return None
        return self.redis

# Singleton instance

cache_service = CacheService()
