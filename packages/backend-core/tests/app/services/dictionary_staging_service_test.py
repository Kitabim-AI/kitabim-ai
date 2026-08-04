import pytest
from unittest.mock import AsyncMock, patch
from app.services.dictionary_staging_service import (
    DictionaryStagingService,
    StagingConflictsUnresolvedError,
)
from app.services.history_extraction_service import HistoryFactSynthesisError


@pytest.mark.asyncio
async def test_approve_staging_term_skips_updating_non_ai_entry():
    mock_session = AsyncMock()
    service = DictionaryStagingService(mock_session)

    mock_staging = AsyncMock()
    mock_staging.id = 1
    mock_staging.status = "pending"
    mock_staging.existing_dictionary_id = 10
    mock_staging.term = "سۇلتان سۇتۇق بۇغراخان"
    mock_staging.transliteration = "Sultan Sutuk Bughra Khan"
    mock_staging.category = "figure"
    mock_staging.significance_score = 9
    mock_staging.facts = [
        {
            "id": 1,
            "text": "AI generated fact",
            "citations": [],
            "status": "active",
            "conflict_group": None,
        }
    ]

    mock_target_entry = AsyncMock()
    mock_target_entry.id = 10
    mock_target_entry.term = "سۇلتان سۇتۇق بۇغراخان"
    mock_target_entry.is_ai_generated = False
    mock_target_entry.definition = "Human curated original definition"
    mock_target_entry.transliteration = "Sultan Sutuk"
    mock_target_entry.letter_group = "س"
    mock_target_entry.category = "figure"
    mock_target_entry.significance_score = 10
    mock_target_entry.facts = []

    service.repo.get_staging_term_by_id = AsyncMock(return_value=mock_staging)
    service.repo.get_history_dictionary_by_id = AsyncMock(
        return_value=mock_target_entry
    )
    service.repo.update_history_dictionary_entry = AsyncMock()
    service.repo.update_staging_term = AsyncMock()
    service.repo.set_staging_status = AsyncMock()

    with patch(
        "app.services.history_extraction_service.HistoryExtractionService._synthesize_definition",
        new=AsyncMock(return_value="synthesized definition"),
    ), patch(
        "app.services.history_extraction_service.HistoryExtractionService._get_system_config_model",
        new=AsyncMock(return_value="gemini-2.5-flash"),
    ):
        res = await service.approve_staging_term(1)

    assert res is not None
    # Should NOT call update_history_dictionary_entry for non-AI generated record
    service.repo.update_history_dictionary_entry.assert_not_called()
    service.repo.set_staging_status.assert_called_once_with(mock_staging, "approved")


@pytest.mark.asyncio
async def test_approve_staging_term_blocks_on_unresolved_conflict():
    mock_session = AsyncMock()
    service = DictionaryStagingService(mock_session)

    mock_staging = AsyncMock()
    mock_staging.id = 1
    mock_staging.status = "pending"
    mock_staging.facts = [
        {
            "id": 1,
            "text": "x",
            "citations": [],
            "status": "conflict",
            "conflict_group": 1,
        },
        {
            "id": 2,
            "text": "y",
            "citations": [],
            "status": "conflict",
            "conflict_group": 1,
        },
    ]
    service.repo.get_staging_term_by_id = AsyncMock(return_value=mock_staging)

    with pytest.raises(StagingConflictsUnresolvedError):
        await service.approve_staging_term(1)


@pytest.mark.asyncio
async def test_approve_staging_term_synthesizes_and_publishes_facts():
    mock_session = AsyncMock()
    service = DictionaryStagingService(mock_session)

    mock_staging = AsyncMock()
    mock_staging.id = 1
    mock_staging.status = "pending"
    mock_staging.existing_dictionary_id = None
    mock_staging.term = "قاراخانىيلار"
    mock_staging.transliteration = "Karakhanids"
    mock_staging.category = "dynasty"
    mock_staging.significance_score = 8
    mock_staging.is_ai_generated = True
    mock_staging.letter_group = "ق"
    mock_staging.facts = [
        {
            "id": 1,
            "text": "fact one",
            "citations": [],
            "status": "active",
            "conflict_group": None,
        }
    ]
    service.repo.get_staging_term_by_id = AsyncMock(return_value=mock_staging)
    service.repo.get_history_dictionary_by_term = AsyncMock(return_value=None)

    mock_entry = AsyncMock()
    mock_entry.id = 5
    mock_entry.term = "قاراخانىيلار"
    mock_entry.transliteration = "Karakhanids"
    mock_entry.definition = "synthesized definition"
    mock_entry.letter_group = "ق"
    mock_entry.category = "dynasty"
    mock_entry.significance_score = 8
    mock_entry.is_ai_generated = True
    mock_entry.facts = mock_staging.facts
    service.repo.create_history_dictionary_entry = AsyncMock(return_value=mock_entry)
    service.repo.update_staging_term = AsyncMock()
    service.repo.set_staging_status = AsyncMock()

    with patch(
        "app.services.history_extraction_service.HistoryExtractionService._synthesize_definition",
        new=AsyncMock(return_value="synthesized definition"),
    ), patch(
        "app.services.history_extraction_service.HistoryExtractionService._get_system_config_model",
        new=AsyncMock(return_value="gemini-2.5-flash"),
    ):
        result = await service.approve_staging_term(1)

    assert result["definition"] == "synthesized definition"
    service.repo.create_history_dictionary_entry.assert_called_once()
    assert (
        service.repo.create_history_dictionary_entry.call_args.kwargs["facts"]
        == mock_staging.facts
    )


@pytest.mark.asyncio
async def test_approve_staging_term_propagates_synthesis_failure():
    mock_session = AsyncMock()
    service = DictionaryStagingService(mock_session)

    mock_staging = AsyncMock()
    mock_staging.id = 1
    mock_staging.status = "pending"
    mock_staging.facts = [
        {
            "id": 1,
            "text": "x",
            "citations": [],
            "status": "active",
            "conflict_group": None,
        }
    ]
    service.repo.get_staging_term_by_id = AsyncMock(return_value=mock_staging)

    with patch(
        "app.services.history_extraction_service.HistoryExtractionService._synthesize_definition",
        new=AsyncMock(side_effect=HistoryFactSynthesisError("boom")),
    ), patch(
        "app.services.history_extraction_service.HistoryExtractionService._get_system_config_model",
        new=AsyncMock(return_value="gemini-2.5-flash"),
    ):
        with pytest.raises(HistoryFactSynthesisError):
            await service.approve_staging_term(1)


@pytest.mark.asyncio
async def test_resolve_fact_updates_status_and_clears_conflict_group():
    mock_session = AsyncMock()
    service = DictionaryStagingService(mock_session)

    mock_staging = AsyncMock()
    mock_staging.id = 1
    mock_staging.status = "pending"
    mock_staging.facts = [
        {
            "id": 1,
            "text": "a",
            "citations": [],
            "status": "conflict",
            "conflict_group": 1,
        },
        {
            "id": 2,
            "text": "b",
            "citations": [],
            "status": "conflict",
            "conflict_group": 1,
        },
    ]
    service.repo.get_staging_term_by_id = AsyncMock(return_value=mock_staging)
    service.repo.update_staging_term = AsyncMock()

    result = await service.resolve_fact(1, fact_id=1, status="active")

    assert result is not None
    kwargs = service.repo.update_staging_term.call_args.kwargs
    resolved = next(f for f in kwargs["facts"] if f["id"] == 1)
    assert resolved["status"] == "active"
    assert resolved["conflict_group"] is None


@pytest.mark.asyncio
async def test_resolve_fact_invalidates_cached_embedding_when_text_edited():
    # A cached embedding is only valid for the text it was computed from — if
    # an admin edits the text, the stale vector must be dropped so the next
    # merge event re-embeds the corrected text instead of comparing against
    # a vector that no longer matches what's stored.
    mock_session = AsyncMock()
    service = DictionaryStagingService(mock_session)

    mock_staging = AsyncMock()
    mock_staging.id = 1
    mock_staging.status = "pending"
    mock_staging.facts = [
        {
            "id": 1,
            "text": "old text",
            "citations": [],
            "status": "active",
            "conflict_group": None,
            "embedding": [1.0, 0.0],
        }
    ]
    service.repo.get_staging_term_by_id = AsyncMock(return_value=mock_staging)
    service.repo.update_staging_term = AsyncMock()

    await service.resolve_fact(1, fact_id=1, status="active", text="edited text")

    kwargs = service.repo.update_staging_term.call_args.kwargs
    edited = next(f for f in kwargs["facts"] if f["id"] == 1)
    assert edited["text"] == "edited text"
    assert "embedding" not in edited


@pytest.mark.asyncio
async def test_resolve_fact_returns_none_for_unknown_fact_id():
    mock_session = AsyncMock()
    service = DictionaryStagingService(mock_session)

    mock_staging = AsyncMock()
    mock_staging.status = "pending"
    mock_staging.facts = [
        {
            "id": 1,
            "text": "a",
            "citations": [],
            "status": "active",
            "conflict_group": None,
        }
    ]
    service.repo.get_staging_term_by_id = AsyncMock(return_value=mock_staging)

    result = await service.resolve_fact(1, fact_id=999, status="rejected")
    assert result is None


@pytest.mark.asyncio
async def test_synthesize_definition_updates_cached_definition():
    mock_session = AsyncMock()
    service = DictionaryStagingService(mock_session)

    mock_staging = AsyncMock()
    mock_staging.id = 1
    mock_staging.term = "قاراخانىيلار"
    mock_staging.facts = [
        {
            "id": 1,
            "text": "x",
            "citations": [],
            "status": "active",
            "conflict_group": None,
        }
    ]
    service.repo.get_staging_term_by_id = AsyncMock(return_value=mock_staging)
    service.repo.update_staging_term = AsyncMock()

    with patch(
        "app.services.history_extraction_service.HistoryExtractionService._synthesize_definition",
        new=AsyncMock(return_value="preview text"),
    ), patch(
        "app.services.history_extraction_service.HistoryExtractionService._get_system_config_model",
        new=AsyncMock(return_value="gemini-2.5-flash"),
    ):
        definition = await service.synthesize_definition(1)

    assert definition == "preview text"
    service.repo.update_staging_term.assert_called_once_with(
        mock_staging, definition="preview text"
    )
