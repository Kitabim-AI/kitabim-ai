import pytest
import json
from unittest.mock import AsyncMock, patch, PropertyMock
from pydantic import BaseModel
from app.services.cache_service import CacheService

class MockModel(BaseModel):
    id: int
    name: str

@pytest.fixture
def cache_service():
    return CacheService()

@pytest.mark.asyncio
async def test_cache_get_hit(cache_service):
    with patch("app.services.cache_service.settings") as mock_settings:
        mock_settings.redis_cache_enabled = True
        mock_settings.redis_cache_key_prefix = "pk:"
        
        mock_redis = AsyncMock()
        mock_redis.get.return_value = json.dumps({"a": 1})
        
        with patch.object(CacheService, "redis", new_callable=PropertyMock) as mock_redis_prop:
            mock_redis_prop.return_value = mock_redis
            cache_service._circuit_breaker.is_open = AsyncMock(return_value=False)
            val = await cache_service.get("test-key")
            assert val == {"a": 1}

@pytest.mark.asyncio
async def test_cache_get_miss(cache_service):
    with patch("app.services.cache_service.settings") as mock_settings:
        mock_settings.redis_cache_enabled = True
        mock_settings.redis_cache_key_prefix = "pk:"
        
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        
        with patch.object(CacheService, "redis", new_callable=PropertyMock) as mock_redis_prop:
            mock_redis_prop.return_value = mock_redis
            cache_service._circuit_breaker.is_open = AsyncMock(return_value=False)
            val = await cache_service.get("missing")
            assert val is None

@pytest.mark.asyncio
async def test_cache_set_pydantic(cache_service):
    with patch("app.services.cache_service.settings") as mock_settings:
        mock_settings.redis_cache_enabled = True
        mock_settings.redis_cache_key_prefix = "pk:"
        mock_settings.redis_cache_default_ttl = 3600
        
        mock_redis = AsyncMock()
        with patch.object(CacheService, "redis", new_callable=PropertyMock) as mock_redis_prop:
            mock_redis_prop.return_value = mock_redis
            cache_service._circuit_breaker.is_open = AsyncMock(return_value=False)
            cache_service._circuit_breaker._on_success = AsyncMock()
            model = MockModel(id=1, name="test")
            await cache_service.set("key", model)
            assert mock_redis.setex.called

@pytest.mark.asyncio
async def test_cache_delete(cache_service):
    with patch("app.services.cache_service.settings") as mock_settings:
        mock_settings.redis_cache_key_prefix = "pk:"
        mock_redis = AsyncMock()
        with patch.object(CacheService, "redis", new_callable=PropertyMock) as mock_redis_prop:
            mock_redis_prop.return_value = mock_redis
            await cache_service.delete("key")
            assert mock_redis.delete.called
