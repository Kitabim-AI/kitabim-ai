import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from services.worker.jobs.knowledge_graph_job import knowledge_graph_job
from app.db.models import Book, Chunk


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

            await knowledge_graph_job(ctx, book_id)

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
            new_callable=AsyncMock,
        ) as mock_get_value:
            mock_get_value.side_effect = lambda key, default=None: {
                "knowledge_graph_enabled": "true",
                "gemini_chat_model": "gemini-2.0-flash-lite",
                "kg_max_parallel_chunks": "5",
                "kg_chunk_batch_size": "5",
            }.get(key, default)

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_session.execute.return_value = mock_result

            await knowledge_graph_job(ctx, book_id)

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
            new_callable=AsyncMock,
        ) as mock_get_value:
            mock_get_value.side_effect = lambda key, default=None: {
                "knowledge_graph_enabled": "true",
                "gemini_chat_model": "gemini-2.0-flash-lite",
                "kg_max_parallel_chunks": "5",
                "kg_chunk_batch_size": "5",
            }.get(key, default)

            mock_book = MagicMock(spec=Book)
            mock_book.id = book_id

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_book
            mock_result.scalars().all.return_value = []
            mock_session.execute.return_value = mock_result

            await knowledge_graph_job(ctx, book_id)

            mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_knowledge_graph_job_success():
    ctx = {}
    book_id = "book-123"

    with (
        patch("app.db.session.async_session_factory") as mock_session_factory,
        patch("services.worker.jobs.knowledge_graph_job.settings") as mock_settings,
        patch(
            "services.worker.jobs.knowledge_graph_job.GraphRepository"
        ) as mock_graph_repo_class,
        patch("services.worker.jobs.knowledge_graph_job.genai") as mock_genai_module,
    ):
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        with patch(
            "services.worker.jobs.knowledge_graph_job.SystemConfigsRepository.get_value",
            new_callable=AsyncMock,
        ) as mock_get_value:
            mock_get_value.side_effect = lambda key, default=None: {
                "knowledge_graph_enabled": "true",
                "gemini_chat_model": "gemini-2.0-flash-lite",
                "kg_max_parallel_chunks": "5",
                "kg_chunk_batch_size": "5",
                "fictional_categories": "رومان, داستان-رومان, novel",
            }.get(key, default)

            mock_settings.gemini_api_key = "fake-key"

            mock_book = MagicMock(spec=Book)
            mock_book.id = book_id
            mock_book.title = "Test Book"
            mock_book.author = "Test Author"
            mock_book.categories = ["تارىخ"]  # Non-fictional category

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

            mock_client = MagicMock()
            mock_genai_module.Client.return_value = mock_client

            mock_response = MagicMock()
            mock_response.text = '{"entities": [{"name": "Test Entity", "type": "Person", "subtype": "Historical character"}], "relations": [{"source_entity": "Test Entity", "relation_type": "FRIEND_OF", "target_entity": "Other Entity"}]}'
            mock_client.aio.models.generate_content = AsyncMock(
                return_value=mock_response
            )

            await knowledge_graph_job(ctx, book_id)

            mock_graph_repo.init_constraints.assert_called_once()
            mock_graph_repo.upsert_entities_bulk.assert_called_once_with(
                [
                    {
                        "name": "Test Entity",
                        "type": "Person",
                        "subtype": "Historical character",
                    },
                    {
                        "name": "Other Entity",
                        "type": "Concept",
                        "subtype": "Auto-extracted from relation",
                    },
                ]
            )
            mock_graph_repo.connect_entities_bulk.assert_called_once_with(
                [
                    {
                        "source_name": "Test Entity",
                        "rel_type": "FRIEND_OF",
                        "target_name": "Other Entity",
                        "book_id": book_id,
                    }
                ]
            )
            mock_graph_repo.close.assert_called_once()

            mock_session.commit.assert_called()


@pytest.mark.asyncio
async def test_knowledge_graph_job_fictional_namespaced():
    ctx = {}
    book_id = "book-123"

    with (
        patch("app.db.session.async_session_factory") as mock_session_factory,
        patch("services.worker.jobs.knowledge_graph_job.settings") as mock_settings,
        patch(
            "services.worker.jobs.knowledge_graph_job.GraphRepository"
        ) as mock_graph_repo_class,
        patch("services.worker.jobs.knowledge_graph_job.genai") as mock_genai_module,
    ):
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        with patch(
            "services.worker.jobs.knowledge_graph_job.SystemConfigsRepository.get_value",
            new_callable=AsyncMock,
        ) as mock_get_value:
            mock_get_value.side_effect = lambda key, default=None: {
                "knowledge_graph_enabled": "true",
                "gemini_chat_model": "gemini-2.0-flash-lite",
                "kg_max_parallel_chunks": "5",
                "kg_chunk_batch_size": "5",
                "fictional_categories": "رومان, داستان-رومان, novel",
            }.get(key, default)

            mock_settings.gemini_api_key = "fake-key"

            mock_book = MagicMock(spec=Book)
            mock_book.id = book_id
            mock_book.title = "Test Book-1"  # Title with volume suffix
            mock_book.author = "Test Author"
            mock_book.categories = ["رومان"]  # Fictional category

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

            mock_client = MagicMock()
            mock_genai_module.Client.return_value = mock_client

            mock_response = MagicMock()
            mock_response.text = '{"entities": [{"name": "Test Entity", "type": "Person", "subtype": "Fictional character"}, {"name": "Other Entity", "type": "Person", "subtype": "Another fictional character"}], "relations": [{"source_entity": "Test Entity", "relation_type": "FRIEND_OF", "target_entity": "Other Entity"}]}'
            mock_client.aio.models.generate_content = AsyncMock(
                return_value=mock_response
            )

            await knowledge_graph_job(ctx, book_id)

            mock_graph_repo.init_constraints.assert_called_once()
            # Assert entities are namespaced using base title (excluding '-1')
            mock_graph_repo.upsert_entities_bulk.assert_called_once_with(
                [
                    {
                        "name": "Test Entity (Test Book)",
                        "type": "Person",
                        "subtype": "Fictional character",
                    },
                    {
                        "name": "Other Entity (Test Book)",
                        "type": "Person",
                        "subtype": "Another fictional character",
                    },
                ]
            )
            mock_graph_repo.connect_entities_bulk.assert_called_once_with(
                [
                    {
                        "source_name": "Test Entity (Test Book)",
                        "rel_type": "FRIEND_OF",
                        "target_name": "Other Entity (Test Book)",
                        "book_id": book_id,
                    }
                ]
            )
            mock_graph_repo.close.assert_called_once()

            mock_session.commit.assert_called()


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
            new_callable=AsyncMock,
        ) as mock_get_value:
            mock_get_value.side_effect = lambda key, default=None: {
                "knowledge_graph_enabled": "true",
                "gemini_chat_model": "gemini-2.0-flash-lite",
                "kg_max_parallel_chunks": "5",
                "kg_chunk_batch_size": "5",
            }.get(key, default)

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
                await knowledge_graph_job(ctx, book_id)

            mock_graph_repo.close.assert_called_once()
            mock_session.commit.assert_called()


@pytest.mark.asyncio
async def test_knowledge_graph_job_duplicate_names_resolution():
    ctx = {}
    book_id = "book-456"

    with (
        patch("app.db.session.async_session_factory") as mock_session_factory,
        patch("services.worker.jobs.knowledge_graph_job.settings") as mock_settings,
        patch(
            "services.worker.jobs.knowledge_graph_job.GraphRepository"
        ) as mock_graph_repo_class,
        patch("services.worker.jobs.knowledge_graph_job.genai") as mock_genai_module,
    ):
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        with patch(
            "services.worker.jobs.knowledge_graph_job.SystemConfigsRepository.get_value",
            new_callable=AsyncMock,
        ) as mock_get_value:
            mock_get_value.side_effect = lambda key, default=None: {
                "knowledge_graph_enabled": "true",
                "gemini_kg_extraction_model": "gemini-3.1-flash-lite",
                "kg_max_parallel_chunks": "5",
                "kg_chunk_batch_size": "1",
                "fictional_categories": "رومان, داستان-رومان, novel",
            }.get(key, default)

            mock_settings.gemini_api_key = "fake-key"

            mock_book = MagicMock(spec=Book)
            mock_book.id = book_id
            mock_book.title = "History Book"
            mock_book.author = "Author"
            mock_book.categories = ["تارىخ"]

            mock_chunk_1 = MagicMock(spec=Chunk)
            mock_chunk_1.id = "chunk-1"
            mock_chunk_1.page_number = 1
            mock_chunk_1.chunk_index = 0
            mock_chunk_1.text = (
                "This is chunk 1 text about Abdullah I and Babur Padishah."
            )

            mock_chunk_2 = MagicMock(spec=Chunk)
            mock_chunk_2.id = "chunk-2"
            mock_chunk_2.page_number = 2
            mock_chunk_2.chunk_index = 0
            mock_chunk_2.text = "This is chunk 2 text about Abdullah II and Babur."

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_book
            mock_result.scalars().all.return_value = [mock_chunk_1, mock_chunk_2]
            mock_session.execute.return_value = mock_result

            mock_graph_repo = AsyncMock()
            mock_graph_repo_class.return_value = mock_graph_repo

            mock_client = MagicMock()
            mock_genai_module.Client.return_value = mock_client

            def mock_generate_content(model, contents, config):
                resp = MagicMock()
                if config.response_schema.__name__ == "KnowledgeExtraction":
                    if "Page 1" in contents:
                        resp.text = '{"entities": [{"name": "\\u0626\\u0627\\u0628\\u062f\\u064f\\u0644\\u0644\\u0627\\u0647", "type": "Person", "subtype": "Sultan", "year_hijri": 800, "context_summary": "ruler of Moghulistan"}, {"name": "\\u0628\\u0627\\u0628\\u064f\\u0648\\u0631 \\u067e\\u0627\\u062f\\u0650\\u0634\\u0627\\u0647", "type": "Person", "subtype": "King"}], "relations": [{"source_entity": "\\u0626\\u0627\\u0628\\u062f\\u064f\\u0644\\u0644\\u0627\\u0647", "relation_type": "SON_OF", "target_entity": "\\u0626\\u06d5\\u062e\\u0645\\u06d5\\u062a"}]}'
                    else:
                        resp.text = '{"entities": [{"name": "\\u0626\\u0627\\u0628\\u062f\\u064f\\u0644\\u0644\\u0627\\u0647", "type": "Person", "subtype": "General", "year_hijri": 950, "context_summary": "general under Abdurashid Khan"}, {"name": "\\u0628\\u0627\\u0628\\u064f\\u0631", "type": "Person", "subtype": "Ruler"}], "relations": [{"source_entity": "\\u0626\\u0627\\u0628\\u062f\\u064f\\u0644\\u0644\\u0627\\u0647", "relation_type": "SERVED", "target_entity": "\\u0626\\u0627\\u0628\\u062f\\u064f\\u0631\\u0627\\u0634\\u064a\\u062f\\u062e\\u0627\\u0646"}, {"source_entity": "\\u0628\\u0627\\u0628\\u064f\\u0631", "relation_type": "RULED", "target_entity": "\\u0643\\u0627\\u0628\\u06c7\\u0644"}]}'
                elif config.response_schema.__name__ == "NameResolutionResponse":
                    resp.text = '{"resolutions": [{"occurrence_index": 0, "resolved_name": "\\u0626\\u0627\\u0628\\u062f\\u064f\\u0644\\u0644\\u0627\\u0647 I"}, {"occurrence_index": 1, "resolved_name": "\\u0628\\u0627\\u0628\\u064f\\u0631"}, {"occurrence_index": 2, "resolved_name": "\\u0626\\u0627\\u0628\\u062f\\u064f\\u0644\\u0644\\u0627\\u0647 II"}, {"occurrence_index": 3, "resolved_name": "\\u0628\\u0627\\u0628\\u064f\\u0631"}]}'
                return resp

            mock_client.aio.models.generate_content = AsyncMock(
                side_effect=mock_generate_content
            )

            await knowledge_graph_job(ctx, book_id)

            mock_graph_repo.init_constraints.assert_called_once()

            upsert_calls = mock_graph_repo.upsert_entities_bulk.call_args[0][0]
            names = [e["name"] for e in upsert_calls]
            assert "ئابدُللاه I" in names
            assert "ئابدُللاه II" in names
            assert "ئەخمەت" in names
            assert "ئابدُراشيدخان" in names
            assert "بابُر" in names
            assert "كابۇل" in names

            connect_calls = mock_graph_repo.connect_entities_bulk.call_args[0][0]
            assert len(connect_calls) == 3

            rel_son = next(c for c in connect_calls if c["rel_type"] == "SON_OF")
            assert rel_son["source_name"] == "ئابدُللاه I"
            assert rel_son["target_name"] == "ئەخمەت"

            rel_served = next(c for c in connect_calls if c["rel_type"] == "SERVED")
            assert rel_served["source_name"] == "ئابدُللاه II"
            assert rel_served["target_name"] == "ئابدُراشيدخان"

            rel_ruled = next(c for c in connect_calls if c["rel_type"] == "RULED")
            assert rel_ruled["source_name"] == "بابُر"
            assert rel_ruled["target_name"] == "كابۇل"

            mock_graph_repo.close.assert_called_once()
            mock_session.commit.assert_called()
