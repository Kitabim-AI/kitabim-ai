import pytest
import numpy as np
from unittest.mock import patch, MagicMock
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
@patch("google.generativeai.embed_content")
async def test_get_embedding_success(mock_embed):
    mock_embed.return_value = {"embedding": [0.1, 0.2, 0.3]}
    result = await get_embedding("test text")
    assert result == [0.1, 0.2, 0.3]
    mock_embed.assert_called_once()

@pytest.mark.asyncio
@patch("google.generativeai.embed_content")
async def test_get_embedding_error(mock_embed):
    mock_embed.side_effect = Exception("API Error")
    result = await get_embedding("test text")
    assert result is None
