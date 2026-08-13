import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.db.repositories.pages_repository import PagesRepository
from app.db.models import Page


@pytest.mark.asyncio
async def test_find_by_book():
    session = AsyncMock()
    repo = PagesRepository(session)

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [
        Page(id=1, book_id="b1", page_number=1)
    ]
    session.execute.return_value = mock_res

    pages = await repo.find_by_book("b1")
    assert len(pages) == 1
    assert pages[0].book_id == "b1"


@pytest.mark.asyncio
async def test_update_many_status():
    session = AsyncMock()
    repo = PagesRepository(session)
    mock_res = MagicMock()
    mock_res.rowcount = 5
    session.execute.return_value = mock_res

    count = await repo.update_many_status("b1", [1, 2, 3], "done")
    assert count == 5
    assert session.flush.called


@pytest.mark.asyncio
async def test_delete_by_book():
    session = AsyncMock()
    repo = PagesRepository(session)
    mock_res = MagicMock()
    mock_res.rowcount = 10
    session.execute.return_value = mock_res

    count = await repo.delete_by_book("b1")
    assert count == 10
    assert session.flush.called


@pytest.mark.asyncio
async def test_count_by_book():
    session = AsyncMock()
    repo = PagesRepository(session)
    mock_res = MagicMock()
    mock_res.scalar_one.return_value = 100
    session.execute.return_value = mock_res

    count = await repo.count_by_book("b1", status="done")
    assert count == 100


def test_get_pages_repository():
    from app.db.repositories.pages_repository import get_pages_repository

    session = AsyncMock()
    repo = get_pages_repository(session)
    assert isinstance(repo, PagesRepository)


@pytest.mark.asyncio
async def test_find_one():
    session = AsyncMock()
    repo = PagesRepository(session)

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = Page(id=1, book_id="b1", page_number=1)
    session.execute.return_value = mock_res

    page = await repo.find_one("b1", 1)
    assert page.page_number == 1


@pytest.mark.asyncio
async def test_upsert():
    session = AsyncMock()
    repo = PagesRepository(session)

    mock_res = MagicMock()
    mock_res.scalar_one.return_value = Page(id=1, book_id="b1", page_number=1)
    session.execute.return_value = mock_res

    page_data = {"book_id": "b1", "page_number": 1, "text": "test"}
    page = await repo.upsert(page_data)

    assert page.id == 1
    assert session.flush.called


@pytest.mark.asyncio
async def test_update_status():
    session = AsyncMock()
    repo = PagesRepository(session)

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = Page(id=1, status="ready")
    session.execute.return_value = mock_res

    page = await repo.update_status("b1", 1, "ready")
    assert page.status == "ready"
    assert session.flush.called


@pytest.mark.asyncio
async def test_set_is_toc_marks_page():
    session = AsyncMock()
    repo = PagesRepository(session)
    mock_res = MagicMock()
    mock_res.rowcount = 1
    session.execute.return_value = mock_res

    result = await repo.set_is_toc("b1", 5, True, "editor@example.com")
    assert result is True
    assert session.flush.called


@pytest.mark.asyncio
async def test_set_is_toc_unmarks_page():
    session = AsyncMock()
    repo = PagesRepository(session)
    mock_res = MagicMock()
    mock_res.rowcount = 1
    session.execute.return_value = mock_res

    result = await repo.set_is_toc("b1", 5, False, "editor@example.com")
    assert result is True


@pytest.mark.asyncio
async def test_set_is_toc_returns_false_for_unknown_page():
    session = AsyncMock()
    repo = PagesRepository(session)
    mock_res = MagicMock()
    mock_res.rowcount = 0
    session.execute.return_value = mock_res

    result = await repo.set_is_toc("b1", 999, True, "editor@example.com")
    assert result is False


@pytest.mark.asyncio
async def test_search_content_pages():
    session = AsyncMock()
    repo = PagesRepository(session)

    mock_count_res = MagicMock()
    mock_count_res.scalar_one.return_value = 1

    mock_row = MagicMock()
    mock_row.book_id = "b1"
    mock_row.page_number = 5
    mock_row.snippet = "مۇھىم تېكىست"
    mock_row.full_text = "مۇھىم تېكىست"
    mock_row.title = "تارىخىي كىتاب"
    mock_row.volume = 1
    mock_row.author = "مۇئەللىپ"
    mock_row.cover_url = "/covers/b1.jpg"
    mock_row.rank = 0.85

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
        hits, total = await repo.search_content_pages("تېكىست", skip=0, limit=20)

    assert total == 1
    assert len(hits) == 1
    assert hits[0]["id"] == "b1_5"
    assert hits[0]["book_id"] == "b1"
    assert hits[0]["book_title"] == "تارىخىي كىتاب"
    assert hits[0]["page_number"] == 5
    assert hits[0]["snippet"] == "مۇھىم تېكىست"
    assert hits[0]["rank"] == 0.85


@pytest.mark.asyncio
async def test_sync_content_page_offset():
    session = AsyncMock()
    repo = PagesRepository(session)
    mock_res = MagicMock()
    mock_res.scalar_one.return_value = 6
    session.execute.side_effect = [mock_res, MagicMock()]

    offset = await repo.sync_content_page_offset("b1")
    assert offset == 6
    assert session.flush.called
