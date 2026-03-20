import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.rag_service import RAGService
from app.models.schemas import ChatRequest

@pytest.fixture
def rag_service():
    return RAGService()

@pytest.mark.asyncio
async def test_rag_get_embeddings(rag_service):
    with patch("app.services.rag_service.GeminiEmbeddings") as mock_emb:
        rag_service._get_embeddings("model-1")
        assert "model-1" in rag_service._embeddings_cache
        rag_service._get_embeddings("model-1")
        assert mock_emb.call_count == 1

@pytest.mark.asyncio
async def test_rag_get_chains(rag_service):
    with patch("app.services.rag_service.build_text_chain"):
        with patch("app.services.rag_service.build_structured_chain"):
            rag_service._get_rag_chain("m1")
            rag_service._get_category_chain("m1")
            assert "m1" in rag_service._rag_chains
            assert "m1" in rag_service._category_chains

def test_rag_is_current_volume_query():
    assert RAGService._is_current_volume_query("ئۇشبۇ تومدا بارمۇ؟") is True
    assert RAGService._is_current_volume_query("") is False
    assert RAGService._is_current_volume_query(None) is False

def test_rag_is_current_page_query():
    assert RAGService._is_current_page_query("بۇ بەتتە نېمە بار؟") is True
    assert RAGService._is_current_page_query("") is False

@pytest.mark.asyncio
async def test_rag_answer_question_catalog(rag_service):
    session = AsyncMock()
    session.add = MagicMock()
    req = ChatRequest(book_id="global", question="مۇئەللىپ كىم؟", history=[])
    
    # Mock repositories
    mock_configs = MagicMock()
    mock_configs.get_value = AsyncMock(side_effect=["chat-model", "cat-model", "emb-model"])
    
    with patch("app.db.repositories.system_configs.SystemConfigsRepository", return_value=mock_configs):
        with patch("app.db.repositories.books.BooksRepository"):
            with patch("app.db.repositories.pages.PagesRepository"):
                with patch("app.db.repositories.chunks.ChunksRepository"):
                    with patch.object(rag_service, "_generate_answer", return_value="The author is X"):
                        # Mock _build_catalog_context
                        with patch.object(rag_service, "_build_catalog_context", return_value=("Context", 1)):
                            res = await rag_service.answer_question(req, session)
                            assert res == "The author is X"

@pytest.mark.asyncio
async def test_rag_answer_question_full_loop(rag_service):
    session = AsyncMock()
    session.add = MagicMock()
    req = ChatRequest(book_id="b1", question="What is in the book?", history=[])
    
    mock_configs = MagicMock()
    mock_configs.get_value = AsyncMock(side_effect=["chat-model", "cat-model", "emb-model"])
    
    with patch("app.db.repositories.system_configs.SystemConfigsRepository", return_value=mock_configs):
        with patch("app.db.repositories.books.BooksRepository") as mock_books_repo_cls:
            mock_books_repo = mock_books_repo_cls.return_value
            mock_book = MagicMock()
            mock_book.id = "b1"
            mock_book.title = "T1"
            mock_book.author = "A1"
            mock_book.status = "ready"
            mock_books_repo.get = AsyncMock(return_value=mock_book)
            
            # Mock session.execute for siblings search
            mock_siblings_res = MagicMock()
            mock_siblings_res.fetchall.return_value = []
            session.execute = AsyncMock(return_value=mock_siblings_res)
            
            with patch("app.db.repositories.pages.PagesRepository"):
                with patch("app.db.repositories.chunks.ChunksRepository") as mock_chunks_repo_cls:
                    mock_chunks_repo = mock_chunks_repo_cls.return_value
                    mock_chunks_repo.similarity_search = AsyncMock(return_value=[
                        {"text": "Content", "similarity": 0.9, "page_number": 1, "title": "T1", "book_id": "b1"}
                    ])
                    
                    with patch("app.services.rag_service.cache_service") as mock_cache:
                        # First call for embedding, second call for search results
                        # We return None for search results so it calls similarity_search
                        mock_cache.get = AsyncMock(side_effect=[[0.1]*768, None])
                        
                        with patch.object(rag_service, "_generate_answer", return_value="Answer from RAG"):
                            res = await rag_service.answer_question(req, session)
                            assert res == "Answer from RAG"

@pytest.mark.asyncio
async def test_rag_generate_answer(rag_service):
    chain = AsyncMock()
    chain.ainvoke.return_value = " Predicted "
    
    res = await rag_service._generate_answer("Context", "Question", chain)
    assert res == "Predicted"

@pytest.mark.asyncio
async def test_rag_categorize_question(rag_service):
    chain = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.categories = ["cat1"]
    chain.ainvoke.return_value = mock_resp
    
    cats = await rag_service._categorize_question("Question", ["cat1", "cat2"], chain)
    assert cats == ["cat1"]
