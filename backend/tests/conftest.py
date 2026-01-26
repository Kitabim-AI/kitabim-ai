import pytest
import google.generativeai as genai
from unittest.mock import MagicMock, AsyncMock, patch
import motor.motor_asyncio
from httpx import AsyncClient
from app.main import app
from app.db.mongodb import db_manager

@pytest.fixture
def mock_db():
    # Mock the MongoDB collections with AsyncMock for methods
    m_db = MagicMock()
    m_db.books = MagicMock()
    
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor
    mock_cursor.to_list = AsyncMock(return_value=[])
    
    m_db.books.find.return_value = mock_cursor
    m_db.books.find_one = AsyncMock()
    m_db.books.insert_one = AsyncMock()
    m_db.books.update_one = AsyncMock()
    m_db.books.delete_one = AsyncMock()
    m_db.books.count_documents = AsyncMock()
    
    # Patch the global db_manager
    with patch("app.db.mongodb.db_manager.db", m_db), \
         patch("app.db.mongodb.db_manager.connect_to_storage", AsyncMock()), \
         patch("app.db.mongodb.db_manager.close_storage", AsyncMock()):
        yield m_db

@pytest.fixture
async def client(mock_db):
    async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as ac:
        yield ac

@pytest.fixture(autouse=True)
def mock_gemini():
    # Mock both the main module and the embed_content/GenerativeModel
    with patch("google.generativeai.embed_content") as mock_embed, \
         patch("google.generativeai.GenerativeModel") as mock_model:
        
        # Default behaviors
        mock_embed.return_value = {"embedding": [0.1] * 768}
        
        mock_instance = MagicMock()
        mock_chat = MagicMock()
        # send_message_async must be an AsyncMock itself to be awaited
        mock_chat.send_message_async = AsyncMock()
        mock_response = MagicMock()
        mock_response.text = "Mocked Response"
        mock_chat.send_message_async.return_value = mock_response
        mock_instance.start_chat.return_value = mock_chat
        mock_model.return_value = mock_instance
        
        yield {
            "embed": mock_embed,
            "model": mock_model,
            "instance": mock_instance,
            "chat": mock_chat,
            "response": mock_response
        }
