import pytest
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
    m_db.books.distinct = AsyncMock(return_value=[])
    
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
    with patch("app.services.genai_client.get_genai_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.aio = MagicMock()
        mock_client.aio.models = MagicMock()

        mock_embed_result = MagicMock()
        mock_embedding = MagicMock()
        mock_embedding.values = [0.1] * 768
        mock_embed_result.embeddings = [mock_embedding]

        mock_response = MagicMock()
        mock_response.text = "Mocked Response"

        mock_client.aio.models.embed_content = AsyncMock(return_value=mock_embed_result)
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client

        yield {
            "client": mock_client,
            "embed_result": mock_embed_result,
            "response": mock_response,
            "get_client": mock_get_client,
        }
