import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.db.repositories.graph import GraphRepository


@pytest.mark.asyncio
async def test_graph_repository_init_constraints():
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_driver = MagicMock()
    mock_driver.close = AsyncMock()
    mock_driver.session.return_value = mock_session

    with patch("app.db.repositories.graph.AsyncGraphDatabase.driver", return_value=mock_driver):
        repo = GraphRepository()
        await repo.init_constraints()

        assert mock_session.run.call_count == 1
        await repo.close()
        assert mock_driver.close.called


@pytest.mark.asyncio
async def test_graph_repository_upsert_entity():
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_driver = MagicMock()
    mock_driver.session.return_value = mock_session

    with patch("app.db.repositories.graph.AsyncGraphDatabase.driver", return_value=mock_driver):
        repo = GraphRepository()
        await repo.upsert_entity("Entity Name", "Person", "Sultan")

        assert mock_session.run.called
        call_args = mock_session.run.call_args[0]
        call_kwargs = mock_session.run.call_args[1]
        assert "MERGE (e:Entity" in call_args[0]
        assert call_kwargs["name"] == "Entity Name"
        assert call_kwargs["type"] == "Person"
        assert call_kwargs["subtype"] == "Sultan"



@pytest.mark.asyncio
async def test_graph_repository_query_subgraph():
    mock_result = AsyncMock()
    mock_result.data.return_value = [{"source": "A", "rel": "KNOWS", "target": "B"}]
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.run.return_value = mock_result
    mock_driver = MagicMock()
    mock_driver.session.return_value = mock_session

    with patch("app.db.repositories.graph.AsyncGraphDatabase.driver", return_value=mock_driver):
        repo = GraphRepository()
        records = await repo.query_subgraph(["A", "B"])

        assert mock_session.run.called
        call_args = mock_session.run.call_args[0]
        call_kwargs = mock_session.run.call_args[1]
        assert "WHERE e.name IN $entity_names" in call_args[0]
        assert call_kwargs["entity_names"] == ["A", "B"]
        assert records == [{"source": "A", "rel": "KNOWS", "target": "B"}]


@pytest.mark.asyncio
async def test_graph_repository_bulk_ops():
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_driver = MagicMock()
    mock_driver.session.return_value = mock_session

    with patch("app.db.repositories.graph.AsyncGraphDatabase.driver", return_value=mock_driver):
        repo = GraphRepository()

        # 1. Test upsert_entities_bulk
        entities = [{"name": "E1", "type": "Person", "subtype": None}]
        await repo.upsert_entities_bulk(entities)
        assert mock_session.run.called
        call_args = mock_session.run.call_args[0]
        call_kwargs = mock_session.run.call_args[1]
        assert "UNWIND $entities_data" in call_args[0]
        assert call_kwargs["entities_data"] == entities

        # 2. Test connect_entities_bulk
        relations = [{"source_name": "E1", "rel_type": "KNOWS", "target_name": "E2"}]
        await repo.connect_entities_bulk(relations)
        assert mock_session.run.called
        call_args = mock_session.run.call_args[0]
        call_kwargs = mock_session.run.call_args[1]
        assert "UNWIND $relations_data" in call_args[0]
        assert call_kwargs["relations_data"] == relations
