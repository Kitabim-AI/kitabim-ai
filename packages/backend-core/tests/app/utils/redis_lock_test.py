import pytest
from unittest.mock import AsyncMock
from app.utils.redis_lock import RedisLock, MultiPageLock


@pytest.mark.asyncio
async def test_redis_lock_prefix_default_and_custom():
    redis_mock = AsyncMock()
    redis_mock.set.return_value = True

    # Default prefix "page"
    lock_default = RedisLock(redis_mock, "123")
    assert lock_default.name == "lock:page:123"

    acquired = await lock_default.acquire()
    assert acquired is True
    redis_mock.set.assert_called_once_with(
        "lock:page:123", lock_default.token, px=3600000, nx=True
    )

    # Custom prefix "ocr"
    redis_mock.reset_mock()
    lock_ocr = RedisLock(redis_mock, "123", prefix="ocr")
    assert lock_ocr.name == "lock:ocr:123"

    acquired = await lock_ocr.acquire()
    assert acquired is True
    redis_mock.set.assert_called_once_with(
        "lock:ocr:123", lock_ocr.token, px=3600000, nx=True
    )


@pytest.mark.asyncio
async def test_multi_page_lock_prefix_isolation():
    redis_mock = AsyncMock()
    # Simulate redis set returning True for any call
    redis_mock.set.return_value = True

    ocr_lock = MultiPageLock(redis_mock, [101, 102], prefix="ocr")
    chunking_lock = MultiPageLock(redis_mock, [101, 102], prefix="chunking")

    acquired_ocr = await ocr_lock.__aenter__()
    assert acquired_ocr == [101, 102]
    assert ocr_lock.locks[101].name == "lock:ocr:101"
    assert ocr_lock.locks[102].name == "lock:ocr:102"

    acquired_chunking = await chunking_lock.__aenter__()
    assert acquired_chunking == [101, 102]
    assert chunking_lock.locks[101].name == "lock:chunking:101"
    assert chunking_lock.locks[102].name == "lock:chunking:102"

    await ocr_lock.__aexit__(None, None, None)
    await chunking_lock.__aexit__(None, None, None)
