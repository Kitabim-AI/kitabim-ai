import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.spell_check_service import SpellCheckService, PageSpellCheck, SpellCorrection


def make_service():
    service = SpellCheckService.__new__(SpellCheckService)
    service.model_name = "mock"
    return service


@pytest.mark.asyncio
async def test_check_page_text_empty():
    service = make_service()
    result = await service.check_page_text("   ", 1)
    assert result.totalIssues == 0
    assert result.checkedAt == ""


@pytest.mark.asyncio
async def test_check_page_text_parses_json():
    service = make_service()
    mock_response = MagicMock()
    mock_response.text = "```json\n[{\"original\": \"a\", \"corrected\": \"b\", \"confidence\": 0.9, \"reason\": \"typo\", \"context\": \"ctx\"}]\n```"
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    with patch("app.services.spell_check_service.genai_client.get_genai_client", return_value=mock_client):
        result = await service.check_page_text("text", 1)
    assert result.totalIssues == 1
    assert result.corrections[0].original == "a"


@pytest.mark.asyncio
async def test_check_page_text_parses_json_block_label():
    service = make_service()
    mock_response = MagicMock()
    mock_response.text = "```\njson\n[{\"original\": \"a\", \"corrected\": \"b\", \"confidence\": 0.9, \"reason\": \"typo\"}]\n```"
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    with patch("app.services.spell_check_service.genai_client.get_genai_client", return_value=mock_client):
        result = await service.check_page_text("text", 1)
    assert result.totalIssues == 1


@pytest.mark.asyncio
async def test_check_page_text_invalid_json():
    service = make_service()
    mock_response = MagicMock()
    mock_response.text = "not json"
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    with patch("app.services.spell_check_service.genai_client.get_genai_client", return_value=mock_client):
        result = await service.check_page_text("text", 2)
    assert result.totalIssues == 0
    assert result.checkedAt


@pytest.mark.asyncio
async def test_check_book_not_found():
    service = make_service()
    db = MagicMock()
    db.books.find_one = AsyncMock(return_value=None)

    with pytest.raises(ValueError):
        await service.check_book("missing", db)


@pytest.mark.asyncio
async def test_check_book_filters_pages():
    service = make_service()
    db = MagicMock()
    db.books.find_one = AsyncMock(return_value={
        "_id": "book-id",
        "results": [
            {"pageNumber": 1, "text": "text", "status": "success"},
            {"pageNumber": 2, "text": "", "status": "success"},
            {"pageNumber": 3, "text": "text", "status": "completed"}
        ]
    })

    service.check_page_text = AsyncMock(return_value=PageSpellCheck(
        pageNumber=1,
        corrections=[SpellCorrection(original="a", corrected="b", confidence=0.9, reason="typo")],
        totalIssues=1,
        checkedAt="2024-01-01T00:00:00"
    ))

    results = await service.check_book("book-id", db)
    assert list(results.keys()) == [1]


@pytest.mark.asyncio
async def test_apply_corrections_success():
    service = make_service()
    db = MagicMock()
    db.books.update_one = AsyncMock()
    db.books.find_one = AsyncMock(return_value={
        "_id": "book-id",
        "content": "abc def",
        "results": [
            {"pageNumber": 1, "text": "abc def", "status": "completed", "embedding": [0.1, 0.2]}
        ]
    })

    success = await service.apply_corrections(
        "book-id",
        1,
        [{"original": "abc", "corrected": "xyz"}],
        db
    )

    assert success is True
    update_args = db.books.update_one.call_args.args
    updated_results = update_args[1]["$set"]["results"]
    assert updated_results[0]["text"] == "xyz def"
    assert "embedding" not in updated_results[0]


@pytest.mark.asyncio
async def test_apply_corrections_missing_book():
    service = make_service()
    db = MagicMock()
    db.books.find_one = AsyncMock(return_value=None)

    success = await service.apply_corrections(
        "book-id",
        1,
        [{"original": "a", "corrected": "b"}],
        db
    )

    assert success is False


@pytest.mark.asyncio
async def test_apply_corrections_missing_page():
    service = make_service()
    db = MagicMock()
    db.books.find_one = AsyncMock(return_value={
        "_id": "book-id",
        "results": []
    })

    success = await service.apply_corrections(
        "book-id",
        1,
        [{"original": "a", "corrected": "b"}],
        db
    )

    assert success is False


@pytest.mark.asyncio
async def test_apply_corrections_no_content():
    service = make_service()
    db = MagicMock()
    db.books.update_one = AsyncMock()
    db.books.find_one = AsyncMock(return_value={
        "_id": "book-id",
        "results": [
            {"pageNumber": 1, "text": "abc def", "status": "completed"}
        ]
    })

    success = await service.apply_corrections(
        "book-id",
        1,
        [{"original": "abc", "corrected": "xyz"}],
        db
    )

    assert success is True
    update_args = db.books.update_one.call_args.args
    assert update_args[1]["$set"]["results"][0]["text"] == "xyz def"
