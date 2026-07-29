import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from services.worker.jobs.knowledge_graph_job import knowledge_graph_job
from app.db.models import Book, Chunk


def _config_get_value(overrides=None):
    base = {
        "knowledge_graph_enabled": "true",
        "gemini_kg_extraction_model": "gemini-3.1-flash-lite",
        "kg_max_parallel_chunks": "5",
        "kg_chunk_batch_size": "5",
    }
    if overrides:
        base.update(overrides)

    async def _get_value(key, default=None):
        return base.get(key, default)

    return _get_value


@pytest.mark.asyncio
async def test_knowledge_graph_job_invalid_scope_raises():
    with pytest.raises(ValueError):
        await knowledge_graph_job({}, "book-123", "unknown-scope")


@pytest.mark.asyncio
async def test_knowledge_graph_job_disabled():
    ctx = {}
    book_id = "book-123"

    with patch("app.db.session.async_session_factory") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        with patch(
            "services.worker.jobs.knowledge_graph_job.SystemConfigsRepository.get_value",
            new_callable=AsyncMock,
        ) as mock_get_value:
            mock_get_value.return_value = "false"

            await knowledge_graph_job(ctx, book_id, "nonfiction")

            mock_get_value.assert_any_call("knowledge_graph_enabled", "false")
            mock_session.execute.assert_called()
            mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_knowledge_graph_job_book_not_found():
    ctx = {}
    book_id = "book-123"

    with patch("app.db.session.async_session_factory") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        with patch(
            "services.worker.jobs.knowledge_graph_job.SystemConfigsRepository.get_value",
            side_effect=_config_get_value(),
        ):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_session.execute.return_value = mock_result

            await knowledge_graph_job(ctx, book_id, "nonfiction")

            mock_session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_knowledge_graph_job_no_chunks():
    ctx = {}
    book_id = "book-123"

    with patch("app.db.session.async_session_factory") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        with patch(
            "services.worker.jobs.knowledge_graph_job.SystemConfigsRepository.get_value",
            side_effect=_config_get_value(),
        ):
            mock_book = MagicMock(spec=Book)
            mock_book.id = book_id

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_book
            mock_result.scalars().all.return_value = []
            mock_session.execute.return_value = mock_result

            await knowledge_graph_job(ctx, book_id, "nonfiction")

            mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_knowledge_graph_job_success_nonfiction():
    ctx = {}
    book_id = "book-123"

    with (
        patch("app.db.session.async_session_factory") as mock_session_factory,
        patch("services.worker.jobs.knowledge_graph_job.settings") as mock_settings,
        patch(
            "services.worker.jobs.knowledge_graph_job.GraphRepository"
        ) as mock_graph_repo_class,
        patch("services.worker.jobs.knowledge_graph_job.genai") as mock_genai_module,
        patch(
            "services.worker.jobs.knowledge_graph_job.GraphResolutionQueueRepository"
        ) as mock_queue_repo_class,
    ):
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        with patch(
            "services.worker.jobs.knowledge_graph_job.SystemConfigsRepository.get_value",
            side_effect=_config_get_value(),
        ):
            mock_settings.gemini_api_key = "fake-key"

            mock_book = MagicMock(spec=Book)
            mock_book.id = book_id
            mock_book.title = "Test Book"
            mock_book.author = "Test Author"

            mock_chunk = MagicMock(spec=Chunk)
            mock_chunk.id = "chunk-1"
            mock_chunk.page_number = 1
            mock_chunk.chunk_index = 0
            mock_chunk.text = "This is a test chunk text."

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_book
            mock_result.scalars().all.return_value = [mock_chunk]
            mock_session.execute.return_value = mock_result

            mock_graph_repo = AsyncMock()
            mock_graph_repo_class.return_value = mock_graph_repo

            mock_queue_repo = AsyncMock()
            mock_queue_repo_class.return_value = mock_queue_repo

            mock_client = MagicMock()
            mock_genai_module.Client.return_value = mock_client

            mock_response = MagicMock()
            mock_response.text = (
                '{"entities": ['
                '{"local_id": "e1", "name": "Test Entity", "type": "Person", "subtype": "Historical character"},'
                '{"local_id": "e2", "name": "Other Entity", "type": "Concept"}'
                '], "relations": ['
                '{"source_entity": "e1", "relation_type": "FRIEND_OF", "target_entity": "e2"}'
                "]}"
            )
            mock_client.aio.models.generate_content = AsyncMock(
                return_value=mock_response
            )

            await knowledge_graph_job(ctx, book_id, "nonfiction")

            mock_graph_repo.init_constraints.assert_called_once()

            entities = mock_graph_repo.upsert_entities_bulk.call_args[0][0]
            assert len(entities) == 2
            by_name = {e["canonical_name"]: e for e in entities}
            assert set(by_name) == {"Test Entity", "Other Entity"}
            for e in entities:
                assert e["scope"] == "nonfiction"
                assert e["book_id"] is None
                assert e["resolution_status"] == "unresolved"
                assert e["aliases"] == [e["canonical_name"]]
                assert e["id"]  # a fresh uuid was assigned

            relations = mock_graph_repo.connect_entities_bulk.call_args[0][0]
            assert len(relations) == 1
            rel = relations[0]
            assert rel["rel_type"] == "FRIEND_OF"
            assert rel["book_id"] == book_id
            assert rel["source_id"] == by_name["Test Entity"]["id"]
            assert rel["target_id"] == by_name["Other Entity"]["id"]
            assert rel["chunk_refs"] == [f"{book_id}:1:0"]

            # Every extracted entity gets queued for the global resolution pass
            queue_rows = mock_queue_repo.bulk_enqueue.call_args[0][0]
            assert len(queue_rows) == 2
            assert {r["entity_id"] for r in queue_rows} == {e["id"] for e in entities}
            assert all(
                r["scope"] == "nonfiction" and r["book_id"] is None for r in queue_rows
            )

            mock_graph_repo.close.assert_called_once()
            mock_session.commit.assert_called()


@pytest.mark.asyncio
async def test_knowledge_graph_job_success_fiction_stamps_book_id():
    ctx = {}
    book_id = "book-456"

    with (
        patch("app.db.session.async_session_factory") as mock_session_factory,
        patch("services.worker.jobs.knowledge_graph_job.settings") as mock_settings,
        patch(
            "services.worker.jobs.knowledge_graph_job.GraphRepository"
        ) as mock_graph_repo_class,
        patch("services.worker.jobs.knowledge_graph_job.genai") as mock_genai_module,
        patch(
            "services.worker.jobs.knowledge_graph_job.GraphResolutionQueueRepository"
        ) as mock_queue_repo_class,
    ):
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        with patch(
            "services.worker.jobs.knowledge_graph_job.SystemConfigsRepository.get_value",
            side_effect=_config_get_value(),
        ):
            mock_settings.gemini_api_key = "fake-key"

            mock_book = MagicMock(spec=Book)
            mock_book.id = book_id
            mock_book.title = "Fiction Book"
            mock_book.author = "Author"

            mock_chunk = MagicMock(spec=Chunk)
            mock_chunk.id = "chunk-1"
            mock_chunk.page_number = 1
            mock_chunk.chunk_index = 0
            mock_chunk.text = "Once upon a time."

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_book
            mock_result.scalars().all.return_value = [mock_chunk]
            mock_session.execute.return_value = mock_result

            mock_graph_repo = AsyncMock()
            mock_graph_repo_class.return_value = mock_graph_repo
            mock_queue_repo = AsyncMock()
            mock_queue_repo_class.return_value = mock_queue_repo

            mock_client = MagicMock()
            mock_genai_module.Client.return_value = mock_client
            mock_response = MagicMock()
            mock_response.text = '{"entities": [{"local_id": "e1", "name": "Hero", "type": "Person"}], "relations": []}'
            mock_client.aio.models.generate_content = AsyncMock(
                return_value=mock_response
            )

            await knowledge_graph_job(ctx, book_id, "fiction")

            entities = mock_graph_repo.upsert_entities_bulk.call_args[0][0]
            assert len(entities) == 1
            assert entities[0]["scope"] == "fiction"
            assert entities[0]["book_id"] == book_id

            queue_rows = mock_queue_repo.bulk_enqueue.call_args[0][0]
            assert queue_rows[0]["scope"] == "fiction"
            assert queue_rows[0]["book_id"] == book_id


@pytest.mark.asyncio
async def test_knowledge_graph_job_relation_with_unresolvable_local_id_is_skipped():
    ctx = {}
    book_id = "book-789"

    with (
        patch("app.db.session.async_session_factory") as mock_session_factory,
        patch("services.worker.jobs.knowledge_graph_job.settings") as mock_settings,
        patch(
            "services.worker.jobs.knowledge_graph_job.GraphRepository"
        ) as mock_graph_repo_class,
        patch("services.worker.jobs.knowledge_graph_job.genai") as mock_genai_module,
        patch(
            "services.worker.jobs.knowledge_graph_job.GraphResolutionQueueRepository"
        ) as mock_queue_repo_class,
    ):
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        with patch(
            "services.worker.jobs.knowledge_graph_job.SystemConfigsRepository.get_value",
            side_effect=_config_get_value(),
        ):
            mock_settings.gemini_api_key = "fake-key"

            mock_book = MagicMock(spec=Book)
            mock_book.id = book_id
            mock_book.title = "Book"
            mock_book.author = "Author"

            mock_chunk = MagicMock(spec=Chunk)
            mock_chunk.id = "chunk-1"
            mock_chunk.page_number = 1
            mock_chunk.chunk_index = 0
            mock_chunk.text = "Text."

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_book
            mock_result.scalars().all.return_value = [mock_chunk]
            mock_session.execute.return_value = mock_result

            mock_graph_repo = AsyncMock()
            mock_graph_repo_class.return_value = mock_graph_repo
            mock_queue_repo_class.return_value = AsyncMock()

            mock_client = MagicMock()
            mock_genai_module.Client.return_value = mock_client
            mock_response = MagicMock()
            # "e2" is referenced by the relation but never emitted as an entity.
            mock_response.text = (
                '{"entities": [{"local_id": "e1", "name": "Solo Entity", "type": "Person"}], '
                '"relations": [{"source_entity": "e1", "relation_type": "KNOWS", "target_entity": "e2"}]}'
            )
            mock_client.aio.models.generate_content = AsyncMock(
                return_value=mock_response
            )

            await knowledge_graph_job(ctx, book_id, "nonfiction")

            entities = mock_graph_repo.upsert_entities_bulk.call_args[0][0]
            assert len(entities) == 1
            mock_graph_repo.connect_entities_bulk.assert_not_called()


@pytest.mark.asyncio
async def test_knowledge_graph_job_child_of_carries_parent_role():
    ctx = {}
    book_id = "book-321"

    with (
        patch("app.db.session.async_session_factory") as mock_session_factory,
        patch("services.worker.jobs.knowledge_graph_job.settings") as mock_settings,
        patch(
            "services.worker.jobs.knowledge_graph_job.GraphRepository"
        ) as mock_graph_repo_class,
        patch("services.worker.jobs.knowledge_graph_job.genai") as mock_genai_module,
        patch(
            "services.worker.jobs.knowledge_graph_job.GraphResolutionQueueRepository"
        ) as mock_queue_repo_class,
    ):
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        with patch(
            "services.worker.jobs.knowledge_graph_job.SystemConfigsRepository.get_value",
            side_effect=_config_get_value(),
        ):
            mock_settings.gemini_api_key = "fake-key"

            mock_book = MagicMock(spec=Book)
            mock_book.id = book_id
            mock_book.title = "Book"
            mock_book.author = "Author"

            mock_chunk = MagicMock(spec=Chunk)
            mock_chunk.id = "chunk-1"
            mock_chunk.page_number = 3
            mock_chunk.chunk_index = 1
            mock_chunk.text = "Text."

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_book
            mock_result.scalars().all.return_value = [mock_chunk]
            mock_session.execute.return_value = mock_result

            mock_graph_repo = AsyncMock()
            mock_graph_repo_class.return_value = mock_graph_repo
            mock_queue_repo_class.return_value = AsyncMock()

            mock_client = MagicMock()
            mock_genai_module.Client.return_value = mock_client
            mock_response = MagicMock()
            mock_response.text = (
                '{"entities": ['
                '{"local_id": "e1", "name": "Child", "type": "Person"},'
                '{"local_id": "e2", "name": "Father", "type": "Person"}'
                '], "relations": ['
                '{"source_entity": "e1", "relation_type": "CHILD_OF", "target_entity": "e2", "parent_role": "father"}'
                "]}"
            )
            mock_client.aio.models.generate_content = AsyncMock(
                return_value=mock_response
            )

            await knowledge_graph_job(ctx, book_id, "nonfiction")

            relations = mock_graph_repo.connect_entities_bulk.call_args[0][0]
            assert len(relations) == 1
            assert relations[0]["parent_role"] == "father"
            assert relations[0]["chunk_refs"] == [f"{book_id}:3:1"]


@pytest.mark.asyncio
async def test_knowledge_graph_job_failure():
    ctx = {}
    book_id = "book-123"

    with (
        patch("app.db.session.async_session_factory") as mock_session_factory,
        patch("services.worker.jobs.knowledge_graph_job.settings") as mock_settings,
        patch(
            "services.worker.jobs.knowledge_graph_job.GraphRepository"
        ) as mock_graph_repo_class,
    ):
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        with patch(
            "services.worker.jobs.knowledge_graph_job.SystemConfigsRepository.get_value",
            side_effect=_config_get_value(),
        ):
            mock_settings.gemini_api_key = "fake-key"

            mock_book = MagicMock(spec=Book)
            mock_book.id = book_id

            mock_chunk = MagicMock(spec=Chunk)
            mock_chunk.id = "chunk-1"
            mock_chunk.page_number = 1
            mock_chunk.chunk_index = 0
            mock_chunk.text = "This is a test chunk text."

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_book
            mock_result.scalars().all.return_value = [mock_chunk]
            mock_session.execute.return_value = mock_result

            mock_graph_repo = AsyncMock()
            mock_graph_repo.init_constraints.side_effect = Exception(
                "Graph connection failure"
            )
            mock_graph_repo_class.return_value = mock_graph_repo

            with pytest.raises(Exception):
                await knowledge_graph_job(ctx, book_id, "nonfiction")

            mock_graph_repo.close.assert_called_once()
            mock_session.commit.assert_called()
