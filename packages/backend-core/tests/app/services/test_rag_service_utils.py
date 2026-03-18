import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.documents import Document
from app.services.rag_service import RAGService
from app.db.models import Book

@pytest.fixture
def rag_service():
    return RAGService()

def test_is_current_volume_query(rag_service):
    assert rag_service._is_current_volume_query("ئۇشبۇ تومدا بارمۇ؟") is True
    assert rag_service._is_current_volume_query("مەزكور قىسىمدا نېمە بار؟") is True

def test_is_current_page_query(rag_service):
    assert rag_service._is_current_page_query("بۇ بەتتە نېمە بار؟") is True
    assert rag_service._is_current_page_query("ئۇشبۇ بەتتە كىم بار؟") is True

def test_normalize_uyghur(rag_service):
    orig = "ئېيى"
    norm = rag_service._normalize_uyghur(orig)
    assert "\u06D0" not in norm
    assert "\u064A" not in norm

def test_is_author_or_catalog_query(rag_service):
    assert rag_service._is_author_or_catalog_query("بۇ كىتابنىڭ ئاپتورى كىم؟") is True
    assert rag_service._is_author_or_catalog_query("قايسى كىتابلار بار؟") is True

def test_entity_matches_question(rag_service):
    assert rag_service._entity_matches_question("زوردۇن سابىر", "زوردۇن سابىرنىڭ ئەسىرى") is True
    assert rag_service._entity_matches_question("ئانا يۇرت", "ئانا يۇرتتا نېمە بار؟") is True

def test_format_book_catalog(rag_service):
    # The standalone _format_book_catalog method does NOT include status tags
    books = [
        MagicMock(title="T1", author="A1"),
        MagicMock(title="T2", author=None)
    ]
    catalog = rag_service._format_book_catalog(books)
    assert "T1 (Author: A1)" in catalog
    assert "- T2" in catalog

def test_format_document(rag_service):
    doc = Document(
        page_content="Content",
        metadata={
            "book_id": "b1",
            "title": "Title",
            "author": "Author",
            "volume": 1,
            "page": 10
        }
    )
    formatted = rag_service._format_document(doc)
    assert "[BookID: b1, Book: Title, Author: Author, Volume: 1, Page: 10]\nContent" == formatted

@pytest.mark.asyncio
async def test_build_catalog_context_title_match(rag_service):
    session = AsyncMock()
    mock_titles = MagicMock()
    mock_titles.fetchall.return_value = [("ئانا يۇرت",)]
    session.execute.side_effect = [
        mock_titles,
        MagicMock(fetchall=MagicMock(return_value=[MagicMock(title="ئانا يۇرت", author="سابىر", volume=1, total_pages=500, status="ready")]))
    ]
    
    ctx, count = await rag_service._build_catalog_context("ئانا يۇرتتا نېمە بار؟", session)
    assert "Information about 'ئانا يۇرت':" in ctx
    assert count == 1
