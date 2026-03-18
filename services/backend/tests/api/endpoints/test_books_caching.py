import pytest
from unittest.mock import AsyncMock
import sys
from pathlib import Path
import importlib.util

BACKEND_DIR = Path(__file__).resolve().parents[3]
BACKEND_CORE_DIR = Path(__file__).resolve().parents[5] / "packages" / "backend-core"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(BACKEND_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_CORE_DIR))

BOOKS_PATH = BACKEND_DIR / "api" / "endpoints" / "books.py"
spec = importlib.util.spec_from_file_location("test_books_endpoint_module", BOOKS_PATH)
books_endpoint = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(books_endpoint)

@pytest.fixture
def mock_cache(monkeypatch):
    m = AsyncMock()
    m.get = AsyncMock(return_value=None)
    m.set = AsyncMock()
    
    # We need to mock settings as well
    class MockSettings:
        redis_cache_enabled = True
        redis_cache_key_prefix = "test:"
        cache_skip_for_admins = False
        cache_ttl_books = 600
    
    monkeypatch.setattr(books_endpoint, "settings", MockSettings())
    monkeypatch.setattr(books_endpoint, "cache_service", m)
    return m

@pytest.mark.asyncio
async def test_get_books_uses_cache(mock_cache):
    mock_cache.get.return_value = {
        "books": [],
        "total": 0,
        "totalReady": 0,
        "page": 1,
        "pageSize": 20,
    }

    result = await books_endpoint.get_books(
        page=1,
        pageSize=20,
        current_user=None,
        session=AsyncMock(),
    )

    assert result.total == 0
    assert result.page == 1
    mock_cache.get.assert_called_once()
