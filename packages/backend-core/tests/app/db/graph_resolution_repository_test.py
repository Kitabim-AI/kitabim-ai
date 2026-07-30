import pytest
from unittest.mock import AsyncMock, MagicMock
from app.db.repositories.graph_resolution_repository import (
    GraphMergeLogRepository,
    GraphResolutionQueueRepository,
    GraphResolutionReviewsRepository,
)


@pytest.mark.asyncio
async def test_bulk_enqueue_empty_rows_noop():
    session = AsyncMock()
    repo = GraphResolutionQueueRepository(session)
    await repo.bulk_enqueue([])
    session.execute.assert_not_called()
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_bulk_enqueue_inserts_rows():
    session = AsyncMock()
    repo = GraphResolutionQueueRepository(session)
    rows = [
        {"entity_id": "e1", "scope": "nonfiction", "book_id": None, "sort_year": None}
    ]
    await repo.bulk_enqueue(rows)
    session.execute.assert_called_once()
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_claim_batch_marks_claimed_rows_in_progress():
    session = AsyncMock()
    repo = GraphResolutionQueueRepository(session)

    claimed_row = MagicMock(id=1, entity_id="e1", scope="nonfiction")
    select_result = MagicMock()
    select_result.scalars.return_value.all.return_value = [claimed_row]
    session.execute.side_effect = [select_result, MagicMock()]

    rows = await repo.claim_batch(10)

    assert rows == [claimed_row]
    assert session.execute.call_count == 2
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_claim_batch_empty_skips_update():
    session = AsyncMock()
    repo = GraphResolutionQueueRepository(session)

    select_result = MagicMock()
    select_result.scalars.return_value.all.return_value = []
    session.execute.return_value = select_result

    rows = await repo.claim_batch(10)

    assert rows == []
    assert session.execute.call_count == 1
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_requeue_or_cap_requeues_under_cap():
    session = AsyncMock()
    repo = GraphResolutionQueueRepository(session)
    repo.get_by_entity_id = AsyncMock(return_value=MagicMock(pass_count=1))

    requeued = await repo.requeue_or_cap("e1", max_passes=5)

    assert requeued is True
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_requeue_or_cap_forces_needs_review_at_cap():
    session = AsyncMock()
    repo = GraphResolutionQueueRepository(session)
    repo.get_by_entity_id = AsyncMock(return_value=MagicMock(pass_count=5))
    repo.mark_status = AsyncMock()

    requeued = await repo.requeue_or_cap("e1", max_passes=5)

    assert requeued is False
    repo.mark_status.assert_called_once_with("e1", "needs_review")


@pytest.mark.asyncio
async def test_requeue_or_cap_missing_row_returns_false():
    session = AsyncMock()
    repo = GraphResolutionQueueRepository(session)
    repo.get_by_entity_id = AsyncMock(return_value=None)

    requeued = await repo.requeue_or_cap("missing", max_passes=5)
    assert requeued is False


@pytest.mark.asyncio
async def test_list_pending_returns_rows_and_total():
    session = AsyncMock()
    repo = GraphResolutionReviewsRepository(session)

    count_result = MagicMock()
    count_result.scalar_one.return_value = 3
    rows_result = MagicMock()
    rows_result.scalars.return_value.all.return_value = ["row1", "row2"]
    session.execute.side_effect = [count_result, rows_result]

    rows, total = await repo.list_pending(skip=0, limit=20)
    assert rows == ["row1", "row2"]
    assert total == 3


@pytest.mark.asyncio
async def test_set_status_updates_review():
    session = AsyncMock()
    repo = GraphResolutionReviewsRepository(session)
    review = MagicMock(status="pending")
    repo.get = AsyncMock(return_value=review)

    updated = await repo.set_status(1, "approved", "user-1")

    assert updated is review
    assert review.status == "approved"
    assert review.reviewed_by == "user-1"
    assert review.reviewed_at is not None
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_set_status_missing_review_returns_none():
    session = AsyncMock()
    repo = GraphResolutionReviewsRepository(session)
    repo.get = AsyncMock(return_value=None)

    updated = await repo.set_status(999, "approved", "user-1")
    assert updated is None


@pytest.mark.asyncio
async def test_log_merge_creates_entry():
    session = AsyncMock()
    repo = GraphMergeLogRepository(session)

    await repo.log_merge(
        kept_entity_id="keep-1",
        removed_entity_id="remove-1",
        removed_entity_snapshot={"canonical_name": "X"},
        removed_edges_snapshot=[],
        performed_by="admin@example.com",
    )
    session.add.assert_called_once()
    added_entry = session.add.call_args[0][0]
    assert added_entry.kept_entity_id == "keep-1"
    assert added_entry.removed_entity_id == "remove-1"
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_mark_reverted_sets_timestamp():
    session = AsyncMock()
    repo = GraphMergeLogRepository(session)
    entry = MagicMock(reverted_at=None)
    repo.get = AsyncMock(return_value=entry)

    updated = await repo.mark_reverted(1)
    assert updated is entry
    assert entry.reverted_at is not None


@pytest.mark.asyncio
async def test_mark_reverted_missing_entry_returns_none():
    session = AsyncMock()
    repo = GraphMergeLogRepository(session)
    repo.get = AsyncMock(return_value=None)

    updated = await repo.mark_reverted(999)
    assert updated is None


@pytest.mark.asyncio
async def test_resolve_reviews_for_merge_updates_pending_reviews():
    import uuid

    session = AsyncMock()
    repo = GraphResolutionReviewsRepository(session)

    e1 = str(uuid.uuid4())
    e2 = str(uuid.uuid4())

    select_result = MagicMock()
    select_result.scalars.return_value.all.return_value = []
    session.execute.return_value = select_result

    await repo.resolve_reviews_for_merge(e1, e2, reviewed_by="user-123")

    assert session.execute.call_count >= 2
    session.commit.assert_called_once()
