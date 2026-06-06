import pytest
from unittest.mock import AsyncMock, patch
from app.utils.rate_limiter import RedisRateLimiter

@pytest.mark.asyncio
async def test_rate_limiter_wait_success():
    limiter = RedisRateLimiter("test", limit=5)
    mock_redis = AsyncMock()
    mock_redis.incr.return_value = 1
    
    with patch("app.utils.rate_limiter.get_redis", return_value=mock_redis):
        await limiter.wait()
        assert mock_redis.incr.called
        assert mock_redis.expire.called

@pytest.mark.asyncio
async def test_rate_limiter_overflow():
    limiter = RedisRateLimiter("test", limit=1, window=10)
    mock_redis = AsyncMock()
    # First call within limit, second call over limit
    mock_redis.incr.side_effect = [2] 
    
    with patch("app.utils.rate_limiter.get_redis", return_value=mock_redis):
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            # We need to make it return a success eventually or it will loop forever
            mock_redis.incr.side_effect = [2, 1] 
            await limiter.wait()
            assert mock_sleep.called
            assert mock_redis.incr.call_count == 2

@pytest.mark.asyncio
async def test_rate_limiter_redis_error():
    limiter = RedisRateLimiter("test", limit=5)
    mock_redis = AsyncMock()
    mock_redis.incr.side_effect = Exception("Redis down")
    
    with patch("app.utils.rate_limiter.get_redis", return_value=mock_redis):
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await limiter.wait()
            assert mock_sleep.called
            # Should fail open after one error
            assert mock_redis.incr.call_count == 1
