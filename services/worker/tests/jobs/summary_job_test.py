import pytest
from unittest.mock import AsyncMock, MagicMock, patch, ANY
from services.worker.jobs.summary_job import summary_job
from app.db.models import Book, Page


@pytest.mark.asyncio
async def test_summary_job_success():
    ctx = {"redis": AsyncMock(), "worker_id": "test_worker"}
    book_id = "test-book"

    # Mock DB Session
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.add = MagicMock()

    # Mock book model
    mock_book = MagicMock(spec=Book)
    mock_book.id = book_id
    mock_book.title = "Test Book"
    mock_book.author = "Test Author"

    # Mock Page model
    mock_page = MagicMock(spec=Page)
    mock_page.text = "Sample page text."
    mock_page.page_number = 1

    # Mock session execute results
    mock_result_book = MagicMock()
    mock_result_book.scalar_one_or_none.return_value = mock_book

    mock_result_pages = MagicMock()
    mock_result_pages.fetchall.return_value = [(mock_page.text,)]

    async def mock_execute(stmt, *args, **kwargs):
        stmt_str = str(stmt).lower()
        if "from books" in stmt_str:
            return mock_result_book
        elif "from pages" in stmt_str:
            return mock_result_pages
        else:
            return MagicMock()

    mock_session.execute.side_effect = mock_execute

    with patch("app.db.session.async_session_factory") as mock_session_factory, patch(
        "services.worker.jobs.summary_job.SystemConfigsRepository.get_value",
        new_callable=AsyncMock,
    ) as mock_get_value, patch(
        "services.worker.jobs.summary_job.build_text_chain"
    ) as mock_build_text_chain, patch(
        "services.worker.jobs.summary_job.GeminiEmbeddings",
        spec=True,
    ) as mock_embeddings_cls, patch(
        "services.worker.jobs.summary_job.BookSummariesRepository",
        spec=True,
    ) as mock_repo_cls:
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        # Mock system configs
        mock_get_value.side_effect = lambda key, default=None: {
            "gemini_chat_model": "gemini-2.0-flash",
            "gemini_embedding_model": "text-embedding-004",
        }.get(key, default)

        # Mock build_text_chain & ainvoke
        mock_chain = AsyncMock()
        mock_chain.ainvoke.return_value = "This is a summary."
        mock_build_text_chain.return_value = mock_chain

        # Mock embeddings
        mock_embed_instance = AsyncMock()
        mock_embed_instance.aembed_documents.return_value = [[0.1, 0.2, 0.3]]
        mock_embeddings_cls.return_value = mock_embed_instance

        # Mock repo
        mock_repo = AsyncMock()
        mock_repo_cls.return_value = mock_repo

        # Run job
        await summary_job(ctx, book_id)

        # Verify build_text_chain was called with correct model
        mock_build_text_chain.assert_called_once_with(
            ANY,  # prompt template
            "gemini-2.0-flash",
            run_name="summary_chain",
        )

        # Verify ainvoke was called with timeout_config_key
        mock_chain.ainvoke.assert_called_once_with(
            {
                "title": "Test Book",
                "author": "Test Author",
                "text": "Sample page text.",
            },
            timeout_config_key="gemini_summary_timeout",
        )

        # Verify repo upsert
        mock_repo.upsert.assert_called_once_with(
            book_id=book_id,
            summary="This is a summary.",
            embedding=[0.1, 0.2, 0.3],
        )
        mock_session.commit.assert_called_once()
