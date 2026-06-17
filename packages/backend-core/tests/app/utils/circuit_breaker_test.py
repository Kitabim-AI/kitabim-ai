import pytest
import pytest_asyncio
import asyncio
import app.utils.circuit_breaker
from app.utils.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, get_redis
from app.utils.rate_limiter import RedisRateLimiter
from app.llm.models import is_transient_error


@pytest_asyncio.fixture(autouse=True)
async def reset_redis():
    if app.utils.circuit_breaker._redis_client is not None:
        try:
            await app.utils.circuit_breaker._redis_client.aclose()
        except Exception:
            pass
        app.utils.circuit_breaker._redis_client = None
    yield
    if app.utils.circuit_breaker._redis_client is not None:
        try:
            await app.utils.circuit_breaker._redis_client.aclose()
        except Exception:
            pass
        app.utils.circuit_breaker._redis_client = None


@pytest.mark.asyncio
async def test_circuit_breaker_transient_error_ignored():
    breaker = CircuitBreaker(
        "test_cb_transient",
        CircuitBreakerConfig(failure_threshold=2, recovery_timeout=5.0),
    )
    # Reset first to make sure it's clean
    await breaker.reset()

    # 1. Test transient rate limit error (429) is ignored
    async def raise_429():
        raise ValueError("API call failed with status code 429")

    with pytest.raises(ValueError, match="429"):
        await breaker.call(raise_429, ignore_on_failure=is_transient_error)

    info = await breaker.get_info()
    assert info["failure_count"] == 0
    assert info["state"] == "closed"

    # 2. Test transient timeout error is ignored
    async def raise_timeout():
        raise TimeoutError("LLM did not respond within 120.0s")

    with pytest.raises(TimeoutError, match="120"):
        await breaker.call(raise_timeout, ignore_on_failure=is_transient_error)

    info = await breaker.get_info()
    assert info["failure_count"] == 0
    assert info["state"] == "closed"

    # 3. Test non-transient error is NOT ignored
    async def raise_non_transient():
        raise ValueError("Generic API error")

    with pytest.raises(ValueError, match="Generic API error"):
        await breaker.call(raise_non_transient, ignore_on_failure=is_transient_error)

    info = await breaker.get_info()
    assert info["failure_count"] == 1
    assert info["state"] == "closed"

    # Trip the breaker with another non-transient failure
    with pytest.raises(ValueError, match="Generic API error"):
        await breaker.call(raise_non_transient, ignore_on_failure=is_transient_error)

    info = await breaker.get_info()
    assert info["failure_count"] == 2
    assert info["state"] == "open"

    await breaker.reset()


@pytest.mark.asyncio
async def test_redis_rate_limiter_no_inflation():
    limiter = RedisRateLimiter("test_limiter_inflation", limit=2, window=10)
    r = get_redis()

    # Generate the slot key matching the limiter logic
    import time

    now = int(time.time())
    key = f"rate_limit:test_limiter_inflation:{now // limiter.window}"

    # Delete key first for clean test
    await r.delete(key)

    # First and second calls should succeed immediately
    await limiter.wait()
    await limiter.wait()

    # Verify count is 2 in Redis
    val = await r.get(key)
    assert int(val) == 2

    # Third call will exceed the limit and sleep/loop
    # We run wait in a task, and cancel it after it sleep-blocks once
    task = asyncio.create_task(limiter.wait())

    # Give it a tiny bit of time to run and block
    await asyncio.sleep(0.1)

    # Count should be 3 in Redis (the 3rd caller registered, count=3, and is now waiting)
    val = await r.get(key)
    assert int(val) == 3

    # Wait a bit longer to simulate wake up and loop retry.
    # The limiter sleep interval is calculated, but since we patched/timed it,
    # wait() will sleep for self.window - (now % self.window) + 0.1, capped at 2.0s.
    # Let's wait 2.2 seconds to allow the task to wake up, retry, and sleep again
    await asyncio.sleep(2.2)

    # Verify count is STILL 3 and not inflated (e.g. not 4 or 5)
    val = await r.get(key)
    assert int(val) == 3

    # Cancel the task
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # Cleanup
    await r.delete(key)
