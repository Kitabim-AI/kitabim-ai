from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Awaitable, Callable, TypeVar

import redis.asyncio as redis
from app.core.config import settings

T = TypeVar("T")

class CircuitBreakerOpen(Exception):
    pass

@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 1
    cooling_period: float = 0.0

_redis_client = None

def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client

class CircuitBreaker:
    def __init__(self, name: str, config: CircuitBreakerConfig | None = None) -> None:
        self.name = name
        self.config = config or CircuitBreakerConfig()

    @property
    def key(self) -> str:
        return f"cb:{self.name}"

    async def _get_state(self) -> dict:
        r = get_redis()
        res = await r.hgetall(self.key)
        if not res:
            now = str(time.time())
            await r.hsetnx(self.key, "initialized_at", now)
            await r.hsetnx(self.key, "state", "closed")
            await r.hsetnx(self.key, "failures", "0")
            await r.hsetnx(self.key, "in_flight", "0")
            await r.hsetnx(self.key, "opened_at", "0")
            res = await r.hgetall(self.key)
        return res

    async def is_open(self) -> bool:
        state = await self._get_state()
        return state.get("state") == "open"

    async def is_half_open(self) -> bool:
        state = await self._get_state()
        return state.get("state") == "half_open"

    async def get_info(self) -> dict:
        state = await self._get_state()
        now = time.time()
        st = state.get("state", "closed")
        opened_at = float(state.get("opened_at", "0"))
        time_since = int(now - opened_at) if st == "open" and opened_at > 0 else 0
        return {
            "state": st,
            "failure_count": int(state.get("failures", "0")),
            "time_since_opened_seconds": time_since,
            "recovery_timeout": self.config.recovery_timeout,
            "failure_threshold": self.config.failure_threshold,
        }

    async def reset(self) -> None:
        r = get_redis()
        await r.hset(self.key, mapping={"state": "closed", "failures": "0", "in_flight": "0", "opened_at": "0"})

    async def force_open(self) -> None:
        r = get_redis()
        now = str(time.time())
        await r.hset(self.key, mapping={"state": "open", "in_flight": "0", "opened_at": now})

    async def _allow_call(self) -> bool:
        r = get_redis()
        now = time.time()
        
        script = """
        local key = KEYS[1]
        local now = tonumber(ARGV[1])
        local recovery_timeout = tonumber(ARGV[2])
        local half_open_max = tonumber(ARGV[3])
        
        local state = redis.call('HGET', key, 'state')
        if not state then
            redis.call('HSET', key, 'initialized_at', now, 'state', 'closed', 'failures', '0', 'in_flight', '0', 'opened_at', '0')
            state = 'closed'
        end
        
        if state == 'open' then
            local opened_at = tonumber(redis.call('HGET', key, 'opened_at') or '0')
            if now - opened_at >= recovery_timeout then
                redis.call('HSET', key, 'state', 'half_open', 'in_flight', '1')
                return {1, 'half_open'}
            else
                return {0, 'open'}
            end
        end
        
        if state == 'half_open' then
            local in_flight = tonumber(redis.call('HGET', key, 'in_flight') or '0')
            if in_flight >= half_open_max then
                return {0, 'half_open'}
            end
            redis.call('HINCRBY', key, 'in_flight', 1)
            state = 'half_open'
        end
        
        return {1, state}
        """
        result = await r.eval(script, 1, self.key, str(now), str(self.config.recovery_timeout), str(self.config.half_open_max_calls))
        # result is {1/0, state_string}
        return bool(result[0]), result[1]

    async def _on_success(self) -> None:
        r = get_redis()
        script = """
        local key = KEYS[1]
        redis.call('HSET', key, 'failures', '0', 'in_flight', '0', 'state', 'closed')
        """
        await r.eval(script, 1, self.key)

    async def _on_failure(self) -> None:
        r = get_redis()
        now = time.time()
        
        script = """
        local key = KEYS[1]
        local now = tonumber(ARGV[1])
        local threshold = tonumber(ARGV[2])
        local cooling_period = tonumber(ARGV[3])
        
        local state = redis.call('HGET', key, 'state')
        if not state then
            redis.call('HSET', key, 'initialized_at', now, 'state', 'closed', 'failures', '0', 'in_flight', '0', 'opened_at', '0')
            state = 'closed'
        end
        
        local init_at = tonumber(redis.call('HGET', key, 'initialized_at') or '0')
        if cooling_period > 0 and (now - init_at < cooling_period) then
            return
        end
        
        local failures = tonumber(redis.call('HINCRBY', key, 'failures', 1))
        
        if state == 'half_open' or failures >= threshold then
            redis.call('HSET', key, 'state', 'open', 'opened_at', now, 'in_flight', '0')
        end
        """
        await r.eval(script, 1, self.key, str(now), str(self.config.failure_threshold), str(self.config.cooling_period))

    async def call(self, fn: Callable[..., Awaitable[T]], *args, **kwargs) -> T:
        allowed, state = await self._allow_call()
        if not allowed:
            if state == "half_open":
                raise CircuitBreakerOpen(f"Circuit breaker '{self.name}' is half-open (recovering but at capacity)")
            raise CircuitBreakerOpen(f"Circuit breaker '{self.name}' is open")

        try:
            result = await fn(*args, **kwargs)
        except Exception:
            await self._on_failure()
            raise
        await self._on_success()
        return result
