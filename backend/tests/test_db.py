import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.db.mongodb import MongoDB, get_db

@pytest.mark.asyncio
async def test_mongodb_connect_success():
    storage = MongoDB()
    with patch("motor.motor_asyncio.AsyncIOMotorClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.admin.command = AsyncMock(return_value={"ok": 1})
        mock_client_class.return_value = mock_client
        
        await storage.connect_to_storage()
        assert storage.client is not None
        assert storage.db is not None
        mock_client.admin.command.assert_called_with('ismaster')

@pytest.mark.asyncio
async def test_mongodb_connect_error():
    storage = MongoDB()
    with patch("motor.motor_asyncio.AsyncIOMotorClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.admin.command = AsyncMock(side_effect=Exception("Conn error"))
        mock_client_class.return_value = mock_client
        
        # Should not raise exception but print it
        await storage.connect_to_storage()
        assert storage.client is not None

@pytest.mark.asyncio
async def test_mongodb_close():
    storage = MongoDB()
    storage.client = MagicMock()
    await storage.close_storage()
    storage.client.close.assert_called_once()

@pytest.mark.asyncio
async def test_get_db(mock_db):
    from app.db.mongodb import db_manager
    # mock_db fixture already set db_manager.db
    db = await get_db()
    assert db == mock_db
