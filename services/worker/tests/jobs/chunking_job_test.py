from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from services.worker.jobs.chunking_job import chunking_job


@pytest.mark.asyncio
async def test_chunking_job_uses_leaf_sections_and_replaces_chunks_with_book_id():
    mock_session = AsyncMock()
    mock_pages_res = MagicMock()
    mock_pages_res.scalars.return_value.all.return_value = [
        SimpleNamespace(page_number=1, text="بىرىنچى بەت تېكىستى", is_toc=False),
    ]
    mock_pages_res.scalar_one_or_none.return_value = "in_progress"
    mock_pages_res.fetchall.return_value = []
    mock_session.execute.return_value = mock_pages_res

    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = False

    mock_chunks_repo = AsyncMock()
    mock_chunks_repo.replace_for_book.return_value = 2

    mock_sections_repo = AsyncMock()
    leaf_section = SimpleNamespace(
        id=10,
        book_id="book-123",
        parent_id=1,
        section_index=1,
        level=2,
        section_type="work",
        title="شېئىر",
        normalized_title="شېئىر",
        start_page=1,
        start_block_index=0,
        end_page=1,
        end_block_index=999999,
    )
    mock_sections_repo.list_leaf_sections.return_value = [leaf_section]

    fake_chunk = SimpleNamespace(
        page_number=1,
        end_page_number=1,
        chunk_index=0,
        text="بىرىنچى بەت تېكىستى",
        section_id=10,
        text_hash="abc123hash",
    )

    with (
        patch(
            "services.worker.jobs.chunking_job.db_session.async_session_factory",
            return_value=mock_cm,
        ),
        patch(
            "services.worker.jobs.chunking_job.ChunksRepository",
            return_value=mock_chunks_repo,
        ),
        patch(
            "services.worker.jobs.chunking_job.BookSectionsRepository",
            return_value=mock_sections_repo,
        ),
        patch(
            "services.worker.jobs.chunking_job.chunking_service.chunk_book_sections",
            return_value=[fake_chunk],
        ) as mock_chunk_fn,
    ):
        await chunking_job({}, book_id="book-123")

    mock_sections_repo.list_leaf_sections.assert_awaited_once_with("book-123")
    mock_sections_repo.list_by_book.assert_not_called()
    mock_chunks_repo.get_embedding_hash_map.assert_not_called()
    mock_chunk_fn.assert_called_once()
    mock_chunks_repo.replace_for_book.assert_awaited_once_with(
        "book-123",
        [
            {
                "book_id": "book-123",
                "page_number": 1,
                "end_page_number": 1,
                "chunk_index": 0,
                "text": "بىرىنچى بەت تېكىستى",
                "section_id": 10,
                "text_hash": "abc123hash",
            }
        ],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("unembedded_count", [0, 3])
async def test_chunking_job_resets_graph_milestone_to_idle_when_chunks_replaced(
    unembedded_count: int,
):
    from sqlalchemy.dialects import postgresql

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [
        SimpleNamespace(page_number=1, text="بىرىنچى بەت", is_toc=False),
    ]
    mock_res.scalar_one_or_none.return_value = "in_progress"
    mock_res.fetchall.return_value = []
    mock_session.execute.return_value = mock_res

    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = False

    mock_chunks_repo = AsyncMock()
    mock_chunks_repo.replace_for_book.return_value = unembedded_count

    mock_sections_repo = AsyncMock()
    mock_sections_repo.list_leaf_sections.return_value = []

    fake_chunk = SimpleNamespace(
        page_number=1,
        end_page_number=1,
        chunk_index=0,
        text="بىرىنچى بەت",
        section_id=None,
        text_hash="h1",
    )

    with (
        patch(
            "services.worker.jobs.chunking_job.db_session.async_session_factory",
            return_value=mock_cm,
        ),
        patch(
            "services.worker.jobs.chunking_job.ChunksRepository",
            return_value=mock_chunks_repo,
        ),
        patch(
            "services.worker.jobs.chunking_job.BookSectionsRepository",
            return_value=mock_sections_repo,
        ),
        patch(
            "services.worker.jobs.chunking_job.chunking_service.chunk_book_sections",
            return_value=[fake_chunk],
        ),
        patch("services.worker.jobs.chunking_job.cache_service") as mock_cache,
    ):
        mock_cache.delete_pattern = AsyncMock()
        await chunking_job({}, book_id="book-ready-1")

    book_updates = [
        str(
            call.args[0].compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        for call in mock_session.execute.call_args_list
        if "UPDATE books" in str(call.args[0])
    ]
    assert any("graph_milestone='idle'" in sql for sql in book_updates)
