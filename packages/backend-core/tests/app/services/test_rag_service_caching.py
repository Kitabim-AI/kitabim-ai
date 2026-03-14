import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.rag_service import RAGService
from app.models.schemas import ChatRequest

from app.core import cache_config

@pytest.mark.asyncio
async def test_rag_answer_uses_embedding_cache(monkeypatch):
    # mocks
    mock_cache = AsyncMock()
    mock_cache.get = AsyncMock(return_value=None) # Start with miss
    mock_cache.set = AsyncMock()
    
    mock_embeddings = AsyncMock()
    mock_embeddings.aembed_query = AsyncMock(return_value=[0.1, 0.2])
    
    # Patches inside RAGService
    monkeypatch.setattr("app.services.rag_service.cache_service", mock_cache)
    
    # Mocking repositories that are locally imported
    mock_configs_repo = AsyncMock()
    mock_configs_repo.get_value = AsyncMock(side_effect=lambda key, default=None: default)
    
    with patch("app.db.repositories.system_configs.SystemConfigsRepository", return_value=mock_configs_repo), \
         patch("app.db.repositories.books.BooksRepository", return_value=AsyncMock()), \
         patch("app.db.repositories.pages.PagesRepository", return_value=AsyncMock()), \
         patch("app.db.repositories.chunks.ChunksRepository", return_value=AsyncMock()):
        
        service = RAGService()
        service.embeddings = mock_embeddings
        monkeypatch.setattr("app.services.rag_service.cache_service", mock_cache)
        
        # Mocking other methods to avoid real LLM calls
        service._find_books_by_title_in_question = AsyncMock(return_value=[])
        service._build_catalog_context = AsyncMock(return_value=("context", 1))
        service._generate_answer = AsyncMock(return_value="answer")
        service._record_eval = AsyncMock()
        
        req = ChatRequest(book_id="global", question="How are you?", history=[])
        
        # Mock session
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result
        
        # Run
        await service.answer_question(req, mock_session)


    
    # Verify embedding cache was checked
    mock_cache.get.assert_any_call(pytest_match_any_string_containing("rag:embedding:"))
    # Verify embedding was generated and stored
    mock_embeddings.aembed_query.assert_called_once()
    from unittest.mock import ANY
    mock_cache.set.assert_any_call(pytest_match_any_string_containing("rag:embedding:"), [0.1, 0.2], ttl=ANY)

# Helper for pytest
def pytest_match_any_string_containing(pattern):
    class Match:
        def __eq__(self, other):
            return isinstance(other, str) and pattern in other
        def __repr__(self):
            return f"<String containing '{pattern}'>"
    return Match()

pytest.match_any_string_containing = pytest_match_any_string_containing
