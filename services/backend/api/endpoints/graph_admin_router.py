"""Admin endpoints for Knowledge Graph entity resolution v2: split, unmerge, and the
review queue for gray-zone resolution outcomes. Mounted at /api/admin/graph.

Merge (id-keyed) stays on the existing `/api/books/graph/merge` endpoint in
books_router.py — these three operations are new in design v2 §5.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.db.repositories.graph_repository import GraphRepository
from app.db.repositories.graph_resolution_repository import (
    GraphResolutionReviewsRepository,
)
from app.models.schemas import to_camel
from app.models.user import User
from app.utils.observability import log_json
from auth.dependencies import require_admin

logger = logging.getLogger("app.api.graph_admin")

router = APIRouter()


class SplitEntityRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    split_point_edge_id: str


@router.post("/entities/{entity_id}/split")
async def split_entity(
    entity_id: str,
    request: SplitEntityRequest,
    current_user: User = Depends(require_admin),
):
    """Split an over-merged entity at `split_point_edge_id` via connected-component
    partitioning (design v2 §5). Edges that don't cluster with either anchor are left
    on the original node and returned as `unclusteredEdgeIds` for manual reassignment.
    """
    from app.db.repositories.graph_repository import GraphRepository
    from app.services.entity_resolution_service import execute_split

    graph_repo = GraphRepository()
    try:
        result = await execute_split(graph_repo, entity_id, request.split_point_edge_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        log_json(
            logger,
            logging.ERROR,
            "failed to split entity",
            entity_id=entity_id,
            error=str(exc),
        )
        raise HTTPException(
            status_code=500, detail="Internal server error during entity split."
        )
    finally:
        await graph_repo.close()

    log_json(
        logger,
        logging.INFO,
        "entity split",
        entity_id=entity_id,
        new_entity_id=result.get("new_entity_id"),
        user=current_user.email,
    )
    return {
        "status": "success",
        "newEntityId": result.get("new_entity_id"),
        "movedEdgeIds": result.get("moved_edge_ids", []),
        "unclusteredEdgeIds": result.get("unclustered_edge_ids", []),
    }


@router.post("/merge-log/{merge_log_id}/unmerge")
async def unmerge_entity(
    merge_log_id: int,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Reverts a merge by its `graph_merge_log` id (design v2 §5). Restores the
    removed node and re-points its original edges (matched by stable edge id) back
    onto it — edges that collided with a pre-existing edge on the kept node during
    the merge cannot be re-pointed (see `unrecoverableEdgeIds`, a known accepted gap).
    """
    from app.db.repositories.graph_repository import GraphRepository
    from app.services.entity_resolution_service import execute_unmerge

    graph_repo = GraphRepository()
    try:
        result = await execute_unmerge(session, graph_repo, merge_log_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        log_json(
            logger,
            logging.ERROR,
            "failed to unmerge entity",
            merge_log_id=merge_log_id,
            error=str(exc),
        )
        raise HTTPException(
            status_code=500, detail="Internal server error during unmerge."
        )
    finally:
        await graph_repo.close()

    log_json(
        logger,
        logging.INFO,
        "entity unmerge",
        merge_log_id=merge_log_id,
        restored_entity_id=result.get("restored_entity_id"),
        user=current_user.email,
    )
    return {
        "status": "success",
        "restoredEntityId": result.get("restored_entity_id"),
        "unrecoverableEdgeIds": result.get("unrecoverable_edge_ids", []),
    }


from sqlalchemy import text
import re


async def _resolve_entity_name(
    entity_id_str: str,
    names_map: dict,
    evidence: dict,
    name_key: str,
    session: AsyncSession,
) -> str:
    # 1. From Neo4j names map
    if names_map.get(entity_id_str):
        return names_map[entity_id_str]

    # 2. From evidence dictionary
    if isinstance(evidence, dict) and evidence.get(name_key):
        return evidence[name_key]

    # 3. From graph_merge_log if the entity was already merged
    try:
        stmt = text("""
            SELECT removed_entity_snapshot->>'canonical_name' AS name
            FROM graph_merge_log
            WHERE removed_entity_id = :eid
            LIMIT 1
        """)
        res = await session.execute(stmt, {"eid": entity_id_str})
        row = res.scalar()
        if row:
            return row
    except Exception:
        pass

    # 4. From reasoning text if single-quoted names exist
    reasoning = evidence.get("reasoning", "") if isinstance(evidence, dict) else ""
    if reasoning:
        quotes = re.findall(r"'([^']+)'", reasoning)
        if quotes:
            return quotes[0]

    # 5. Fallback display label
    return f"Entity ({entity_id_str[:8]})"


@router.get("/review-queue")
async def list_review_queue(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Paginated list of pending gray-zone resolution reviews (design v2 §4.1/§5)."""
    reviews_repo = GraphResolutionReviewsRepository(session)
    rows, total = await reviews_repo.list_pending(skip=skip, limit=limit)

    entity_ids = list(
        set([str(r.entity_a_id) for r in rows] + [str(r.entity_b_id) for r in rows])
    )
    graph_repo = GraphRepository()
    names_map = await graph_repo.get_entity_names_by_ids(entity_ids)

    items = []
    for r in rows:
        ent_a_id = str(r.entity_a_id)
        ent_b_id = str(r.entity_b_id)
        name_a = await _resolve_entity_name(
            ent_a_id, names_map, r.evidence, "entity_a_name", session
        )
        name_b = await _resolve_entity_name(
            ent_b_id, names_map, r.evidence, "entity_b_name", session
        )
        items.append(
            {
                "id": r.id,
                "entityAId": ent_a_id,
                "entityBId": ent_b_id,
                "entityAName": name_a,
                "entityBName": name_b,
                "scope": r.scope,
                "evidence": r.evidence,
                "suggestedAction": r.suggested_action,
                "status": r.status,
                "createdAt": r.created_at,
            }
        )

    return {
        "items": items,
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.post("/review-queue/{review_id}/approve")
async def approve_review(
    review_id: int,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Approves a pending review and executes its `suggestedAction` (merge only —
    'split'/'unsure' suggestions require the admin to call split/unmerge explicitly
    with the specific edge/log id, since neither can be inferred from the review row
    alone).
    """
    from app.db.repositories.graph_repository import GraphRepository
    from app.services.entity_resolution_service import execute_merge

    reviews_repo = GraphResolutionReviewsRepository(session)
    review = await reviews_repo.get(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    if review.status != "pending":
        raise HTTPException(status_code=400, detail="Review has already been decided.")

    if review.suggested_action == "merge":
        graph_repo = GraphRepository()
        try:
            await execute_merge(
                session,
                graph_repo,
                keep_id=str(review.entity_a_id),
                remove_id=str(review.entity_b_id),
                performed_by=current_user.email,
                user_id=current_user.id,
            )
        finally:
            await graph_repo.close()

    updated = await reviews_repo.set_status(review_id, "approved", current_user.id)
    log_json(
        logger,
        logging.INFO,
        "review approved",
        review_id=review_id,
        suggested_action=review.suggested_action,
        user=current_user.email,
    )
    return {"status": "success", "review": {"id": updated.id, "status": updated.status}}


@router.post("/review-queue/{review_id}/reject")
async def reject_review(
    review_id: int,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Rejects a pending review — leaves both entities exactly as they are."""
    reviews_repo = GraphResolutionReviewsRepository(session)
    review = await reviews_repo.get(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    if review.status != "pending":
        raise HTTPException(status_code=400, detail="Review has already been decided.")

    updated = await reviews_repo.set_status(review_id, "rejected", current_user.id)
    log_json(
        logger,
        logging.INFO,
        "review rejected",
        review_id=review_id,
        user=current_user.email,
    )
    return {"status": "success", "review": {"id": updated.id, "status": updated.status}}
