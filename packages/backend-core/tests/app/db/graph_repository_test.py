import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from app.db.repositories.graph_repository import GraphRepository


@pytest_asyncio.fixture(autouse=True)
async def cleanup_graph_driver():
    """Ensure class-level graph driver is clean before and after each test."""
    GraphRepository._driver = None
    yield
    await GraphRepository.close_driver()


@pytest.mark.asyncio
async def test_graph_repository_init_constraints():
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_driver = MagicMock()
    mock_driver.close = AsyncMock()
    mock_driver.session.return_value = mock_session

    with patch(
        "app.db.repositories.graph_repository.AsyncGraphDatabase.driver",
        return_value=mock_driver,
    ):
        repo = GraphRepository()
        await repo.init_constraints()

        assert mock_session.run.call_count == 1
        await GraphRepository.close_driver()
        assert mock_driver.close.called


@pytest.mark.asyncio
async def test_graph_repository_query_subgraph():
    mock_result = AsyncMock()
    mock_result.data.return_value = [{"source": "A", "rel": "KNOWS", "target": "B"}]
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.run.return_value = mock_result
    mock_driver = MagicMock()
    mock_driver.session.return_value = mock_session

    with patch(
        "app.db.repositories.graph_repository.AsyncGraphDatabase.driver",
        return_value=mock_driver,
    ):
        repo = GraphRepository()
        records = await repo.query_subgraph(["A", "B"])

        assert mock_session.run.called
        call_args = mock_session.run.call_args[0]
        call_kwargs = mock_session.run.call_args[1]
        assert "(e.name IN $entity_names OR n.name IN $entity_names)" in call_args[0]
        assert "r.book_id IN $book_ids" in call_args[0]
        assert call_kwargs["entity_names"] == ["A", "B"]
        assert call_kwargs["book_ids"] is None
        assert records == [{"source": "A", "rel": "KNOWS", "target": "B"}]


@pytest.mark.asyncio
async def test_graph_repository_query_subgraph_with_book_ids():
    mock_result = AsyncMock()
    mock_result.data.return_value = [{"source": "A", "rel": "KNOWS", "target": "B"}]
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.run.return_value = mock_result
    mock_driver = MagicMock()
    mock_driver.session.return_value = mock_session

    with patch(
        "app.db.repositories.graph_repository.AsyncGraphDatabase.driver",
        return_value=mock_driver,
    ):
        repo = GraphRepository()
        records = await repo.query_subgraph(["A", "B"], book_ids=["bid-1", "bid-2"])

        assert mock_session.run.called
        call_args = mock_session.run.call_args[0]
        call_kwargs = mock_session.run.call_args[1]
        assert "(e.name IN $entity_names OR n.name IN $entity_names)" in call_args[0]
        assert "r.book_id IN $book_ids" in call_args[0]
        assert call_kwargs["entity_names"] == ["A", "B"]
        assert call_kwargs["book_ids"] == ["bid-1", "bid-2"]
        assert records == [{"source": "A", "rel": "KNOWS", "target": "B"}]


@pytest.mark.asyncio
async def test_graph_repository_bulk_ops():
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_driver = MagicMock()
    mock_driver.session.return_value = mock_session

    with patch(
        "app.db.repositories.graph_repository.AsyncGraphDatabase.driver",
        return_value=mock_driver,
    ):
        repo = GraphRepository()

        # 1. Test upsert_entities_bulk
        entities = [{"name": "E1", "type": "Person", "subtype": None}]
        await repo.upsert_entities_bulk(entities)
        assert mock_session.run.called
        call_args = mock_session.run.call_args[0]
        call_kwargs = mock_session.run.call_args[1]
        assert "UNWIND $entities_data" in call_args[0]
        expected_entities = [
            {
                "name": "E1",
                "type": "Person",
                "subtype": None,
                "year_hijri": None,
                "year_gregorian": None,
                "century_gregorian": None,
            }
        ]
        assert call_kwargs["entities_data"] == expected_entities

        # 2. Test connect_entities_bulk
        relations = [{"source_name": "E1", "rel_type": "KNOWS", "target_name": "E2"}]
        await repo.connect_entities_bulk(relations)
        assert mock_session.run.called
        call_args = mock_session.run.call_args[0]
        call_kwargs = mock_session.run.call_args[1]
        assert "UNWIND $relations_data" in call_args[0]
        expected_relations = [
            {
                "source_name": "E1",
                "rel_type": "KNOWS",
                "target_name": "E2",
                "book_id": None,
                "year_hijri": None,
                "year_gregorian": None,
                "century_gregorian": None,
            }
        ]
        assert call_kwargs["relations_data"] == expected_relations
