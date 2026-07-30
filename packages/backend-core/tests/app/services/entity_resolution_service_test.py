import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.entity_resolution_service import (
    EntityResolutionVerdict,
    _check_hard_constraints,
    _graded_score,
    execute_merge,
    execute_split,
    execute_unmerge,
    normalize_alias,
    resolve_entity,
    update_alias_cache,
)


def test_normalize_alias_trims_and_lowercases():
    assert normalize_alias("  Ismail  ") == "ismail"


def test_check_hard_constraints_conflict_on_disjoint_parents():
    entity_facts = {
        "child_of": [{"parent_id": "p1"}],
        "born_in": [],
        "died_in": [],
        "neighbors": [],
    }
    candidate_facts = {
        "child_of": [{"parent_id": "p2"}],
        "born_in": [],
        "died_in": [],
        "neighbors": [],
    }
    assert _check_hard_constraints(entity_facts, candidate_facts) == "conflict"


def test_check_hard_constraints_match_on_shared_parent():
    entity_facts = {
        "child_of": [{"parent_id": "p1"}],
        "born_in": [],
        "died_in": [],
        "neighbors": [],
    }
    candidate_facts = {
        "child_of": [{"parent_id": "p1"}],
        "born_in": [],
        "died_in": [],
        "neighbors": [],
    }
    assert _check_hard_constraints(entity_facts, candidate_facts) == "match"


def test_check_hard_constraints_none_when_sparse():
    entity_facts = {"child_of": [], "born_in": [], "died_in": [], "neighbors": []}
    candidate_facts = {"child_of": [], "born_in": [], "died_in": [], "neighbors": []}
    assert _check_hard_constraints(entity_facts, candidate_facts) == "none"


def test_check_hard_constraints_falls_back_to_born_in():
    entity_facts = {
        "child_of": [],
        "born_in": [{"location_id": "l1"}],
        "died_in": [],
        "neighbors": [],
    }
    candidate_facts = {
        "child_of": [],
        "born_in": [{"location_id": "l2"}],
        "died_in": [],
        "neighbors": [],
    }
    assert _check_hard_constraints(entity_facts, candidate_facts) == "conflict"


def test_graded_score_high_for_identical_name_and_overlapping_neighbors():
    entity = {"canonical_name": "Same Name", "aliases": [], "subtype": "Sultan"}
    candidate = {"canonical_name": "Same Name", "aliases": [], "subtype": "Sultan"}
    entity_facts = {"neighbors": [{"neighbor_id": "n1"}, {"neighbor_id": "n2"}]}
    candidate_facts = {"neighbors": [{"neighbor_id": "n1"}, {"neighbor_id": "n2"}]}
    score = _graded_score(entity, candidate, entity_facts, candidate_facts)
    assert score > 0.9


def test_graded_score_low_for_different_name_and_no_overlap():
    entity = {"canonical_name": "Alpha", "aliases": [], "subtype": None}
    candidate = {"canonical_name": "Zeta", "aliases": [], "subtype": None}
    entity_facts = {"neighbors": [{"neighbor_id": "n1"}]}
    candidate_facts = {"neighbors": [{"neighbor_id": "n2"}]}
    score = _graded_score(entity, candidate, entity_facts, candidate_facts)
    assert score < 0.3


@pytest.mark.asyncio
async def test_update_alias_cache_unions_existing_ids():
    graph_repo = AsyncMock()
    graph_repo.get_entity_by_id.return_value = {
        "canonical_name": "Name",
        "aliases": ["Alt"],
    }
    with patch("app.services.entity_resolution_service.cache_service") as mock_cache:
        mock_cache.get = AsyncMock(return_value=["other-id"])
        mock_cache.set = AsyncMock()

        await update_alias_cache(graph_repo, "e1")

        assert mock_cache.set.call_count == 2  # "Name" and "Alt"
        for call in mock_cache.set.call_args_list:
            ids = call[0][1]
            assert set(ids) == {"other-id", "e1"}


@pytest.mark.asyncio
async def test_update_alias_cache_noop_when_entity_missing():
    graph_repo = AsyncMock()
    graph_repo.get_entity_by_id.return_value = None
    with patch("app.services.entity_resolution_service.cache_service") as mock_cache:
        await update_alias_cache(graph_repo, "missing")
        mock_cache.set.assert_not_called()


@pytest.mark.asyncio
async def test_execute_merge_noop_when_entity_missing():
    session = AsyncMock()
    graph_repo = AsyncMock()
    graph_repo.get_entity_by_id.side_effect = [{"id": "keep-1"}, None]

    result = await execute_merge(
        session, graph_repo, "keep-1", "remove-1", "admin@example.com"
    )
    assert result is None
    graph_repo.merge_entities_by_id.assert_not_called()


@pytest.mark.asyncio
async def test_execute_merge_happy_path_logs_before_delete_and_requeues_children():
    session = AsyncMock()
    graph_repo = AsyncMock()
    graph_repo.get_entity_by_id.side_effect = [
        {"id": "keep-1", "canonical_name": "Keep", "aliases": []},
        {"id": "remove-1", "canonical_name": "Remove", "aliases": ["RemoveAlt"]},
    ]
    graph_repo.get_entity_edges_snapshot.return_value = [{"id": "edge-1"}]
    graph_repo.get_children_via_child_of.side_effect = [
        ["child-of-remove"],
        ["child-of-keep"],
    ]

    with (
        patch(
            "app.services.entity_resolution_service.GraphMergeLogRepository"
        ) as MockMergeLogRepo,
        patch(
            "app.services.entity_resolution_service.GraphResolutionQueueRepository"
        ) as MockQueueRepo,
        patch(
            "app.services.entity_resolution_service.GraphResolutionReviewsRepository"
        ) as MockReviewsRepo,
        patch(
            "app.services.entity_resolution_service.SystemConfigsRepository"
        ) as MockConfigRepo,
        patch(
            "app.services.entity_resolution_service.update_alias_cache", new=AsyncMock()
        ) as mock_update_cache,
    ):
        merge_log_repo = AsyncMock()
        merge_log_entry = MagicMock(id=42)
        merge_log_repo.log_merge.return_value = merge_log_entry
        MockMergeLogRepo.return_value = merge_log_repo

        queue_repo = AsyncMock()
        MockQueueRepo.return_value = queue_repo

        reviews_repo = AsyncMock()
        MockReviewsRepo.return_value = reviews_repo

        config_repo = AsyncMock()
        config_repo.get_value.return_value = "5"
        MockConfigRepo.return_value = config_repo

        result = await execute_merge(
            session, graph_repo, "keep-1", "remove-1", "admin@example.com"
        )

        assert result == 42
        # Snapshot logged BEFORE the Neo4j merge/delete call
        assert merge_log_repo.log_merge.call_args[1]["removed_entity_id"] == "remove-1"
        assert merge_log_repo.log_merge.call_args[1]["removed_edges_snapshot"] == [
            {"id": "edge-1"}
        ]
        graph_repo.merge_entities_by_id.assert_called_once()
        combined_aliases = graph_repo.merge_entities_by_id.call_args[0][2]
        assert set(combined_aliases) == {"Remove", "RemoveAlt"}

        queue_repo.delete_by_entity_id.assert_called_once_with("remove-1")
        reviews_repo.resolve_reviews_for_merge.assert_called_once_with(
            keep_id="keep-1", remove_id="remove-1", reviewed_by="admin@example.com"
        )
        requeued_ids = {c[0][0] for c in queue_repo.requeue_or_cap.call_args_list}
        assert requeued_ids == {"child-of-remove", "child-of-keep"}
        mock_update_cache.assert_called_once_with(graph_repo, "keep-1")


@pytest.mark.asyncio
async def test_execute_split_updates_alias_cache_for_both_nodes():
    graph_repo = AsyncMock()
    graph_repo.split_entities.return_value = {
        "new_entity_id": "new-1",
        "moved_edge_ids": ["edge-1"],
        "unclustered_edge_ids": [],
    }
    with patch(
        "app.services.entity_resolution_service.update_alias_cache", new=AsyncMock()
    ) as mock_update_cache:
        result = await execute_split(graph_repo, "orig-1", "split-edge")
        assert result["new_entity_id"] == "new-1"
        assert mock_update_cache.call_count == 2


@pytest.mark.asyncio
async def test_execute_unmerge_restores_and_marks_reverted():
    session = AsyncMock()
    graph_repo = AsyncMock()
    graph_repo.restore_entity_from_snapshot.return_value = []

    with (
        patch(
            "app.services.entity_resolution_service.GraphMergeLogRepository"
        ) as MockMergeLogRepo,
        patch(
            "app.services.entity_resolution_service.update_alias_cache", new=AsyncMock()
        ),
    ):
        merge_log_repo = AsyncMock()
        entry = MagicMock(
            reverted_at=None,
            kept_entity_id="keep-1",
            removed_entity_id="remove-1",
            removed_entity_snapshot={"id": "remove-1"},
            removed_edges_snapshot=[],
        )
        merge_log_repo.get.return_value = entry
        MockMergeLogRepo.return_value = merge_log_repo

        result = await execute_unmerge(session, graph_repo, 42)

        assert result["restored_entity_id"] == "remove-1"
        merge_log_repo.mark_reverted.assert_called_once_with(42)


@pytest.mark.asyncio
async def test_execute_unmerge_raises_on_missing_entry():
    session = AsyncMock()
    graph_repo = AsyncMock()
    with patch(
        "app.services.entity_resolution_service.GraphMergeLogRepository"
    ) as MockMergeLogRepo:
        merge_log_repo = AsyncMock()
        merge_log_repo.get.return_value = None
        MockMergeLogRepo.return_value = merge_log_repo

        with pytest.raises(ValueError):
            await execute_unmerge(session, graph_repo, 999)


@pytest.mark.asyncio
async def test_execute_unmerge_raises_if_already_reverted():
    session = AsyncMock()
    graph_repo = AsyncMock()
    with patch(
        "app.services.entity_resolution_service.GraphMergeLogRepository"
    ) as MockMergeLogRepo:
        merge_log_repo = AsyncMock()
        merge_log_repo.get.return_value = MagicMock(reverted_at="2026-01-01T00:00:00Z")
        MockMergeLogRepo.return_value = merge_log_repo

        with pytest.raises(ValueError):
            await execute_unmerge(session, graph_repo, 1)


@pytest.mark.asyncio
async def test_resolve_entity_missing_marks_failed():
    session = AsyncMock()
    graph_repo = AsyncMock()
    graph_repo.get_entity_by_id.return_value = None

    with patch(
        "app.services.entity_resolution_service.GraphResolutionQueueRepository"
    ) as MockQueueRepo:
        queue_repo = AsyncMock()
        MockQueueRepo.return_value = queue_repo

        await resolve_entity(session, graph_repo, "missing-id")

        queue_repo.mark_status.assert_called_once_with("missing-id", "failed")


@pytest.mark.asyncio
async def test_resolve_entity_no_candidates_marks_succeeded_and_resolved():
    session = AsyncMock()
    graph_repo = AsyncMock()
    graph_repo.get_entity_by_id.return_value = {
        "id": "e1",
        "canonical_name": "Solo",
        "aliases": [],
        "scope": "nonfiction",
        "book_id": None,
    }
    graph_repo.find_resolution_candidates.return_value = []
    graph_repo.get_entity_facts.return_value = {
        "child_of": [],
        "born_in": [],
        "died_in": [],
        "neighbors": [],
    }

    with (
        patch(
            "app.services.entity_resolution_service.GraphResolutionQueueRepository"
        ) as MockQueueRepo,
        patch(
            "app.services.entity_resolution_service.GraphResolutionReviewsRepository"
        ),
        patch(
            "app.services.entity_resolution_service.SystemConfigsRepository"
        ) as MockConfigRepo,
        patch(
            "app.services.entity_resolution_service.update_alias_cache", new=AsyncMock()
        ),
    ):
        queue_repo = AsyncMock()
        MockQueueRepo.return_value = queue_repo
        config_repo = AsyncMock()
        config_repo.get_value.return_value = "5"
        MockConfigRepo.return_value = config_repo

        await resolve_entity(session, graph_repo, "e1")

        graph_repo.set_resolution_status.assert_any_call("e1", "resolving")
        graph_repo.set_resolution_status.assert_any_call("e1", "resolved")
        queue_repo.mark_status.assert_called_once_with("e1", "succeeded")


@pytest.mark.asyncio
async def test_resolve_entity_hard_conflict_skips_candidate_and_succeeds():
    session = AsyncMock()
    graph_repo = AsyncMock()
    graph_repo.get_entity_by_id.side_effect = lambda eid: {
        "e1": {
            "id": "e1",
            "canonical_name": "A",
            "aliases": [],
            "scope": "nonfiction",
            "book_id": None,
        },
        "cand-1": {"id": "cand-1", "canonical_name": "A-lookalike", "aliases": []},
    }.get(eid)
    graph_repo.find_resolution_candidates.return_value = [
        {"id": "cand-1", "canonical_name": "A-lookalike"}
    ]
    graph_repo.get_entity_facts.side_effect = lambda eid: {
        "e1": {
            "child_of": [{"parent_id": "p1"}],
            "born_in": [],
            "died_in": [],
            "neighbors": [],
        },
        "cand-1": {
            "child_of": [{"parent_id": "p2"}],
            "born_in": [],
            "died_in": [],
            "neighbors": [],
        },
    }.get(eid, {"child_of": [], "born_in": [], "died_in": [], "neighbors": []})

    with (
        patch(
            "app.services.entity_resolution_service.GraphResolutionQueueRepository"
        ) as MockQueueRepo,
        patch(
            "app.services.entity_resolution_service.GraphResolutionReviewsRepository"
        ) as MockReviewsRepo,
        patch(
            "app.services.entity_resolution_service.SystemConfigsRepository"
        ) as MockConfigRepo,
        patch(
            "app.services.entity_resolution_service.execute_merge", new=AsyncMock()
        ) as mock_execute_merge,
        patch(
            "app.services.entity_resolution_service.update_alias_cache", new=AsyncMock()
        ),
    ):
        queue_repo = AsyncMock()
        MockQueueRepo.return_value = queue_repo
        reviews_repo = AsyncMock()
        MockReviewsRepo.return_value = reviews_repo
        config_repo = AsyncMock()
        config_repo.get_value.return_value = "5"
        MockConfigRepo.return_value = config_repo

        await resolve_entity(session, graph_repo, "e1")

        mock_execute_merge.assert_not_called()
        reviews_repo.create_review.assert_not_called()
        queue_repo.mark_status.assert_called_once_with("e1", "succeeded")


@pytest.mark.asyncio
async def test_resolve_entity_hard_match_executes_merge():
    session = AsyncMock()
    graph_repo = AsyncMock()
    graph_repo.get_entity_by_id.side_effect = lambda eid: {
        "e1": {
            "id": "e1",
            "canonical_name": "A",
            "aliases": [],
            "subtype": "Person",
            "scope": "nonfiction",
            "book_id": None,
        },
        "cand-1": {"id": "cand-1", "canonical_name": "A", "subtype": "Person"},
    }.get(eid)
    graph_repo.find_resolution_candidates.return_value = [
        {"id": "cand-1", "canonical_name": "A", "subtype": "Person"}
    ]
    graph_repo.get_entity_facts.side_effect = lambda eid: {
        "e1": {
            "child_of": [{"parent_id": "p1"}],
            "born_in": [],
            "died_in": [],
            "neighbors": [],
        },
        "cand-1": {
            "child_of": [{"parent_id": "p1"}],
            "born_in": [],
            "died_in": [],
            "neighbors": [],
        },
    }.get(eid, {"child_of": [], "born_in": [], "died_in": [], "neighbors": []})

    with (
        patch(
            "app.services.entity_resolution_service.GraphResolutionQueueRepository"
        ) as MockQueueRepo,
        patch(
            "app.services.entity_resolution_service.GraphResolutionReviewsRepository"
        ) as MockReviewsRepo,
        patch(
            "app.services.entity_resolution_service.SystemConfigsRepository"
        ) as MockConfigRepo,
        patch(
            "app.services.entity_resolution_service.execute_merge", new=AsyncMock()
        ) as mock_execute_merge,
        patch(
            "app.services.entity_resolution_service.update_alias_cache", new=AsyncMock()
        ),
    ):
        queue_repo = AsyncMock()
        MockQueueRepo.return_value = queue_repo
        reviews_repo = AsyncMock()
        MockReviewsRepo.return_value = reviews_repo
        config_repo = AsyncMock()
        config_repo.get_value.return_value = "5"
        MockConfigRepo.return_value = config_repo

        await resolve_entity(session, graph_repo, "e1")

        mock_execute_merge.assert_called_once_with(
            session,
            graph_repo,
            keep_id="e1",
            remove_id="cand-1",
            performed_by="system:resolution_job",
        )
        queue_repo.mark_status.assert_called_once_with("e1", "succeeded")


@pytest.mark.asyncio
async def test_resolve_entity_gray_zone_unsure_creates_review_and_marks_needs_review():
    session = AsyncMock()
    graph_repo = AsyncMock()
    graph_repo.get_entity_by_id.side_effect = lambda eid: {
        "e1": {
            "id": "e1",
            "canonical_name": "Somewhat Similar A",
            "aliases": [],
            "scope": "nonfiction",
            "book_id": None,
        },
        "cand-1": {
            "id": "cand-1",
            "canonical_name": "Somewhat Similar B",
            "aliases": [],
        },
    }.get(eid)
    graph_repo.find_resolution_candidates.return_value = [
        {"id": "cand-1", "canonical_name": "Somewhat Similar B"}
    ]
    sparse_facts = {"child_of": [], "born_in": [], "died_in": [], "neighbors": []}
    graph_repo.get_entity_facts.return_value = sparse_facts

    with (
        patch(
            "app.services.entity_resolution_service.GraphResolutionQueueRepository"
        ) as MockQueueRepo,
        patch(
            "app.services.entity_resolution_service.GraphResolutionReviewsRepository"
        ) as MockReviewsRepo,
        patch(
            "app.services.entity_resolution_service.SystemConfigsRepository"
        ) as MockConfigRepo,
        patch("app.services.entity_resolution_service._graded_score", return_value=0.5),
        patch(
            "app.services.entity_resolution_service._gray_zone_judge",
            new=AsyncMock(
                return_value=EntityResolutionVerdict(
                    verdict="unsure", confidence=0.4, reasoning="not sure"
                )
            ),
        ) as mock_judge,
        patch(
            "app.services.entity_resolution_service.execute_merge", new=AsyncMock()
        ) as mock_execute_merge,
        patch(
            "app.services.entity_resolution_service.update_alias_cache", new=AsyncMock()
        ),
    ):
        queue_repo = AsyncMock()
        MockQueueRepo.return_value = queue_repo
        reviews_repo = AsyncMock()
        MockReviewsRepo.return_value = reviews_repo
        config_repo = AsyncMock()
        config_repo.get_value.return_value = "5"
        MockConfigRepo.return_value = config_repo

        await resolve_entity(session, graph_repo, "e1")

        mock_judge.assert_called_once()
        mock_execute_merge.assert_not_called()
        reviews_repo.create_review.assert_called_once()
        assert reviews_repo.create_review.call_args[0][0] == "e1"
        assert reviews_repo.create_review.call_args[0][1] == "cand-1"
        assert reviews_repo.create_review.call_args[0][4] == "unsure"
        queue_repo.mark_status.assert_called_once_with("e1", "needs_review")


@pytest.mark.asyncio
async def test_resolve_entity_gray_zone_confident_same_merges():
    session = AsyncMock()
    graph_repo = AsyncMock()
    graph_repo.get_entity_by_id.side_effect = lambda eid: {
        "e1": {
            "id": "e1",
            "canonical_name": "A",
            "aliases": [],
            "scope": "nonfiction",
            "book_id": None,
        },
        "cand-1": {"id": "cand-1", "canonical_name": "B"},
    }.get(eid)
    graph_repo.find_resolution_candidates.return_value = [
        {"id": "cand-1", "canonical_name": "B"}
    ]
    sparse_facts = {"child_of": [], "born_in": [], "died_in": [], "neighbors": []}
    graph_repo.get_entity_facts.return_value = sparse_facts

    with (
        patch(
            "app.services.entity_resolution_service.GraphResolutionQueueRepository"
        ) as MockQueueRepo,
        patch(
            "app.services.entity_resolution_service.GraphResolutionReviewsRepository"
        ) as MockReviewsRepo,
        patch(
            "app.services.entity_resolution_service.SystemConfigsRepository"
        ) as MockConfigRepo,
        patch("app.services.entity_resolution_service._graded_score", return_value=0.5),
        patch(
            "app.services.entity_resolution_service._gray_zone_judge",
            new=AsyncMock(
                return_value=EntityResolutionVerdict(
                    verdict="same", confidence=0.9, reasoning="clearly the same"
                )
            ),
        ),
        patch(
            "app.services.entity_resolution_service.execute_merge", new=AsyncMock()
        ) as mock_execute_merge,
        patch(
            "app.services.entity_resolution_service.update_alias_cache", new=AsyncMock()
        ),
    ):
        queue_repo = AsyncMock()
        MockQueueRepo.return_value = queue_repo
        reviews_repo = AsyncMock()
        MockReviewsRepo.return_value = reviews_repo
        config_repo = AsyncMock()
        config_repo.get_value.return_value = "5"
        MockConfigRepo.return_value = config_repo

        await resolve_entity(session, graph_repo, "e1")

        mock_execute_merge.assert_called_once()
        reviews_repo.create_review.assert_not_called()
        queue_repo.mark_status.assert_called_once_with("e1", "succeeded")


@pytest.mark.asyncio
async def test_gray_zone_judge_defaults_to_unsure_on_exception():
    from app.services.entity_resolution_service import _gray_zone_judge

    config_repo = AsyncMock()
    config_repo.get_value.return_value = "gemini-3.1-flash-lite"

    with patch("app.services.entity_resolution_service.genai") as mock_genai:
        mock_genai.Client.side_effect = RuntimeError("boom")
        verdict = await _gray_zone_judge({}, {}, {}, {}, config_repo)
        assert verdict.verdict == "unsure"
        assert verdict.confidence == 0.0
