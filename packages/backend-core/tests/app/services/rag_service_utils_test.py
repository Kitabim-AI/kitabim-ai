import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.rag.answer_builder import Document

from app.services.rag.utils import (
    is_current_volume_query,
    is_current_page_query,
    normalize_uyghur,
    is_author_or_catalog_query,
    entity_matches_question,
)
from app.services.rag.answer_builder import format_document
from app.services.rag.handlers.catalog import CatalogHandler


def test_is_current_volume_query():
    assert is_current_volume_query("ئۇشبۇ تومدا بارمۇ؟") is True
    assert is_current_volume_query("") is False
    assert is_current_volume_query(None) is False


def test_is_current_page_query():
    assert is_current_page_query("بۇ بەتتە نېمە بار؟") is True
    assert is_current_page_query("") is False
    assert is_current_page_query(None) is False


def test_normalize_uyghur():
    orig = "ئېيى"
    norm = normalize_uyghur(orig)
    assert norm == normalize_uyghur("ئىيى")


def test_is_author_or_catalog_query():
    assert is_author_or_catalog_query("بۇ كىتابنىڭ ئاپتورى كىم؟") is True
    assert is_author_or_catalog_query("بەت 10 نى ئوقۇ") is False


def test_entity_matches_question():
    assert entity_matches_question("زوردۇن سابىر", "زوردۇن سابىرنىڭ ئەسىرى") is True
    assert entity_matches_question("زوردۇن سابىر", "يازغۇچى كىم؟") is False


def test_format_document():
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
    formatted = format_document(doc)
    assert "Content" in formatted
    assert "Title" in formatted
    assert "BookID: b1" in formatted


@pytest.mark.asyncio
async def test_build_catalog_context_title_match():
    session = AsyncMock()
    
    # 1st execute is select Book.title to get all title candidates
    mock_titles = MagicMock()
    mock_titles.fetchall.return_value = [("ئانا يۇرت",)]
    
    # 2nd execute is select title, author, volume, etc. for matched title
    mock_books = MagicMock()
    mock_books.fetchall.return_value = [
        MagicMock(title="ئانا يۇرت", author="زوردۇن سابىر", volume=1, total_pages=500, status="ready")
    ]
    
    session.execute.side_effect = [
        mock_titles,
        mock_books
    ]

    ctx, count = await CatalogHandler._build_catalog_context("ئانا يۇرتتا نېمە بار؟", session)
    assert "ئانا يۇرت" in ctx
    assert "زوردۇن سابىر" in ctx
    assert count == 1
