import gzip
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def setup_paths():
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
    core_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../../../../packages/backend-core")
    )
    for m in list(sys.modules.keys()):
        if m == "api" or m.startswith("api."):
            del sys.modules[m]
    for p in [core_dir, backend_dir]:
        if p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)


@pytest.mark.asyncio
async def test_get_backfill_candidates_returns_pdf_books_below_ocr_version():
    setup_paths()
    from api.endpoints.books_router import get_backfill_candidates
    from app.db.models import Book

    mock_session = AsyncMock()
    mock_user = MagicMock()

    b1 = Book(
        id="b1",
        title="Book One",
        author="Author A",
        total_pages=100,
        ocr_version="surya-1.0",
        source="surya_local",
        file_name="b1.pdf",
        file_type="pdf",
        status="ready",
    )
    mock_books_repo = MagicMock()
    mock_books_repo.count_pending_index_books = AsyncMock(return_value=3)
    mock_books_repo.list_backfill_candidates = AsyncMock(return_value=[b1])

    mock_configs_repo = MagicMock()
    mock_configs_repo.get_value = AsyncMock(return_value="true")

    with (
        patch(
            "api.endpoints.books_router.BooksRepository", return_value=mock_books_repo
        ),
        patch(
            "api.endpoints.books_router.SystemConfigsRepository",
            return_value=mock_configs_repo,
        ),
    ):
        res = await get_backfill_candidates(
            ocr_version="surya-2.5-v2",
            limit=10,
            current_user=mock_user,
            session=mock_session,
        )

    assert res.pending_index_books == 3
    assert len(res.candidates) == 1
    assert res.candidates[0].id == "b1"
    assert res.candidates[0].ocr_version == "surya-1.0"
    assert res.candidates[0].total_pages == 100


@pytest.mark.asyncio
async def test_replace_book_ocr_preserves_ready_status_and_writes_first_run_backup():
    setup_paths()
    from api.endpoints.books_router import replace_book_ocr
    from app.db.models import Book, Page

    mock_session = AsyncMock()
    mock_user = MagicMock()
    mock_user.email = "admin@example.com"

    mock_book = Book(
        id="book123",
        title="Test Book",
        total_pages=2,
        status="ready",
        ocr_version="surya-1.0",
        gcs_ocr_backup_uri=None,
        ocr_milestone="complete",
        structure_milestone="complete",
        chunking_milestone="complete",
        embedding_milestone="complete",
    )

    old_pages = [
        Page(
            book_id="book123",
            page_number=1,
            text="old p1",
            is_toc=True,
            content_page_number=None,
            detected_page_number=None,
            status="indexed",
            ocr_milestone="succeeded",
            spell_check_milestone="succeeded",
        ),
        Page(
            book_id="book123",
            page_number=2,
            text="old p2",
            is_toc=False,
            content_page_number="1",
            detected_page_number=None,
            status="indexed",
            ocr_milestone="succeeded",
            spell_check_milestone="succeeded",
        ),
    ]

    mock_books_repo = MagicMock()
    mock_books_repo.get = AsyncMock(return_value=mock_book)
    mock_books_repo.update_one = AsyncMock()

    mock_pages_repo = MagicMock()
    mock_pages_repo.find_by_book = AsyncMock(return_value=old_pages)
    mock_pages_repo.bulk_replace_pages = AsyncMock(return_value=(2, 0))

    mock_configs_repo = MagicMock()
    mock_configs_repo.get_value = AsyncMock(return_value="true")

    payload_dict = {
        "ocrVersion": "surya-2.5-v2",
        "pages": [
            {"pageNumber": 1, "text": "new p1", "detectedPageNumber": None},
            {
                "pageNumber": 2,
                "text": "new p2",
                "isToc": False,
                "detectedPageNumber": 1,
            },
        ],
    }
    compressed_body = gzip.compress(json.dumps(payload_dict).encode("utf-8"))

    mock_request = MagicMock()
    mock_request.headers = {"content-encoding": "gzip"}
    mock_request.body = AsyncMock(return_value=compressed_body)

    uploaded_backups = []

    async def fake_upload_bytes(data, key, **kw):
        uploaded_backups.append((key, data))

    with (
        patch(
            "api.endpoints.books_router.BooksRepository", return_value=mock_books_repo
        ),
        patch(
            "api.endpoints.books_router.PagesRepository", return_value=mock_pages_repo
        ),
        patch(
            "api.endpoints.books_router.SystemConfigsRepository",
            return_value=mock_configs_repo,
        ),
        patch("api.endpoints.books_router.storage") as mock_storage,
        patch("api.endpoints.books_router.cache_service") as mock_cache,
        patch(
            "api.endpoints.books_router._enqueue_structure_job_best_effort",
            new_callable=AsyncMock,
        ),
    ):
        mock_storage.upload_bytes = AsyncMock(side_effect=fake_upload_bytes)
        mock_cache.delete = AsyncMock()
        mock_cache.delete_pattern = AsyncMock()
        mock_cache.bump_namespace_version = AsyncMock()

        res = await replace_book_ocr(
            book_id="book123",
            request=mock_request,
            current_user=mock_user,
            session=mock_session,
        )

    assert res.book_id == "book123"
    assert res.pages_updated == 2
    assert res.status == "ok"

    update_kwargs = mock_books_repo.update_one.call_args.kwargs
    # Book status == 'ready' must be preserved so readers see no downtime
    assert update_kwargs["status"] == "ready"
    assert update_kwargs["ocr_version"] == "surya-2.5-v2"
    assert update_kwargs["structure_milestone"] == "idle"
    assert update_kwargs["gcs_ocr_backup_uri"].startswith(
        "backups/ocr_pre_backfill/book123_"
    )

    # First-run backup written and non-empty
    assert len(uploaded_backups) == 1
    backup_key, gz_data = uploaded_backups[0]
    decompressed_lines = [
        json.loads(line)
        for line in gzip.decompress(gz_data).decode("utf-8").splitlines()
        if line.strip()
    ]
    assert len(decompressed_lines) == 2
    assert decompressed_lines[0]["page_number"] == 1
    assert decompressed_lines[0]["text"] == "old p1"
    assert decompressed_lines[0]["is_toc"] is True

    # Calling a second time when gcs_ocr_backup_uri is already set must NOT upload a new backup
    mock_book.gcs_ocr_backup_uri = backup_key
    mock_request_2 = MagicMock()
    mock_request_2.headers = {}
    mock_request_2.body = AsyncMock(
        return_value=json.dumps(payload_dict).encode("utf-8")
    )

    with (
        patch(
            "api.endpoints.books_router.BooksRepository", return_value=mock_books_repo
        ),
        patch(
            "api.endpoints.books_router.PagesRepository", return_value=mock_pages_repo
        ),
        patch(
            "api.endpoints.books_router.SystemConfigsRepository",
            return_value=mock_configs_repo,
        ),
        patch("api.endpoints.books_router.storage") as mock_storage,
        patch("api.endpoints.books_router.cache_service") as mock_cache,
        patch(
            "api.endpoints.books_router._enqueue_structure_job_best_effort",
            new_callable=AsyncMock,
        ),
    ):
        mock_storage.upload_bytes = AsyncMock(side_effect=fake_upload_bytes)
        mock_cache.delete = AsyncMock()
        mock_cache.delete_pattern = AsyncMock()
        mock_cache.bump_namespace_version = AsyncMock()

        await replace_book_ocr(
            book_id="book123",
            request=mock_request_2,
            current_user=mock_user,
            session=mock_session,
        )

    assert len(uploaded_backups) == 1


@pytest.mark.asyncio
async def test_replace_book_ocr_rejects_mismatched_page_count():
    setup_paths()
    from api.endpoints.books_router import replace_book_ocr
    from app.db.models import Book

    mock_session = AsyncMock()
    mock_user = MagicMock()

    mock_book = Book(
        id="book123", total_pages=5, status="ready", ocr_version="surya-1.0"
    )
    mock_books_repo = MagicMock()
    mock_books_repo.get = AsyncMock(return_value=mock_book)

    payload_dict = {
        "ocrVersion": "surya-2.5-v2",
        "pages": [{"pageNumber": 1, "text": "only one page"}],
    }
    mock_request = MagicMock()
    mock_request.headers = {}
    mock_request.body = AsyncMock(return_value=json.dumps(payload_dict).encode("utf-8"))

    with (
        patch(
            "api.endpoints.books_router.BooksRepository", return_value=mock_books_repo
        ),
        patch("api.endpoints.books_router.PagesRepository"),
        patch("api.endpoints.books_router.SystemConfigsRepository"),
    ):
        with pytest.raises(HTTPException) as excinfo:
            await replace_book_ocr(
                book_id="book123",
                request=mock_request,
                current_user=mock_user,
                session=mock_session,
            )

    assert excinfo.value.status_code == 400


@pytest.mark.asyncio
async def test_bulk_replace_pages_preserves_manual_edits_unless_forced():
    setup_paths()
    from app.db.models import Page
    from app.db.repositories.pages_repository import PagesRepository

    mock_session = AsyncMock()
    repo = PagesRepository(mock_session)

    manual_page = Page(
        id=10,
        book_id="b1",
        page_number=1,
        text="ئەركىن تەھرىرلىگەن تېكىست",
        is_toc=False,
        detected_page_number=None,
        updated_by="editor@example.com",
        status="indexed",
        ocr_milestone="succeeded",
        spell_check_milestone="succeeded",
    )
    auto_page = Page(
        id=11,
        book_id="b1",
        page_number=2,
        text="كونا OCR تېكىستى",
        is_toc=False,
        detected_page_number=None,
        updated_by=None,
        status="indexed",
        ocr_milestone="succeeded",
        spell_check_milestone="succeeded",
    )
    repo.find_by_book = AsyncMock(return_value=[manual_page, auto_page])

    payload = [
        {"page_number": 1, "text": "يېڭى OCR 1", "detected_page_number": 1},
        {"page_number": 2, "text": "يېڭى OCR 2", "detected_page_number": 2},
    ]

    # Default force_overwrite_manual=False: page 1 (manual) is preserved, page 2 is updated
    updated, unchanged = await repo.bulk_replace_pages(
        "b1", payload, reset_spell_check=True, force_overwrite_manual=False
    )
    assert updated == 1
    assert unchanged == 1
    assert manual_page.text == "ئەركىن تەھرىرلىگەن تېكىست"
    assert manual_page.detected_page_number == 1

    # With force_overwrite_manual=True: both pages are updated
    updated_forced, unchanged_forced = await repo.bulk_replace_pages(
        "b1", payload, reset_spell_check=True, force_overwrite_manual=True
    )
    assert updated_forced == 2
    assert unchanged_forced == 0


@pytest.mark.asyncio
async def test_reprocess_chunking_and_embedding_reset_retry_counters():
    setup_paths()
    from api.endpoints.books_router import reprocess_chunking, reprocess_embedding
    from app.db.models import Book

    mock_session = AsyncMock()
    mock_user = MagicMock()
    mock_user.email = "editor@example.com"
    mock_book = Book(id="b1", total_pages=10, status="error")

    mock_books_repo = MagicMock()
    mock_books_repo.get = AsyncMock(return_value=mock_book)
    mock_books_repo.update_one = AsyncMock()

    with (
        patch(
            "api.endpoints.books_router.BooksRepository", return_value=mock_books_repo
        ),
        patch("api.endpoints.books_router.cache_service") as mock_cache,
    ):
        mock_cache.delete = AsyncMock()
        mock_cache.delete_pattern = AsyncMock()

        await reprocess_chunking("b1", current_user=mock_user, session=mock_session)
        chunk_kwargs = mock_books_repo.update_one.call_args.kwargs
        assert chunk_kwargs["chunking_retry_count"] == 0
        assert chunk_kwargs["chunking_claimed_at"] is None
        assert chunk_kwargs["embedding_retry_count"] == 0
        assert chunk_kwargs["embedding_claimed_at"] is None

        mock_books_repo.update_one.reset_mock()
        await reprocess_embedding("b1", current_user=mock_user, session=mock_session)
        embed_kwargs = mock_books_repo.update_one.call_args.kwargs
        assert embed_kwargs["embedding_retry_count"] == 0
        assert embed_kwargs["embedding_claimed_at"] is None


@pytest.mark.asyncio
async def test_update_page_text_noop_save_does_not_delete_cross_page_chunks():
    setup_paths()
    from api.endpoints.books_router import update_page_text
    from app.db.models import Page

    mock_session = AsyncMock()
    mock_user = MagicMock()
    mock_user.email = "editor@example.com"

    existing_page = Page(
        id=42,
        book_id="b1",
        page_number=5,
        text="بىرىنچى ئابزاس تېكىستى",
        status="indexed",
        is_indexed=True,
    )

    mock_books_repo = MagicMock()
    mock_books_repo.update_one = AsyncMock()

    mock_pages_repo = MagicMock()
    mock_pages_repo.find_one = AsyncMock(return_value=existing_page)

    mock_configs_repo = MagicMock()
    mock_configs_repo.get_value = AsyncMock(return_value="gemini-embedding-001")

    with (
        patch(
            "api.endpoints.books_router.BooksRepository", return_value=mock_books_repo
        ),
        patch(
            "api.endpoints.books_router.PagesRepository", return_value=mock_pages_repo
        ),
        patch(
            "api.endpoints.books_router.SystemConfigsRepository",
            return_value=mock_configs_repo,
        ),
        patch("api.endpoints.books_router.cache_service") as mock_cache,
        patch(
            "api.endpoints.books_router._enqueue_structure_job_best_effort",
            new_callable=AsyncMock,
        ) as mock_enqueue,
    ):
        mock_cache.delete = AsyncMock()
        mock_cache.delete_pattern = AsyncMock()

        res = await update_page_text(
            book_id="b1",
            page_num=5,
            payload={"text": "بىرىنچى ئابزاس تېكىستى"},
            current_user=mock_user,
            session=mock_session,
        )

    assert res == {
        "status": "page_updated",
        "requires_rag": False,
        "synchronous": True,
    }
    # Must NOT execute DELETE FROM chunks on a no-op save
    mock_session.execute.assert_not_called()
    mock_enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_page_text_rebuilds_full_multi_page_span_when_overlapping_cross_page_chunk():
    setup_paths()
    from types import SimpleNamespace
    from api.endpoints.books_router import update_page_text
    from app.db.models import Page

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_user = MagicMock()
    mock_user.email = "editor@example.com"

    page4 = Page(
        id=41,
        book_id="b1",
        page_number=4,
        text="4-بەت تېكىستى داۋاملىشىدۇ",
        is_toc=False,
        status="indexed",
    )
    page5 = Page(
        id=42,
        book_id="b1",
        page_number=5,
        text="5-بەت كونا تېكىستى.",
        is_toc=False,
        status="indexed",
    )
    page6 = Page(
        id=43,
        book_id="b1",
        page_number=6,
        text="6-بەت تېكىستى تاماملىنىدۇ.",
        is_toc=False,
        status="indexed",
    )

    spell_del_res = MagicMock()
    span_res = MagicMock()
    span_res.first.return_value = (4, 6)

    del_res = MagicMock()

    span_pages_res = MagicMock()
    span_pages_res.scalars.return_value.all.return_value = [page4, page5, page6]

    initial_results = iter([spell_del_res, span_res, del_res, span_pages_res])

    async def _fake_execute(stmt, *args, **kwargs):
        return next(initial_results, MagicMock())

    mock_session.execute.side_effect = _fake_execute

    mock_books_repo = MagicMock()
    mock_books_repo.update_one = AsyncMock()

    mock_pages_repo = MagicMock()
    mock_pages_repo.find_one = AsyncMock(return_value=page5)
    mock_pages_repo.update_one = AsyncMock()

    mock_configs_repo = MagicMock()
    mock_configs_repo.get_value = AsyncMock(return_value="gemini-embedding-001")

    sec1 = SimpleNamespace(
        id=101,
        title="باب 2",
        level=1,
        section_index=2,
        start_page=4,
        end_page=6,
        parent_section_id=None,
    )
    sec0 = SimpleNamespace(
        id=100,
        title="باب 1",
        level=1,
        section_index=1,
        start_page=4,
        end_page=6,
        parent_section_id=None,
    )
    mock_sections_repo = MagicMock()
    mock_sections_repo.list_leaf_sections = AsyncMock(return_value=[sec1, sec0])

    mock_embed_svc = MagicMock()
    mock_embed_svc.aembed_documents = AsyncMock(
        side_effect=lambda texts, **kw: [[0.1] * 8 for _ in texts]
    )

    with (
        patch(
            "api.endpoints.books_router.BooksRepository", return_value=mock_books_repo
        ),
        patch(
            "api.endpoints.books_router.PagesRepository", return_value=mock_pages_repo
        ),
        patch(
            "api.endpoints.books_router.SystemConfigsRepository",
            return_value=mock_configs_repo,
        ),
        patch(
            "app.db.repositories.book_sections_repository.BookSectionsRepository",
            return_value=mock_sections_repo,
        ),
        patch(
            "api.endpoints.books_router.GeminiEmbeddings", return_value=mock_embed_svc
        ),
        patch(
            "app.services.book_milestone_service.BookMilestoneService.update_book_milestones",
            new_callable=AsyncMock,
        ),
        patch("api.endpoints.books_router.cache_service") as mock_cache,
        patch(
            "api.endpoints.books_router._enqueue_structure_job_best_effort",
            new_callable=AsyncMock,
        ) as mock_enqueue,
    ):
        mock_cache.delete = AsyncMock()
        mock_cache.delete_pattern = AsyncMock()

        res = await update_page_text(
            book_id="b1",
            page_num=5,
            payload={"text": "5-بەت يېڭى تېكىستى."},
            current_user=mock_user,
            session=mock_session,
        )

    assert res["status"] == "page_updated"
    assert res["requires_rag"] is True
    assert mock_session.add.called
    added_chunks = [c.args[0] for c in mock_session.add.call_args_list]
    combined_chunk_text = "\n".join(c.text for c in added_chunks)
    assert "4-بەت تېكىستى" in combined_chunk_text
    assert "5-بەت يېڭى تېكىستى" in combined_chunk_text
    assert "6-بەت تېكىستى" in combined_chunk_text
    mock_enqueue.assert_awaited_once_with("b1")
