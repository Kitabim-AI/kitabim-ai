import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.db.repositories.base_repository import BaseRepository
from app.db.models import Book


@pytest.mark.asyncio
async def test_base_get():
    session = AsyncMock()
    repo = BaseRepository(session, Book)

    # Mocking sqlalchemy inspect and session.execute
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = Book(id="b1")
    session.execute.return_value = mock_res

    with patch("sqlalchemy.inspect") as mock_inspect:
        # Mocking primary key column for inspect(Book)
        mock_pk = MagicMock()
        mock_inspect.return_value.primary_key = [mock_pk]

        book = await repo.get("b1")
        assert book.id == "b1"
        session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_base_get_all():
    session = AsyncMock()
    repo = BaseRepository(session, Book)

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [Book(id="b1"), Book(id="b2")]
    session.execute.return_value = mock_res

    books = await repo.get_all(skip=0, limit=2, order_by="title")
    assert len(books) == 2
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_base_create():
    session = AsyncMock()
    session.add = MagicMock()
    repo = BaseRepository(session, Book)

    # BaseRepository.create uses self.model(**kwargs)
    # Then session.add(), session.flush(), session.refresh()

    book = await repo.create(title="Title")
    assert book.title == "Title"
    session.add.assert_called_once()
    session.flush.assert_called_once()
    session.refresh.assert_called_once()


@pytest.mark.asyncio
async def test_base_update_one():
    session = AsyncMock()
    repo = BaseRepository(session, Book)

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = Book(id="b1", title="new")
    session.execute.return_value = mock_res

    with patch("sqlalchemy.inspect") as mock_inspect:
        mock_pk = MagicMock()
        mock_inspect.return_value.primary_key = [mock_pk]

        book = await repo.update_one("b1", title="new")
        assert book.title == "new"
        session.execute.assert_called_once()
        session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_base_delete_one():
    session = AsyncMock()
    repo = BaseRepository(session, Book)

    mock_res = MagicMock()
    mock_res.rowcount = 1
    session.execute.return_value = mock_res

    with patch("sqlalchemy.inspect") as mock_inspect:
        mock_pk = MagicMock()
        mock_inspect.return_value.primary_key = [mock_pk]

        res = await repo.delete_one("b1")
        assert res is True
        assert session.flush.called


@pytest.mark.asyncio
async def test_base_count():
    session = AsyncMock()
    repo = BaseRepository(session, Book)

    mock_res = MagicMock()
    mock_res.scalar_one.return_value = 5
    session.execute.return_value = mock_res

    count = await repo.count(status="ready")
    assert count == 5
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_base_exists():
    session = AsyncMock()
    repo = BaseRepository(session, Book)

    mock_res = MagicMock()
    mock_res.scalar_one.return_value = 1
    session.execute.return_value = mock_res

    with patch("sqlalchemy.inspect") as mock_inspect:
        mock_pk = MagicMock()
        mock_inspect.return_value.primary_key = [mock_pk]

        exists = await repo.exists("b1")
        assert exists is True


@pytest.mark.asyncio
async def test_base_update_one_filters_unmapped_columns():
    session = AsyncMock()
    repo = BaseRepository(session, Book)

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = Book(id="b1", title="new")
    session.execute.return_value = mock_res

    with patch("sqlalchemy.inspect") as mock_inspect:
        mock_pk = MagicMock()
        mock_inspect.return_value.primary_key = [mock_pk]

        # Pass an unmapped column like has_history
        book = await repo.update_one(
            "b1", title="new", has_history=True, non_existent_col="foo"
        )
        assert book.title == "new"
        session.execute.assert_called_once()
        # Verify statement passed to session.execute only updated mapped column 'title'
        stmt = session.execute.call_args[0][0]
        params = stmt.compile().params
        assert "title" in params
        assert "has_history" not in params
        assert "non_existent_col" not in params


@pytest.mark.asyncio
async def test_base_update_one_no_op_when_only_unmapped_columns():
    session = AsyncMock()
    repo = BaseRepository(session, Book)

    with patch.object(repo, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = Book(id="b1", title="existing")

        book = await repo.update_one("b1", has_history=True, non_existent_col="foo")
        assert book.title == "existing"
        mock_get.assert_awaited_once_with("b1")
        session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_base_create_filters_unmapped_columns():
    session = AsyncMock()
    session.add = MagicMock()
    repo = BaseRepository(session, Book)

    # Book constructor would fail if invalid keyword args are passed
    book = await repo.create(
        id="b1", title="Title", has_history=True, non_existent_col="foo"
    )
    assert book.id == "b1"
    assert book.title == "Title"
    assert not hasattr(book, "non_existent_col")
    session.add.assert_called_once()
