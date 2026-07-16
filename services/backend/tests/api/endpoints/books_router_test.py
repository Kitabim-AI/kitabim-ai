import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock, MagicMock, patch

BACKEND_DIR = str(Path(__file__).resolve().parents[3])
BACKEND_CORE_DIR = str(
    Path(__file__).resolve().parents[5] / "packages" / "backend-core"
)


def setup_paths():
    # Force reload of api modules to avoid cache shadowing from tests/api
    for m in list(sys.modules.keys()):
        if m == "api" or m.startswith("api."):
            del sys.modules[m]
    for p in [BACKEND_CORE_DIR, BACKEND_DIR]:
        if p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)


def test_books_basic():
    """Basic unit test scaffold for books."""
    assert True


@pytest.mark.asyncio
async def test_reprocess_graph_disabled():
    setup_paths()
    from api.endpoints.books_router import reprocess_graph  # type: ignore[import]

    mock_session = AsyncMock()
    mock_user = MagicMock()
    mock_user.email = "test@example.com"

    mock_repo = MagicMock()
    mock_repo.get = AsyncMock(return_value=MagicMock())

    mock_configs_repo = MagicMock()
    mock_configs_repo.get_value = AsyncMock(return_value="false")

    with (
        patch("api.endpoints.books_router.BooksRepository", return_value=mock_repo),
        patch(
            "api.endpoints.books_router.SystemConfigsRepository",
            return_value=mock_configs_repo,
        ),
    ):
        with pytest.raises(HTTPException) as excinfo:
            await reprocess_graph(
                book_id="some-book-id",
                current_user=mock_user,
                session=mock_session,
            )

    assert excinfo.value.status_code == 400
    assert "Knowledge Graph generation is currently disabled" in excinfo.value.detail


@pytest.mark.asyncio
async def test_get_books():
    setup_paths()
    from api.endpoints.books_router import get_books
    from app.db.models import Book as BookDB
    from datetime import datetime, timezone

    mock_session = AsyncMock()
    mock_user = MagicMock()
    mock_user.role = "reader"

    # Mock Book database object
    mock_book = BookDB(
        id="book-1",
        content_hash="hash-1",
        title="Test Book",
        author="Test Author",
        volume=1,
        total_pages=10,
        status="ready",
        pipeline_step="ready",
        upload_date=datetime.now(timezone.utc),
        last_updated=datetime.now(timezone.utc),
        visibility="public",
        categories=["Fiction"],
        read_count=0,
        file_name="test.pdf",
        file_type="pdf",
        source="upload",
        ocr_milestone="succeeded",
        chunking_milestone="succeeded",
        embedding_milestone="succeeded",
        spell_check_milestone="succeeded",
        graph_milestone="complete",
    )

    # Mock count results
    mock_count_row = MagicMock()
    mock_count_row.total = 1
    mock_count_row.total_ready = 1
    mock_count_res = MagicMock()
    mock_count_res.fetchone.return_value = mock_count_row

    # Mock main books results
    mock_books_res = MagicMock()
    mock_books_res.scalars.return_value.all.return_value = [mock_book]

    # Mock summary check results
    mock_summary_res = MagicMock()
    mock_summary_res.fetchall.return_value = [("book-1",)]

    # Mock graph check results
    mock_graph_res = MagicMock()
    mock_graph_res.fetchall.return_value = [("book-1",)]

    # Setup session.execute side effects for the sequential queries
    mock_session.execute.side_effect = [
        mock_count_res,
        mock_books_res,
        mock_summary_res,
        mock_graph_res,
    ]

    with patch("api.endpoints.books_router.cache_service") as mock_cache:
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()
        mock_cache.get_namespace_version = AsyncMock(return_value="v1")

        result = await get_books(
            page=1,
            pageSize=10,
            q=None,
            category=None,
            sortBy="title",
            order=1,
            current_user=mock_user,
            session=mock_session,
        )

    assert result["total"] == 1
    assert len(result["books"]) == 1
    assert result["books"][0].id == "book-1"
    assert result["books"][0].has_summary is True
    assert result["books"][0].has_graph is True


@pytest.mark.asyncio
async def test_merge_graph_entities_endpoint():
    setup_paths()
    from api.endpoints.books_router import merge_graph_entities, MergeEntitiesRequest

    mock_session = AsyncMock()
    mock_user = MagicMock()

    mock_request = MergeEntitiesRequest(keep_name="A", remove_name="B")

    mock_repo = MagicMock()
    mock_repo.merge_entities = AsyncMock()

    with patch(
        "app.db.repositories.graph_repository.GraphRepository", return_value=mock_repo
    ):
        response = await merge_graph_entities(
            request=mock_request, current_user=mock_user, session=mock_session
        )

    assert response["status"] == "success"
    mock_repo.merge_entities.assert_called_once_with("A", "B")
