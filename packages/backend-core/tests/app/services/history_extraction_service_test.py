import pytest
from unittest.mock import AsyncMock, patch
from app.services.history_extraction_service import HistoryExtractionService


@pytest.mark.asyncio
async def test_process_book_pages():
    mock_session = AsyncMock()
    service = HistoryExtractionService(mock_session)

    mock_entities = [
        {
            "term": "قاراخانىيلار خاندانلىقى",
            "transliteration": "Karakhanid Khanate",
            "definition": "ئوتتۇرا ئاسىيادىكى تۇنجى ئىسلاملاشقان تۈركىي خانلىق [1].",
            "category": "dynasty",
            "significance_score": 9,
            "significance_reason": "Central historical empire in Central Asia",
            "pages": [10, 11],
        }
    ]

    with patch.object(
        service, "_call_llm_extraction", return_value=mock_entities
    ), patch.object(
        service, "_get_system_config_model", return_value="gemini-2.5-flash"
    ), patch.object(
        service,
        "_stage_entity",
        return_value={"id": 1, "term": "قاراخانىيلار خاندانلىقى"},
    ):
        pages_data = [
            {
                "page_number": 10,
                "content": "قاراخانىيلار خاندانلىقى تۆرەلگەندىن كېيىن...",
            },
            {"page_number": 11, "content": "ئىسلام دىنىنى قوبۇل قىلدى..."},
        ]

        staged_items = await service.process_book_pages(
            book_id="test-book-123",
            book_title="ئۇيغۇر تارىخى",
            volume=1,
            pages_data=pages_data,
            min_significance=5,
        )

        assert len(staged_items) == 1
        assert staged_items[0]["term"] == "قاراخانىيلار خاندانلىقى"
