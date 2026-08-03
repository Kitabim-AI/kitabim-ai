import pytest
from unittest.mock import AsyncMock, patch
from app.services.history_extraction_service import HistoryExtractionService


def _svc():
    return HistoryExtractionService(AsyncMock())


def test_parse_extraction_entities_handles_wrapped_object():
    from app.services.history_extraction_service import parse_extraction_entities

    raw = '{"entities": [{"term": "x"}]}'
    assert parse_extraction_entities(raw) == [{"term": "x"}]


def test_parse_extraction_entities_handles_bare_list():
    # Some models skip the requested {"entities": [...]} wrapper and return
    # the array directly — this must not be silently dropped.
    from app.services.history_extraction_service import parse_extraction_entities

    raw = '[{"term": "x"}, {"term": "y"}]'
    assert parse_extraction_entities(raw) == [{"term": "x"}, {"term": "y"}]


def test_parse_extraction_entities_handles_markdown_fence():
    from app.services.history_extraction_service import parse_extraction_entities

    raw = '```json\n{"entities": [{"term": "x"}]}\n```'
    assert parse_extraction_entities(raw) == [{"term": "x"}]


def test_parse_extraction_entities_returns_empty_for_garbage():
    from app.services.history_extraction_service import parse_extraction_entities

    assert parse_extraction_entities("not json at all") == []


@pytest.mark.asyncio
async def test_call_llm_extraction_handles_bare_list_response():
    service = _svc()
    with patch(
        "app.llm.models.generate_text",
        new=AsyncMock(return_value='[{"term": "x", "facts": []}]'),
    ):
        entities = await service._call_llm_extraction("page text", "gemini-2.5-flash")
    assert entities == [{"term": "x", "facts": []}]


@pytest.mark.asyncio
async def test_merge_facts_tier1_deterministic_duplicate_merges_citation():
    service = _svc()
    existing = [
        {
            "id": 1,
            "text": "تارىخى رەشىدى ئۇنىڭ نامىغا بېغىشلانغان.",
            "citations": [{"book_id": "book-1", "book_title": "T", "pages": [40]}],
            "status": "active",
            "conflict_group": None,
        }
    ]
    candidates = [{"text": "تارىخى رەشىدىي ئۇنىڭ نامىغا بېغىشلانغان.", "pages": [54]}]
    citation_base = {"book_id": "book-1", "book_title": "T", "volume": None}

    result = await service._merge_facts(
        "سۇلتان سەئىدخان", existing, candidates, citation_base, "gemini-2.5-flash"
    )

    assert len(result) == 1
    assert result[0]["citations"][0]["pages"] == [40, 54]


@pytest.mark.asyncio
async def test_merge_facts_no_existing_facts_appends_as_new_without_embedding_or_llm():
    service = _svc()
    candidates = [{"text": "ھىجرىيە 915-يىلى تۇغۇلغان.", "pages": [343]}]
    citation_base = {"book_id": "book-1", "book_title": "T", "volume": None}

    with patch.object(
        service, "_embed_facts", new=AsyncMock()
    ) as mock_embed, patch.object(
        service, "_classify_facts", new=AsyncMock()
    ) as mock_classify:
        result = await service._merge_facts(
            "سۇلتان سەئىدخان", [], candidates, citation_base, "gemini-2.5-flash"
        )

    mock_embed.assert_not_called()
    mock_classify.assert_not_called()
    assert len(result) == 1
    assert result[0]["status"] == "active"
    assert result[0]["id"] == 1


@pytest.mark.asyncio
async def test_merge_facts_tier2_low_similarity_appends_as_new_without_llm():
    service = _svc()
    existing = [
        {
            "id": 1,
            "text": "ياركەند خانلىقىنىڭ خانى.",
            "citations": [],
            "status": "active",
            "conflict_group": None,
        }
    ]
    candidates = [{"text": "ھىجرىيە 915-يىلى تۇغۇلغان.", "pages": [343]}]
    citation_base = {"book_id": "book-1", "book_title": "T", "volume": None}

    with patch.object(
        service, "_embed_facts", new=AsyncMock(return_value=[[1.0, 0.0], [0.0, 1.0]])
    ), patch.object(service, "_classify_facts", new=AsyncMock()) as mock_classify:
        result = await service._merge_facts(
            "سۇلتان سەئىدخان", existing, candidates, citation_base, "gemini-2.5-flash"
        )

    mock_classify.assert_not_called()
    assert len(result) == 2
    assert result[1]["text"] == "ھىجرىيە 915-يىلى تۇغۇلغان."
    assert result[1]["status"] == "active"


@pytest.mark.asyncio
async def test_merge_facts_tier3_duplicate_decision_merges_citation():
    service = _svc()
    existing = [
        {
            "id": 1,
            "text": "ياركەند خانلىقىنىڭ خانى.",
            "citations": [],
            "status": "active",
            "conflict_group": None,
        }
    ]
    candidates = [{"text": "ياركەند سەئىدىيە خانلىقىنىڭ ھۆكۈمرانى.", "pages": [341]}]
    citation_base = {"book_id": "book-2", "book_title": "U", "volume": None}

    with patch.object(
        service, "_embed_facts", new=AsyncMock(return_value=[[1.0, 0.0], [0.9, 0.1]])
    ), patch.object(
        service,
        "_classify_facts",
        new=AsyncMock(
            return_value=[
                {
                    "candidate_index": 0,
                    "decision": "duplicate",
                    "existing_fact_id": 1,
                    "reason": "same fact",
                }
            ]
        ),
    ):
        result = await service._merge_facts(
            "سۇلتان سەئىدخان", existing, candidates, citation_base, "gemini-2.5-flash"
        )

    assert len(result) == 1
    assert result[0]["citations"][0]["book_id"] == "book-2"


@pytest.mark.asyncio
async def test_merge_facts_tier3_conflict_decision_flags_both_facts():
    service = _svc()
    existing = [
        {
            "id": 1,
            "text": "ھىجرىيە 915-يىلى تۇغۇلغان.",
            "citations": [],
            "status": "active",
            "conflict_group": None,
        }
    ]
    candidates = [{"text": "ھىجرىيە 916-يىلى تۇغۇلغان.", "pages": [346]}]
    citation_base = {"book_id": "book-2", "book_title": "U", "volume": None}

    with patch.object(
        service, "_embed_facts", new=AsyncMock(return_value=[[1.0, 0.0], [0.95, 0.05]])
    ), patch.object(
        service,
        "_classify_facts",
        new=AsyncMock(
            return_value=[
                {
                    "candidate_index": 0,
                    "decision": "conflict",
                    "existing_fact_id": 1,
                    "reason": "different year",
                }
            ]
        ),
    ):
        result = await service._merge_facts(
            "سۇلتان سەئىدخان", existing, candidates, citation_base, "gemini-2.5-flash"
        )

    assert len(result) == 2
    assert all(f["status"] == "conflict" for f in result)
    assert result[0]["conflict_group"] == result[1]["conflict_group"]
    assert result[0]["conflict_group"] is not None


@pytest.mark.asyncio
async def test_merge_facts_tier3_failure_falls_back_to_new():
    service = _svc()
    existing = [
        {
            "id": 1,
            "text": "ياركەند خانلىقىنىڭ خانى.",
            "citations": [],
            "status": "active",
            "conflict_group": None,
        }
    ]
    candidates = [{"text": "قوشۇمچە پاكىت.", "pages": [50]}]
    citation_base = {"book_id": "book-2", "book_title": "U", "volume": None}

    with patch.object(
        service, "_embed_facts", new=AsyncMock(return_value=[[1.0, 0.0], [0.9, 0.1]])
    ), patch.object(service, "_classify_facts", new=AsyncMock(return_value=[])):
        result = await service._merge_facts(
            "سۇلتان سەئىدخان", existing, candidates, citation_base, "gemini-2.5-flash"
        )

    assert len(result) == 2
    assert result[1]["status"] == "active"


@pytest.mark.asyncio
async def test_merge_facts_embedding_failure_routes_all_unresolved_to_classification():
    service = _svc()
    existing = [
        {
            "id": 1,
            "text": "ياركەند خانلىقىنىڭ خانى.",
            "citations": [],
            "status": "active",
            "conflict_group": None,
        }
    ]
    candidates = [{"text": "قوشۇمچە پاكىت.", "pages": [50]}]
    citation_base = {"book_id": "book-2", "book_title": "U", "volume": None}

    with patch.object(
        service,
        "_embed_facts",
        new=AsyncMock(side_effect=RuntimeError("embedding api down")),
    ), patch.object(
        service,
        "_classify_facts",
        new=AsyncMock(
            return_value=[
                {
                    "candidate_index": 0,
                    "decision": "new",
                    "existing_fact_id": None,
                    "reason": "x",
                }
            ]
        ),
    ) as mock_classify:
        result = await service._merge_facts(
            "سۇلتان سەئىدخان", existing, candidates, citation_base, "gemini-2.5-flash"
        )

    mock_classify.assert_called_once()
    assert len(result) == 2


@pytest.mark.asyncio
async def test_synthesize_definition_returns_text_from_llm():
    service = _svc()
    facts = [
        {
            "id": 1,
            "text": "ياركەند خانلىقىنىڭ خانى.",
            "citations": [{"book_id": "b1", "book_title": "T", "pages": [40]}],
            "status": "active",
            "conflict_group": None,
        },
    ]
    with patch(
        "app.llm.models.generate_text",
        new=AsyncMock(return_value='{"definition": "ياركەند خانلىقىنىڭ خانى [40]."}'),
    ):
        definition = await service._synthesize_definition(
            "سۇلتان سەئىدخان", facts, "gemini-2.5-flash"
        )
    assert definition == "ياركەند خانلىقىنىڭ خانى [40]."


@pytest.mark.asyncio
async def test_synthesize_definition_excludes_non_active_facts():
    service = _svc()
    facts = [
        {
            "id": 1,
            "text": "active fact",
            "citations": [],
            "status": "active",
            "conflict_group": None,
        },
        {
            "id": 2,
            "text": "conflicting fact",
            "citations": [],
            "status": "conflict",
            "conflict_group": 1,
        },
    ]
    captured_prompt = {}

    async def fake_generate_text(prompt, model_name):
        captured_prompt["value"] = prompt
        return '{"definition": "synthesized"}'

    with patch("app.llm.models.generate_text", new=fake_generate_text):
        await service._synthesize_definition("Term", facts, "gemini-2.5-flash")

    assert "conflicting fact" not in captured_prompt["value"]
    assert "active fact" in captured_prompt["value"]


@pytest.mark.asyncio
async def test_synthesize_definition_raises_on_empty_result():
    from app.services.history_extraction_service import HistoryFactSynthesisError

    service = _svc()
    facts = [
        {
            "id": 1,
            "text": "x",
            "citations": [],
            "status": "active",
            "conflict_group": None,
        }
    ]
    with patch(
        "app.llm.models.generate_text", new=AsyncMock(return_value='{"definition": ""}')
    ):
        with pytest.raises(HistoryFactSynthesisError):
            await service._synthesize_definition("Term", facts, "gemini-2.5-flash")


@pytest.mark.asyncio
async def test_synthesize_definition_raises_on_llm_failure():
    from app.services.history_extraction_service import HistoryFactSynthesisError

    service = _svc()
    facts = [
        {
            "id": 1,
            "text": "x",
            "citations": [],
            "status": "active",
            "conflict_group": None,
        }
    ]
    with patch(
        "app.llm.models.generate_text",
        new=AsyncMock(side_effect=RuntimeError("timeout")),
    ):
        with pytest.raises(HistoryFactSynthesisError):
            await service._synthesize_definition("Term", facts, "gemini-2.5-flash")


@pytest.mark.asyncio
async def test_stage_entity_skips_non_ai_generated_records():
    service = _svc()

    non_ai_record = AsyncMock()
    non_ai_record.id = 100
    non_ai_record.term = "سۇلتان سۇتۇق بۇغراخان"
    non_ai_record.is_ai_generated = False

    service.repo.find_matching_history_term = AsyncMock(return_value=non_ai_record)
    service.repo.find_matching_staging_term = AsyncMock(return_value=None)
    service.repo.create_staging_term = AsyncMock()

    entity = {
        "term": "سۇلتان سۇتۇق بۇغراخان",
        "transliteration": "Sultan Sutuk Bughra Khan",
        "category": "figure",
        "significance_score": 9,
        "significance_reason": "Ruler",
        "facts": [{"text": "تارىخىي شەخس", "pages": [12]}],
    }

    staged_item = await service._stage_entity(
        book_id="test-book",
        book_title="Test Book",
        volume=1,
        entity=entity,
        model_name="gemini-2.5-flash",
    )

    assert staged_item is None
    service.repo.create_staging_term.assert_not_called()


@pytest.mark.asyncio
async def test_stage_entity_new_term_creates_staging_with_merged_facts():
    service = _svc()

    service.repo.find_matching_history_term = AsyncMock(return_value=None)
    service.repo.find_matching_staging_term = AsyncMock(return_value=None)

    mock_staged = AsyncMock()
    mock_staged.id = 200
    mock_staged.term = "قاراخانىيلار"
    mock_staged.category = "dynasty"
    mock_staged.significance_score = 8
    mock_staged.entry_type = "new"
    service.repo.create_staging_term = AsyncMock(return_value=mock_staged)

    entity = {
        "term": "قاراخانىيلار",
        "transliteration": "Karakhanids",
        "category": "dynasty",
        "significance_score": 8,
        "significance_reason": "Dynasty",
        "facts": [
            {
                "text": "ئوتتۇرا ئاسىيادىكى تۇنجى ئىسلاملاشقان تۈركىي خانلىق.",
                "pages": [5],
            }
        ],
    }

    staged_item = await service._stage_entity(
        book_id="test-book",
        book_title="Test Book",
        volume=1,
        entity=entity,
        model_name="gemini-2.5-flash",
    )

    assert staged_item is not None
    service.repo.create_staging_term.assert_called_once()
    kwargs = service.repo.create_staging_term.call_args.kwargs
    assert kwargs["entry_type"] == "new"
    assert kwargs["definition"] is None
    assert len(kwargs["facts"]) == 1
    assert kwargs["facts"][0]["citations"][0]["pages"] == [5]


@pytest.mark.asyncio
async def test_stage_entity_enrichment_bootstraps_legacy_facts_from_live_definition():
    service = _svc()

    ai_record = AsyncMock()
    ai_record.id = 101
    ai_record.term = "قاراخانىيلار"
    ai_record.is_ai_generated = True
    ai_record.definition = "دەسلەپكى ئېنىقلىما."
    ai_record.facts = []
    ai_record.transliteration = "Karakhanids"

    service.repo.find_matching_history_term = AsyncMock(return_value=ai_record)
    service.repo.find_matching_staging_term = AsyncMock(return_value=None)

    mock_staged = AsyncMock()
    mock_staged.id = 200
    mock_staged.term = "قاراخانىيلار"
    mock_staged.category = "dynasty"
    mock_staged.significance_score = 8
    mock_staged.entry_type = "enrichment"
    service.repo.create_staging_term = AsyncMock(return_value=mock_staged)

    entity = {
        "term": "قاراخانىيلار",
        "transliteration": "Karakhanids",
        "category": "dynasty",
        "significance_score": 8,
        "significance_reason": "Dynasty",
        "facts": [{"text": "يېڭى پاكىت.", "pages": [6]}],
    }

    with patch.object(
        service, "_embed_facts", new=AsyncMock(return_value=[[1.0, 0.0], [0.0, 1.0]])
    ):
        staged_item = await service._stage_entity(
            book_id="test-book",
            book_title="Test Book",
            volume=1,
            entity=entity,
            model_name="gemini-2.5-flash",
        )

    assert staged_item is not None
    kwargs = service.repo.create_staging_term.call_args.kwargs
    assert kwargs["existing_dictionary_id"] == 101
    assert kwargs["original_definition"] == "دەسلەپكى ئېنىقلىما."
    texts = [f["text"] for f in kwargs["facts"]]
    assert "دەسلەپكى ئېنىقلىما." in texts  # bootstrapped legacy fact preserved
    assert "يېڭى پاكىت." in texts


@pytest.mark.asyncio
async def test_stage_entity_updates_existing_staging_in_place():
    service = _svc()

    existing_staging = AsyncMock()
    existing_staging.id = 50
    existing_staging.term = "ئاتالغۇ"
    existing_staging.transliteration = "Term"
    existing_staging.category = "general"
    existing_staging.significance_score = 5
    existing_staging.significance_reason = "Reason"
    existing_staging.entry_type = "new"
    existing_staging.facts = [
        {
            "id": 1,
            "text": "دەسلەپكى تەكلىپ.",
            "citations": [],
            "status": "active",
            "conflict_group": None,
        }
    ]

    service.repo.find_matching_history_term = AsyncMock(return_value=None)
    service.repo.find_matching_staging_term = AsyncMock(return_value=existing_staging)

    mock_updated = AsyncMock()
    mock_updated.id = 50
    mock_updated.term = "ئاتالغۇ"
    mock_updated.category = "general"
    mock_updated.significance_score = 7
    mock_updated.entry_type = "new"
    service.repo.update_staging_term = AsyncMock(return_value=mock_updated)
    service.repo.create_staging_term = AsyncMock()

    entity = {
        "term": "ئاتالغۇ",
        "transliteration": "Term",
        "category": "general",
        "significance_score": 7,
        "significance_reason": "Updated Reason",
        "facts": [{"text": "يېڭىلانغان پاكىت.", "pages": [15]}],
    }

    with patch.object(
        service, "_embed_facts", new=AsyncMock(return_value=[[1.0, 0.0], [0.0, 1.0]])
    ):
        staged_item = await service._stage_entity(
            book_id="book-1",
            book_title="Title",
            volume=1,
            entity=entity,
            model_name="gemini-2.5-flash",
        )

    assert staged_item is not None
    service.repo.update_staging_term.assert_called_once()
    service.repo.create_staging_term.assert_not_called()
    kwargs = service.repo.update_staging_term.call_args.kwargs
    assert kwargs["significance_score"] == 7
    assert len(kwargs["facts"]) == 2


def test_process_book_pages_defaults_overlap_to_zero():
    import inspect
    from app.services.history_extraction_service import HistoryExtractionService

    sig = inspect.signature(HistoryExtractionService.process_book_pages)
    assert sig.parameters["overlap"].default == 0
