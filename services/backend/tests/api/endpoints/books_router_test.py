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
    from api.endpoints.books_router import reprocess_graph, ReprocessGraphRequest  # type: ignore[import]

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
                request=ReprocessGraphRequest(scope="nonfiction"),
                current_user=mock_user,
                session=mock_session,
            )

    assert excinfo.value.status_code == 400
    assert "Knowledge Graph generation is currently disabled" in excinfo.value.detail


@pytest.mark.asyncio
async def test_reprocess_graph_request_rejects_invalid_scope():
    setup_paths()
    from api.endpoints.books_router import ReprocessGraphRequest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ReprocessGraphRequest(scope="not-a-real-scope")


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
async def test_search_book_content_returns_paginated_hits():
    setup_paths()
    from api.endpoints.books_router import search_book_content

    mock_session = AsyncMock()

    mock_hit = {
        "id": "book-1_5",
        "book_id": "book-1",
        "book_title": "Test Book",
        "book_author": "Test Author",
        "book_volume": 1,
        "book_cover_url": "/covers/1.jpg",
        "page_number": 5,
        "snippet": "Test snippet page content",
        "rank": 0.5,
    }

    mock_repo = AsyncMock()
    mock_repo.search_content_pages = AsyncMock(return_value=([mock_hit], 1))

    with patch("api.endpoints.books_router.PagesRepository", return_value=mock_repo):
        result = await search_book_content(
            q="king Babur",
            page=1,
            pageSize=40,
            current_user=None,
            session=mock_session,
        )

    assert result.total == 1
    assert len(result.hits) == 1
    assert result.hits[0].id == "book-1_5"
    mock_repo.search_content_pages.assert_awaited_once_with(
        "king Babur", skip=0, limit=40, restrict_to_public=True
    )


@pytest.mark.asyncio
async def test_search_book_content_admin_sees_private_books():
    setup_paths()
    from api.endpoints.books_router import search_book_content

    mock_session = AsyncMock()
    mock_user = MagicMock()
    mock_user.role = "admin"

    mock_repo = AsyncMock()
    mock_repo.search_content_pages = AsyncMock(return_value=([], 0))

    with patch("api.endpoints.books_router.PagesRepository", return_value=mock_repo):
        await search_book_content(
            q="king Babur",
            page=2,
            pageSize=20,
            current_user=mock_user,
            session=mock_session,
        )

    mock_repo.search_content_pages.assert_awaited_once_with(
        "king Babur", skip=20, limit=20, restrict_to_public=False
    )


@pytest.mark.asyncio
async def test_update_book_details_overrides_error_status_when_made_public():
    setup_paths()
    from api.endpoints.books_router import update_book_details

    mock_session = AsyncMock()
    mock_user = MagicMock()
    mock_user.email = "editor@example.com"

    mock_book = MagicMock()
    mock_book.status = "error"

    mock_repo = MagicMock()
    mock_repo.get = AsyncMock(return_value=mock_book)
    mock_repo.update_one = AsyncMock(return_value=mock_book)

    mock_cache = MagicMock()
    mock_cache.delete = AsyncMock()
    mock_cache.bump_namespace_version = AsyncMock()

    with (
        patch("api.endpoints.books_router.BooksRepository", return_value=mock_repo),
        patch("api.endpoints.books_router.PagesRepository", return_value=MagicMock()),
        patch("api.endpoints.books_router.cache_service", mock_cache),
    ):
        await update_book_details(
            book_id="book-1",
            book_update={"visibility": "public"},
            current_user=mock_user,
            session=mock_session,
        )

    _, kwargs = mock_repo.update_one.call_args
    assert kwargs["visibility"] == "public"
    assert kwargs["status"] == "ready"
    assert kwargs["pipeline_step"] == "ready"


@pytest.mark.asyncio
async def test_update_book_details_does_not_override_status_when_already_ready():
    setup_paths()
    from api.endpoints.books_router import update_book_details

    mock_session = AsyncMock()
    mock_user = MagicMock()
    mock_user.email = "editor@example.com"

    mock_book = MagicMock()
    mock_book.status = "ready"

    mock_repo = MagicMock()
    mock_repo.get = AsyncMock(return_value=mock_book)
    mock_repo.update_one = AsyncMock(return_value=mock_book)

    mock_cache = MagicMock()
    mock_cache.delete = AsyncMock()
    mock_cache.bump_namespace_version = AsyncMock()

    with (
        patch("api.endpoints.books_router.BooksRepository", return_value=mock_repo),
        patch("api.endpoints.books_router.PagesRepository", return_value=MagicMock()),
        patch("api.endpoints.books_router.cache_service", mock_cache),
    ):
        await update_book_details(
            book_id="book-1",
            book_update={"visibility": "public"},
            current_user=mock_user,
            session=mock_session,
        )

    _, kwargs = mock_repo.update_one.call_args
    assert kwargs["visibility"] == "public"
    assert "status" not in kwargs
    assert "pipeline_step" not in kwargs


@pytest.mark.asyncio
async def test_update_book_details_does_not_override_status_when_not_going_public():
    setup_paths()
    from api.endpoints.books_router import update_book_details

    mock_session = AsyncMock()
    mock_user = MagicMock()
    mock_user.email = "editor@example.com"

    mock_book = MagicMock()
    mock_book.status = "error"

    mock_repo = MagicMock()
    mock_repo.get = AsyncMock(return_value=mock_book)
    mock_repo.update_one = AsyncMock(return_value=mock_book)

    mock_cache = MagicMock()
    mock_cache.delete = AsyncMock()
    mock_cache.bump_namespace_version = AsyncMock()

    with (
        patch("api.endpoints.books_router.BooksRepository", return_value=mock_repo),
        patch("api.endpoints.books_router.PagesRepository", return_value=MagicMock()),
        patch("api.endpoints.books_router.cache_service", mock_cache),
    ):
        await update_book_details(
            book_id="book-1",
            book_update={"title": "New Title"},
            current_user=mock_user,
            session=mock_session,
        )

    _, kwargs = mock_repo.update_one.call_args
    assert "status" not in kwargs
    assert "pipeline_step" not in kwargs


@pytest.mark.asyncio
async def test_merge_graph_entities_endpoint():
    setup_paths()
    from api.endpoints.books_router import merge_graph_entities, MergeEntitiesRequest

    mock_session = AsyncMock()
    mock_user = MagicMock()
    mock_user.email = "admin@example.com"
    mock_user.id = "user-1"

    mock_request = MergeEntitiesRequest(keep_id="keep-1", remove_id="remove-1")

    mock_repo = MagicMock()
    mock_repo.close = AsyncMock()

    with (
        patch(
            "app.db.repositories.graph_repository.GraphRepository",
            return_value=mock_repo,
        ),
        patch(
            "app.services.entity_resolution_service.execute_merge",
            new=AsyncMock(return_value=42),
        ) as mock_execute_merge,
    ):
        response = await merge_graph_entities(
            request=mock_request, current_user=mock_user, session=mock_session
        )

    assert response["status"] == "success"
    assert response["mergeLogId"] == 42
    mock_execute_merge.assert_called_once_with(
        mock_session,
        mock_repo,
        keep_id="keep-1",
        remove_id="remove-1",
        performed_by="admin@example.com",
        user_id="user-1",
    )


@pytest.mark.asyncio
async def test_merge_graph_entities_endpoint_missing_entity_returns_400():
    setup_paths()
    from api.endpoints.books_router import merge_graph_entities, MergeEntitiesRequest

    mock_session = AsyncMock()
    mock_user = MagicMock()
    mock_user.email = "admin@example.com"
    mock_request = MergeEntitiesRequest(keep_id="keep-1", remove_id="missing")

    mock_repo = MagicMock()
    mock_repo.close = AsyncMock()

    with (
        patch(
            "app.db.repositories.graph_repository.GraphRepository",
            return_value=mock_repo,
        ),
        patch(
            "app.services.entity_resolution_service.execute_merge",
            new=AsyncMock(return_value=None),
        ),
    ):
        with pytest.raises(HTTPException) as excinfo:
            await merge_graph_entities(
                request=mock_request, current_user=mock_user, session=mock_session
            )
    assert excinfo.value.status_code == 400


@pytest.mark.asyncio
async def test_merge_entities_request_accepts_camel_case():
    setup_paths()
    from api.endpoints.books_router import MergeEntitiesRequest

    req = MergeEntitiesRequest.model_validate(
        {"keepId": "keep-1", "removeId": "remove-1"}
    )
    assert req.keep_id == "keep-1"
    assert req.remove_id == "remove-1"


@pytest.mark.asyncio
async def test_delete_graph_relationship_endpoint():
    setup_paths()
    from api.endpoints.books_router import (
        delete_graph_relationship,
        DeleteRelationshipRequest,
    )

    mock_session = AsyncMock()
    mock_user = MagicMock()

    mock_request = DeleteRelationshipRequest(edge_id="edge-1")

    mock_repo = MagicMock()
    mock_repo.delete_relationship_by_id = AsyncMock()

    with patch(
        "app.db.repositories.graph_repository.GraphRepository", return_value=mock_repo
    ):
        response = await delete_graph_relationship(
            request=mock_request, current_user=mock_user, session=mock_session
        )

    assert response["status"] == "success"
    mock_repo.delete_relationship_by_id.assert_called_once_with("edge-1")


@pytest.mark.asyncio
async def test_delete_graph_relationship_endpoint_not_found():
    setup_paths()
    from api.endpoints.books_router import (
        delete_graph_relationship,
        DeleteRelationshipRequest,
    )

    mock_session = AsyncMock()
    mock_user = MagicMock()
    mock_request = DeleteRelationshipRequest(edge_id="missing-edge")

    mock_repo = MagicMock()
    mock_repo.delete_relationship_by_id = AsyncMock(side_effect=ValueError("not found"))

    with patch(
        "app.db.repositories.graph_repository.GraphRepository", return_value=mock_repo
    ):
        with pytest.raises(HTTPException) as excinfo:
            await delete_graph_relationship(
                request=mock_request, current_user=mock_user, session=mock_session
            )
    assert excinfo.value.status_code == 400


@pytest.mark.asyncio
async def test_delete_relationship_request_accepts_camel_case():
    setup_paths()
    from api.endpoints.books_router import DeleteRelationshipRequest

    req = DeleteRelationshipRequest.model_validate({"edgeId": "edge-1"})
    assert req.edge_id == "edge-1"


@pytest.mark.asyncio
async def test_rename_graph_entity_endpoint_success():
    setup_paths()
    from api.endpoints.books_router import (
        rename_graph_entity,
        RenameEntityRequest,
    )

    mock_session = AsyncMock()
    mock_user = MagicMock()
    mock_request = RenameEntityRequest(entity_id="entity-1", new_name="NewName")

    mock_repo = MagicMock()
    mock_repo.rename_entity = AsyncMock(return_value=True)

    with (
        patch(
            "app.db.repositories.graph_repository.GraphRepository",
            return_value=mock_repo,
        ),
        patch(
            "app.services.entity_resolution_service.update_alias_cache",
            new=AsyncMock(),
        ) as mock_update_cache,
    ):
        response = await rename_graph_entity(
            request=mock_request, current_user=mock_user, session=mock_session
        )

    assert response["status"] == "success"
    assert response["message"] == "Renamed entity 'entity-1' to 'NewName'"
    mock_repo.rename_entity.assert_called_once_with("entity-1", "NewName")
    mock_update_cache.assert_called_once_with(mock_repo, "entity-1")


@pytest.mark.asyncio
async def test_rename_graph_entity_endpoint_error():
    setup_paths()
    from api.endpoints.books_router import (
        rename_graph_entity,
        RenameEntityRequest,
    )

    mock_session = AsyncMock()
    mock_user = MagicMock()
    mock_request = RenameEntityRequest(entity_id="entity-1", new_name="NewName")

    mock_repo = MagicMock()
    mock_repo.rename_entity = AsyncMock(side_effect=ValueError("Already exists"))

    with patch(
        "app.db.repositories.graph_repository.GraphRepository", return_value=mock_repo
    ):
        with pytest.raises(HTTPException) as excinfo:
            await rename_graph_entity(
                request=mock_request, current_user=mock_user, session=mock_session
            )

    assert excinfo.value.status_code == 400
    assert "Already exists" in excinfo.value.detail


@pytest.mark.asyncio
async def test_rename_entity_request_accepts_camel_case():
    setup_paths()
    from api.endpoints.books_router import RenameEntityRequest

    req = RenameEntityRequest.model_validate(
        {"entityId": "entity-1", "newName": "NewName"}
    )
    assert req.entity_id == "entity-1"
    assert req.new_name == "NewName"


@pytest.mark.asyncio
async def test_upload_pdf_exceeds_size_limit():
    setup_paths()
    from api.endpoints.books_router import upload_pdf
    from app.core.config import settings

    mock_file = AsyncMock()
    mock_file.filename = "large_book.pdf"
    # Stream chunks totaling more than max_book_upload_bytes
    large_chunk = b"X" * (settings.max_book_upload_bytes + 1024)
    mock_file.read = AsyncMock(side_effect=[large_chunk, b""])

    mock_user = MagicMock()
    mock_session = AsyncMock()

    with patch("api.endpoints.books_router.BooksRepository", return_value=MagicMock()):
        with pytest.raises(HTTPException) as excinfo:
            await upload_pdf(
                file=mock_file, current_user=mock_user, session=mock_session
            )

    assert excinfo.value.status_code == 413
    assert "File size exceeds maximum limit" in excinfo.value.detail
