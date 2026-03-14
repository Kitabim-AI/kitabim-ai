import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

# Verify import works
try:
    import api.endpoints.books
except ImportError:
    # If not in PYTHONPATH, try adding it
    import sys
    import os
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

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
    
    monkeypatch.setattr("api.endpoints.books.settings", MockSettings())
    monkeypatch.setattr("api.endpoints.books.cache_service", m)
    return m

def test_get_books_uses_cache(mock_cache, monkeypatch):
    monkeypatch.setattr("api.endpoints.books.get_current_user_optional", lambda: None)
    
    mock_cache.get.return_value = {
        "books": [], 
        "total": 0, 
        "totalReady": 0, 
        "page": 1, 
        "pageSize": 20
    }
    
    from services.backend.main import app
    client = TestClient(app)
    
    response = client.get("/api/books/")
    assert response.status_code == 200
    mock_cache.get.assert_called_once()
