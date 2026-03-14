import pytest
import json
import asyncio
from unittest.mock import MagicMock, AsyncMock
from fakeredis.aioredis import FakeRedis
from app.services.cache_service import CacheService

# Force asyncio mode for all tests in this file
pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_settings(monkeypatch):
    class MockSettings:
        redis_cache_enabled = True
        redis_cache_key_prefix = "test:"
        redis_cache_default_ttl = 60
        cache_ttl_rag_query = 3600
        cache_max_keys_per_pattern = 1000

    m = MockSettings()
    monkeypatch.setattr("app.services.cache_service.settings", m)
    return m

@pytest.fixture
async def service(mock_settings, monkeypatch):

    redis = FakeRedis(decode_responses=True)
    # Mock info command since fakeredis implementation might be limited or different
    redis.info = AsyncMock(return_value={
        "used_memory": 1024,
        "maxmemory": 2048,
        "used_memory_human": "1K",
        "keyspace_hits": 10,
        "keyspace_misses": 5,
        "db0": {"keys": 1}
    })
    
    async def mock_eval(script, numkeys, key, *args):
        # script 1: _allow_call
        if "state == 'open'" in script:
            state = await redis.hget(key, "state")
            if state == "open":
                return 0
            return 1
        # script 2: _on_failure
        if "failures >= threshold" in script:
            await redis.hset(key, "state", "open")
            return None
        # script 3: _on_success
        if "state', 'closed'" in script:
            await redis.hset(key, "state", "closed")
            return None
        return None

    redis.eval = AsyncMock(side_effect=mock_eval)
    
    monkeypatch.setattr("app.utils.circuit_breaker.get_redis", lambda: redis)
    monkeypatch.setattr("app.services.cache_service.get_redis", lambda: redis)
    
    # Create fresh service
    s = CacheService()
    # Reset circuit breaker
    await s._circuit_breaker.reset()

    
    yield s, redis
    await redis.aclose()


async def test_get_set(service):
    s, redis = service
    key = "foo"
    value = {"a": 1}
    
    # Test Set
    success = await s.set(key, value)
    assert success is True
    
    # Verify in redis
    stored = await redis.get("test:foo")
    assert stored is not None
    assert json.loads(stored) == value
    
    # Test Get
    retrieved = await s.get(key)
    assert retrieved == value

async def test_get_miss(service):
    s, redis = service
    assert await s.get("nonexistent") is None

async def test_delete(service):
    s, redis = service
    await s.set("bar", "baz")
    assert await redis.get("test:bar") is not None
    
    await s.delete("bar")
    assert await redis.get("test:bar") is None

async def test_delete_pattern(service):
    s, redis = service
    await s.set("user:1", "a")
    await s.set("user:2", "b")
    await s.set("other:1", "c")
    
    count = await s.delete_pattern("user:*")
    assert count == 2
    assert await s.get("user:1") is None
    assert await s.get("user:2") is None
    assert await s.get("other:1") == "c"

async def test_circuit_breaker_degradation(service, monkeypatch):
    s, _ = service
    # Mock redis to raise error
    bad_redis = AsyncMock()
    bad_redis.get = AsyncMock(side_effect=Exception("Redis Down"))
    monkeypatch.setattr("app.services.cache_service.get_redis", lambda: bad_redis)
    
    # Trip the breaker
    for _ in range(6):
        await s.get("any")
        
    assert await s._circuit_breaker.is_open() is True
    
    # Fix it but breaker remains open
    bad_redis.get = AsyncMock(return_value=b'{"ok": true}')
    assert await s.get("any") is None

async def test_get_stats(service):
    s, redis = service
    await s.set("stat_test", 1)
    stats = await s.get_stats()
    
    assert stats["enabled"] is True
    assert "used_memory_percent" in stats
