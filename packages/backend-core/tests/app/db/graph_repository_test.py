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
        assert "e.name IN $entity_names" in call_args[0]
        assert (
            "any(alt IN COALESCE(e.aliases, []) WHERE alt IN $entity_names)"
            in call_args[0]
        )
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
        assert "e.name IN $entity_names" in call_args[0]
        assert (
            "any(alt IN COALESCE(e.aliases, []) WHERE alt IN $entity_names)"
            in call_args[0]
        )
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


@pytest.mark.asyncio
async def test_graph_repository_merge_entities_success():
    mock_result_check = AsyncMock()
    mock_result_check.data.return_value = [
        {"name": "KeepName", "aliases": ["AltKeep"]},
        {"name": "RemoveName", "aliases": ["AltRemove"]},
    ]

    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.run.side_effect = [
        mock_result_check,
        AsyncMock(),
    ]  # First checks, second merges

    mock_driver = MagicMock()
    mock_driver.session.return_value = mock_session

    with patch(
        "app.db.repositories.graph_repository.AsyncGraphDatabase.driver",
        return_value=mock_driver,
    ):
        repo = GraphRepository()
        success = await repo.merge_entities("KeepName", "RemoveName")
        assert success is True
        assert mock_session.run.call_count == 2

        # Verify the second call received the combined, deduplicated aliases
        second_call_kwargs = mock_session.run.call_args_list[1][1]
        assert "combined_aliases" in second_call_kwargs
        assert second_call_kwargs["combined_aliases"] == [
            "AltKeep",
            "RemoveName",
            "AltRemove",
        ]


@pytest.mark.asyncio
async def test_graph_repository_merge_entities_missing():
    mock_result_check = AsyncMock()
    mock_result_check.data.return_value = [{"name": "KeepName"}]  # Missing RemoveName

    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.run.return_value = mock_result_check

    mock_driver = MagicMock()
    mock_driver.session.return_value = mock_session

    with patch(
        "app.db.repositories.graph_repository.AsyncGraphDatabase.driver",
        return_value=mock_driver,
    ):
        repo = GraphRepository()
        with pytest.raises(ValueError) as excinfo:
            await repo.merge_entities("KeepName", "RemoveName")
        assert "Duplicate entity to remove 'RemoveName' does not exist." in str(
            excinfo.value
        )


@pytest.mark.asyncio
async def test_graph_repository_query_paths_empty():
    mock_driver = MagicMock()
    with patch(
        "app.db.repositories.graph_repository.AsyncGraphDatabase.driver",
        return_value=mock_driver,
    ):
        repo = GraphRepository()
        # Less than 2 entity names should return empty list directly without querying DB
        records = await repo.query_paths(["A"])
        assert records == []
        assert not mock_driver.session.called


@pytest.mark.asyncio
async def test_graph_repository_query_paths_success():
    mock_result = AsyncMock()
    mock_result.data.return_value = [{"source": "A", "rel": "SON_OF", "target": "B"}]
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
        records = await repo.query_paths(
            ["A", "B"], book_ids=["bid-1"], familial_only=True
        )

        assert mock_session.run.called
        call_args = mock_session.run.call_args[0]
        call_kwargs = mock_session.run.call_args[1]
        assert "MATCH p = (a:Entity)-[r:RELATED_TO*1..4]-(b:Entity)" in call_args[0]
        assert (
            "all(rel in relationships(p) WHERE rel.type IN $familial_rels)"
            in call_args[0]
        )
        assert call_kwargs["entity_names"] == ["A", "B"]
        assert call_kwargs["book_ids"] == ["bid-1"]
        assert "familial_rels" in call_kwargs
        assert records == [{"source": "A", "rel": "SON_OF", "target": "B"}]


@pytest.mark.asyncio
async def test_graph_repository_delete_relationship_success():
    mock_result = AsyncMock()
    mock_result.data.return_value = [{"deleted": 2}]
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
        success = await repo.delete_relationship("A", "B", "SON_OF")

        assert success is True
        assert mock_session.run.called
        call_args = mock_session.run.call_args[0]
        call_kwargs = mock_session.run.call_args[1]
        assert "DELETE r" in call_args[0]
        assert "RELATED_TO {type: $rel_type}" in call_args[0]
        assert call_kwargs["source_name"] == "A"
        assert call_kwargs["target_name"] == "B"
        assert call_kwargs["rel_type"] == "SON_OF"


@pytest.mark.asyncio
async def test_graph_repository_delete_relationship_not_found():
    mock_result = AsyncMock()
    mock_result.data.return_value = [{"deleted": 0}]
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
        with pytest.raises(ValueError) as excinfo:
            await repo.delete_relationship("A", "B", "SON_OF")
        assert "No 'SON_OF' relationship found between 'A' and 'B'." in str(
            excinfo.value
        )


@pytest.mark.asyncio
async def test_graph_repository_rename_entity_success():
    mock_result_check = AsyncMock()
    mock_result_check.data.return_value = [{"name": "OldName"}]

    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.run.side_effect = [
        mock_result_check,
        AsyncMock(),
    ]

    mock_driver = MagicMock()
    mock_driver.session.return_value = mock_session

    with patch(
        "app.db.repositories.graph_repository.AsyncGraphDatabase.driver",
        return_value=mock_driver,
    ):
        repo = GraphRepository()
        success = await repo.rename_entity("OldName", "NewName")
        assert success is True
        assert mock_session.run.call_count == 2

        second_call_args = mock_session.run.call_args_list[1][0]
        second_call_kwargs = mock_session.run.call_args_list[1][1]
        assert "SET e.name = $new" in second_call_args[0]
        assert second_call_kwargs["old"] == "OldName"
        assert second_call_kwargs["new"] == "NewName"


@pytest.mark.asyncio
async def test_graph_repository_rename_entity_missing():
    mock_result_check = AsyncMock()
    mock_result_check.data.return_value = []

    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.run.return_value = mock_result_check

    mock_driver = MagicMock()
    mock_driver.session.return_value = mock_session

    with patch(
        "app.db.repositories.graph_repository.AsyncGraphDatabase.driver",
        return_value=mock_driver,
    ):
        repo = GraphRepository()
        with pytest.raises(ValueError) as excinfo:
            await repo.rename_entity("OldName", "NewName")
        assert "Entity to rename 'OldName' does not exist." in str(excinfo.value)


@pytest.mark.asyncio
async def test_graph_repository_rename_entity_already_exists():
    mock_result_check = AsyncMock()
    mock_result_check.data.return_value = [
        {"name": "OldName"},
        {"name": "NewName"},
    ]

    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.run.return_value = mock_result_check

    mock_driver = MagicMock()
    mock_driver.session.return_value = mock_session

    with patch(
        "app.db.repositories.graph_repository.AsyncGraphDatabase.driver",
        return_value=mock_driver,
    ):
        repo = GraphRepository()
        with pytest.raises(ValueError) as excinfo:
            await repo.rename_entity("OldName", "NewName")
        assert "An entity with the name 'NewName' already exists." in str(excinfo.value)


@pytest.mark.asyncio
async def test_graph_repository_rename_entity_identical():
    mock_driver = MagicMock()
    with patch(
        "app.db.repositories.graph_repository.AsyncGraphDatabase.driver",
        return_value=mock_driver,
    ):
        repo = GraphRepository()
        success = await repo.rename_entity("SameName", "SameName")
        assert success is True
        assert not mock_driver.session.called
