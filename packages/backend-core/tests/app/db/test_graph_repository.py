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

        assert mock_session.run.call_count == 4
        await repo.close()
        assert mock_driver.close.called



@pytest.mark.asyncio
async def test_graph_repository_upsert_book():
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_driver = MagicMock()
    mock_driver.session.return_value = mock_session

    with patch("app.db.repositories.graph.AsyncGraphDatabase.driver", return_value=mock_driver):
        repo = GraphRepository()
        await repo.upsert_book("b1", "Title", "Author", "Summary")

        assert mock_session.run.called
        call_args = mock_session.run.call_args[0]
        call_kwargs = mock_session.run.call_args[1]
        assert "MERGE (b:Book" in call_args[0]
        assert call_kwargs["book_id"] == "b1"
        assert call_kwargs["title"] == "Title"
        assert call_kwargs["author"] == "Author"
        assert call_kwargs["summary"] == "Summary"


@pytest.mark.asyncio
async def test_graph_repository_upsert_author():
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_driver = MagicMock()
    mock_driver.session.return_value = mock_session

    with patch("app.db.repositories.graph.AsyncGraphDatabase.driver", return_value=mock_driver):
        repo = GraphRepository()
        await repo.upsert_author("Author Name", "Bio text")

        assert mock_session.run.called
        call_args = mock_session.run.call_args[0]
        call_kwargs = mock_session.run.call_args[1]
        assert "MERGE (a:Author" in call_args[0]
        assert call_kwargs["name"] == "Author Name"
        assert call_kwargs["bio"] == "Bio text"


@pytest.mark.asyncio
async def test_graph_repository_upsert_chunk():
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_driver = MagicMock()
    mock_driver.session.return_value = mock_session

    with patch("app.db.repositories.graph.AsyncGraphDatabase.driver", return_value=mock_driver):
        repo = GraphRepository()
        await repo.upsert_chunk(123, "b1", 5, "Preview text")

        assert mock_session.run.called
        call_args = mock_session.run.call_args[0]
        call_kwargs = mock_session.run.call_args[1]
        assert "MERGE (c:Chunk" in call_args[0]
        assert call_kwargs["chunk_id"] == 123
        assert call_kwargs["book_id"] == "b1"
        assert call_kwargs["page_number"] == 5
        assert call_kwargs["text_preview"] == "Preview text"


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
async def test_graph_repository_relationships():
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_driver = MagicMock()
    mock_driver.session.return_value = mock_session

    with patch("app.db.repositories.graph.AsyncGraphDatabase.driver", return_value=mock_driver):
        repo = GraphRepository()

        # Connect author and book
        await repo.connect_author_book("Author Name", "b1")
        assert mock_session.run.called
        assert "[:WROTE]" in mock_session.run.call_args[0][0]

        # Connect book and chunk
        await repo.connect_book_chunk("b1", 123)
        assert mock_session.run.called
        assert "[:HAS_CHUNK]" in mock_session.run.call_args[0][0]

        # Connect chunk and entity
        await repo.connect_chunk_entity(123, "Entity Name")
        assert mock_session.run.called
        assert "[:MENTIONS]" in mock_session.run.call_args[0][0]

        # Connect entities
        await repo.connect_entities("Src", "RELATED", "Tgt")
        assert mock_session.run.called
        assert "RELATED_TO" in mock_session.run.call_args[0][0]

        # Connect book to entity
        await repo.connect_book_to_entity("b1", "Tgt", "HAS_THEME")
        assert mock_session.run.called
        assert "RELATED_TO" in mock_session.run.call_args[0][0]


@pytest.mark.asyncio
async def test_graph_repository_clear_book_graph():
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_driver = MagicMock()
    mock_driver.session.return_value = mock_session

    with patch("app.db.repositories.graph.AsyncGraphDatabase.driver", return_value=mock_driver):
        repo = GraphRepository()
        await repo.clear_book_graph("b1")

        assert mock_session.run.called
        call_args = mock_session.run.call_args[0]
        assert "DETACH DELETE c" in call_args[0]


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

