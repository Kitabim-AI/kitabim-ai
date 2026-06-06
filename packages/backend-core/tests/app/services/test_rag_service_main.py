import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.rag_service import RAGService
from app.models.schemas import ChatRequest


@pytest.fixture
def rag_service():
    return RAGService()


@pytest.mark.asyncio
async def test_answer_question_catalog_query(rag_service):
    session = AsyncMock()
    req = ChatRequest(
        book_id="global",
        question="قايسى كىتابلار بار؟",
        history=[]
    )
    
    # Mock system configs and dependencies called in _build_context
    with patch("app.db.repositories.system_configs.SystemConfigsRepository.get_value", side_effect=["chat-model", "emb-model", "agent-model", "6", "8", "false"]), \
         patch("app.services.rag_service.llm_resources") as mock_resources:
         
        mock_resources.get_rag_chain.return_value = MagicMock()
        mock_resources.get_rewrite_chain.return_value = MagicMock()
        mock_resources.get_embeddings.return_value = MagicMock()
        
        # Mock registry dispatch
        rag_service._registry.dispatch = AsyncMock(return_value="AI Answer")
        
        answer = await rag_service.answer_question(req, session)
        assert answer == "AI Answer"
        
        # Verify dispatch was called with QueryContext
        rag_service._registry.dispatch.assert_called_once()
        called_ctx = rag_service._registry.dispatch.call_args[0][0]
        assert called_ctx.question == "قايسى كىتابلار بار؟"
        assert called_ctx.is_global is True


@pytest.mark.asyncio
async def test_answer_question_current_page_only(rag_service):
    session = AsyncMock()
    req = ChatRequest(
        book_id="book-123",
        question="بۇ بەتتە نېمە بار؟",
        current_page=10,
        history=[]
    )
    
    mock_book = MagicMock()
    mock_book.id = "book-123"
    mock_book.title = "Book"
    mock_book.author = "A"
    
    with patch("app.db.repositories.system_configs.SystemConfigsRepository.get_value", side_effect=["chat-model", "emb-model", "agent-model", "6", "8", "false"]), \
         patch("app.db.repositories.books.BooksRepository.get", return_value=mock_book), \
         patch("app.services.rag_service.llm_resources") as mock_resources:
         
        mock_resources.get_rag_chain.return_value = MagicMock()
        mock_resources.get_rewrite_chain.return_value = MagicMock()
        mock_resources.get_embeddings.return_value = MagicMock()
        
        rag_service._registry.dispatch = AsyncMock(return_value="Page Answer")
        
        answer = await rag_service.answer_question(req, session)
        assert answer == "Page Answer"
        
        called_ctx = rag_service._registry.dispatch.call_args[0][0]
        assert called_ctx.book_id == "book-123"
        assert called_ctx.book == mock_book


@pytest.mark.asyncio
async def test_answer_question_stream(rag_service):
    session = AsyncMock()
    req = ChatRequest(
        book_id="global",
        question="Hello",
        history=[]
    )
    
    async def mock_stream(ctx):
        yield "Hello"
        yield " world"
        
    with patch("app.db.repositories.system_configs.SystemConfigsRepository.get_value", side_effect=["chat-model", "emb-model", "agent-model", "6", "8", "false"]), \
         patch("app.services.rag_service.llm_resources") as mock_resources:
         
        mock_resources.get_rag_chain.return_value = MagicMock()
        mock_resources.get_rewrite_chain.return_value = MagicMock()
        mock_resources.get_embeddings.return_value = MagicMock()
        
        rag_service._registry.dispatch_stream = mock_stream
        
        chunks = []
        async for chunk in rag_service.answer_question_stream(req, session):
            chunks.append(chunk)
            
        assert chunks == ["Hello", " world"]
