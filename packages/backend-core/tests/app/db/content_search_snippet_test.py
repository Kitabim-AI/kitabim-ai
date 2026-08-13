import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.db.repositories.pages_repository import PagesRepository


@pytest.mark.asyncio
async def test_search_content_pages_truncates_snippet_to_config_limit():
    session = AsyncMock()
    repo = PagesRepository(session)

    mock_count_res = MagicMock()
    mock_count_res.scalar_one.return_value = 1

    long_text = "سۆز " * 200  # ~800 chars
    mock_row = MagicMock()
    mock_row.book_id = "b1"
    mock_row.page_number = 1
    mock_row.snippet = long_text
    mock_row.full_text = long_text
    mock_row.title = "تارىخ كىتابى"
    mock_row.volume = None
    mock_row.author = "ئاپتور"
    mock_row.cover_url = None
    mock_row.rank = 1.0

    mock_hits_res = MagicMock()
    mock_hits_res.fetchall.return_value = [mock_row]

    session.execute.side_effect = [
        MagicMock(),  # SET work_mem
        MagicMock(),  # SET statement_timeout
        mock_count_res,
        mock_hits_res,
    ]

    with patch(
        "app.db.repositories.system_configs_repository.SystemConfigsRepository.get_value",
        return_value="500",
    ):
        hits, total = await repo.search_content_pages("سۆز", skip=0, limit=10)

    assert total == 1
    assert len(hits) == 1
    # Check that snippet length is capped around 500 characters
    assert len(hits[0]["snippet"]) <= 503  # 500 + "..."
    assert hits[0]["snippet"].endswith("...")
