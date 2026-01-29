import pytest
import numpy as np
from unittest.mock import patch, MagicMock, AsyncMock
from app.services.ai_service import cosine_similarity, get_embedding

def test_cosine_similarity():
    v1 = np.array([1, 0, 0])
    v2 = np.array([1, 0, 0])
    assert pytest.approx(cosine_similarity(v1, v2)) == 1.0
    
    v3 = np.array([0, 1, 0])
    assert pytest.approx(cosine_similarity(v1, v3)) == 0.0

@pytest.mark.asyncio
async def test_get_embedding_empty():
    assert await get_embedding("") is None
    assert await get_embedding("   ") is None
    assert await get_embedding("\n\n") is None

@pytest.mark.asyncio
@patch("app.services.ai_service.genai_client.get_genai_client")
async def test_get_embedding_success(mock_get_client):
    mock_client = MagicMock()
    mock_result = MagicMock()
    mock_embedding = MagicMock()
    mock_embedding.values = [0.1, 0.2, 0.3]
    mock_result.embeddings = [mock_embedding]
    mock_client.aio.models.embed_content = AsyncMock(return_value=mock_result)
    mock_get_client.return_value = mock_client
    result = await get_embedding("test text")
    assert result == [0.1, 0.2, 0.3]
    mock_client.aio.models.embed_content.assert_awaited_once()

@pytest.mark.asyncio
@patch("app.services.ai_service.genai_client.get_genai_client")
async def test_get_embedding_error(mock_get_client):
    mock_client = MagicMock()
    mock_client.aio.models.embed_content = AsyncMock(side_effect=Exception("API Error"))
    mock_get_client.return_value = mock_client
    result = await get_embedding("test text")
    assert result is None
