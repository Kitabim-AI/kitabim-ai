import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock, MagicMock, patch

BACKEND_DIR = str(Path(__file__).resolve().parents[3])
BACKEND_CORE_DIR = str(
    Path(__file__).resolve().parents[5] / "packages" / "backend-core"
)


def setup_paths():
    for m in list(sys.modules.keys()):
        if m == "api" or m.startswith("api."):
            del sys.modules[m]
    for p in [BACKEND_CORE_DIR, BACKEND_DIR]:
        if p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)


@pytest.mark.asyncio
async def test_split_entity_success():
    setup_paths()
    from api.endpoints.graph_admin_router import split_entity, SplitEntityRequest

    mock_user = MagicMock()
    mock_user.email = "admin@example.com"
    mock_request = SplitEntityRequest(split_point_edge_id="edge-1")

    mock_repo = MagicMock()
    mock_repo.close = AsyncMock()

    with (
        patch(
            "app.db.repositories.graph_repository.GraphRepository",
            return_value=mock_repo,
        ),
        patch(
            "app.services.entity_resolution_service.execute_split",
            new=AsyncMock(
                return_value={
                    "new_entity_id": "new-1",
                    "moved_edge_ids": ["edge-2"],
                    "unclustered_edge_ids": ["edge-3"],
                }
            ),
        ) as mock_execute_split,
    ):
        response = await split_entity(
            entity_id="entity-1", request=mock_request, current_user=mock_user
        )

    assert response["status"] == "success"
    assert response["newEntityId"] == "new-1"
    assert response["movedEdgeIds"] == ["edge-2"]
    assert response["unclusteredEdgeIds"] == ["edge-3"]
    mock_execute_split.assert_called_once_with(mock_repo, "entity-1", "edge-1")


@pytest.mark.asyncio
async def test_split_entity_missing_edge_returns_400():
    setup_paths()
    from api.endpoints.graph_admin_router import split_entity, SplitEntityRequest

    mock_user = MagicMock()
    mock_request = SplitEntityRequest(split_point_edge_id="missing-edge")
    mock_repo = MagicMock()
    mock_repo.close = AsyncMock()

    with (
        patch(
            "app.db.repositories.graph_repository.GraphRepository",
            return_value=mock_repo,
        ),
        patch(
            "app.services.entity_resolution_service.execute_split",
            new=AsyncMock(side_effect=ValueError("Edge not found")),
        ),
    ):
        with pytest.raises(HTTPException) as excinfo:
            await split_entity(
                entity_id="entity-1", request=mock_request, current_user=mock_user
            )
    assert excinfo.value.status_code == 400


@pytest.mark.asyncio
async def test_unmerge_entity_success():
    setup_paths()
    from api.endpoints.graph_admin_router import unmerge_entity

    mock_user = MagicMock()
    mock_user.email = "admin@example.com"
    mock_session = AsyncMock()
    mock_repo = MagicMock()
    mock_repo.close = AsyncMock()

    with (
        patch(
            "app.db.repositories.graph_repository.GraphRepository",
            return_value=mock_repo,
        ),
        patch(
            "app.services.entity_resolution_service.execute_unmerge",
            new=AsyncMock(
                return_value={
                    "restored_entity_id": "restored-1",
                    "unrecoverable_edge_ids": [],
                }
            ),
        ) as mock_execute_unmerge,
    ):
        response = await unmerge_entity(
            merge_log_id=42, current_user=mock_user, session=mock_session
        )

    assert response["status"] == "success"
    assert response["restoredEntityId"] == "restored-1"
    mock_execute_unmerge.assert_called_once_with(mock_session, mock_repo, 42)


@pytest.mark.asyncio
async def test_unmerge_entity_not_found_returns_400():
    setup_paths()
    from api.endpoints.graph_admin_router import unmerge_entity

    mock_user = MagicMock()
    mock_session = AsyncMock()
    mock_repo = MagicMock()
    mock_repo.close = AsyncMock()

    with (
        patch(
            "app.db.repositories.graph_repository.GraphRepository",
            return_value=mock_repo,
        ),
        patch(
            "app.services.entity_resolution_service.execute_unmerge",
            new=AsyncMock(side_effect=ValueError("does not exist")),
        ),
    ):
        with pytest.raises(HTTPException) as excinfo:
            await unmerge_entity(
                merge_log_id=999, current_user=mock_user, session=mock_session
            )
    assert excinfo.value.status_code == 400


@pytest.mark.asyncio
async def test_list_review_queue_returns_paginated_items():
    setup_paths()
    from api.endpoints.graph_admin_router import list_review_queue

    mock_user = MagicMock()
    mock_session = AsyncMock()

    review = MagicMock(
        id=1,
        entity_a_id="a1",
        entity_b_id="b1",
        scope="nonfiction",
        evidence={"reasoning": "similar"},
        suggested_action="merge",
        status="pending",
        created_at="2026-01-01T00:00:00Z",
    )

    with patch(
        "api.endpoints.graph_admin_router.GraphResolutionReviewsRepository"
    ) as MockReviewsRepo:
        reviews_repo = AsyncMock()
        reviews_repo.list_pending.return_value = ([review], 1)
        MockReviewsRepo.return_value = reviews_repo

        response = await list_review_queue(
            skip=0, limit=20, current_user=mock_user, session=mock_session
        )

    assert response["total"] == 1
    assert response["items"][0]["id"] == 1
    assert response["items"][0]["suggestedAction"] == "merge"


@pytest.mark.asyncio
async def test_approve_review_merge_action_executes_merge():
    setup_paths()
    from api.endpoints.graph_admin_router import approve_review

    mock_user = MagicMock()
    mock_user.email = "admin@example.com"
    mock_user.id = "admin-id"
    mock_session = AsyncMock()

    review = MagicMock(
        id=1,
        status="pending",
        suggested_action="merge",
        entity_a_id="a1",
        entity_b_id="b1",
    )
    updated_review = MagicMock(id=1, status="approved")

    with (
        patch(
            "api.endpoints.graph_admin_router.GraphResolutionReviewsRepository"
        ) as MockReviewsRepo,
        patch("app.db.repositories.graph_repository.GraphRepository") as MockGraphRepo,
        patch(
            "app.services.entity_resolution_service.execute_merge", new=AsyncMock()
        ) as mock_execute_merge,
    ):
        reviews_repo = AsyncMock()
        reviews_repo.get.return_value = review
        reviews_repo.set_status.return_value = updated_review
        MockReviewsRepo.return_value = reviews_repo
        MockGraphRepo.return_value = AsyncMock()

        response = await approve_review(
            review_id=1, current_user=mock_user, session=mock_session
        )

    assert response["status"] == "success"
    mock_execute_merge.assert_called_once_with(
        mock_session,
        MockGraphRepo.return_value,
        keep_id="a1",
        remove_id="b1",
        performed_by="admin@example.com",
        user_id="admin-id",
    )
    reviews_repo.set_status.assert_called_once_with(1, "approved", "admin-id")


@pytest.mark.asyncio
async def test_approve_review_missing_returns_404():
    setup_paths()
    from api.endpoints.graph_admin_router import approve_review

    mock_user = MagicMock()
    mock_session = AsyncMock()

    with patch(
        "api.endpoints.graph_admin_router.GraphResolutionReviewsRepository"
    ) as MockReviewsRepo:
        reviews_repo = AsyncMock()
        reviews_repo.get.return_value = None
        MockReviewsRepo.return_value = reviews_repo

        with pytest.raises(HTTPException) as excinfo:
            await approve_review(
                review_id=999, current_user=mock_user, session=mock_session
            )
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_approve_review_already_decided_returns_400():
    setup_paths()
    from api.endpoints.graph_admin_router import approve_review

    mock_user = MagicMock()
    mock_session = AsyncMock()
    review = MagicMock(id=1, status="approved")

    with patch(
        "api.endpoints.graph_admin_router.GraphResolutionReviewsRepository"
    ) as MockReviewsRepo:
        reviews_repo = AsyncMock()
        reviews_repo.get.return_value = review
        MockReviewsRepo.return_value = reviews_repo

        with pytest.raises(HTTPException) as excinfo:
            await approve_review(
                review_id=1, current_user=mock_user, session=mock_session
            )
    assert excinfo.value.status_code == 400


@pytest.mark.asyncio
async def test_reject_review_success():
    setup_paths()
    from api.endpoints.graph_admin_router import reject_review

    mock_user = MagicMock()
    mock_user.id = "admin-id"
    mock_session = AsyncMock()
    review = MagicMock(id=1, status="pending")
    updated_review = MagicMock(id=1, status="rejected")

    with patch(
        "api.endpoints.graph_admin_router.GraphResolutionReviewsRepository"
    ) as MockReviewsRepo:
        reviews_repo = AsyncMock()
        reviews_repo.get.return_value = review
        reviews_repo.set_status.return_value = updated_review
        MockReviewsRepo.return_value = reviews_repo

        response = await reject_review(
            review_id=1, current_user=mock_user, session=mock_session
        )

    assert response["status"] == "success"
    reviews_repo.set_status.assert_called_once_with(1, "rejected", "admin-id")
