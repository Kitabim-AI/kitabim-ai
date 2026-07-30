"""Postgres repositories coordinating Neo4j entity resolution (design v2 §2/§4/§5).

Postgres owns queue/review/audit state; Neo4j owns the entity data itself.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import GraphMergeLog, GraphResolutionQueue, GraphResolutionReview
from app.db.repositories.base_repository import BaseRepository


class GraphResolutionQueueRepository(BaseRepository[GraphResolutionQueue]):
    """CRUD + claiming for `graph_resolution_queue`."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, GraphResolutionQueue)

    async def bulk_enqueue(self, rows: List[Dict[str, Any]]) -> None:
        """Insert queue rows for freshly extracted entities.

        `entity_id` is unique — `ON CONFLICT DO NOTHING` since a fresh uuid4 is
        assigned per entity at extraction time and is never reused across runs.
        """
        if not rows:
            return
        stmt = pg_insert(GraphResolutionQueue).values(rows)
        stmt = stmt.on_conflict_do_nothing(index_elements=["entity_id"])
        await self.session.execute(stmt)
        await self.session.commit()

    async def claim_batch(self, batch_size: int) -> List[GraphResolutionQueue]:
        """Atomically claim up to `batch_size` idle rows, oldest generation first."""
        stmt = (
            select(GraphResolutionQueue)
            .where(GraphResolutionQueue.status == "idle")
            .order_by(
                GraphResolutionQueue.scope,
                GraphResolutionQueue.sort_year.asc().nulls_last(),
            )
            .with_for_update(skip_locked=True)
            .limit(batch_size)
        )
        result = await self.session.execute(stmt)
        rows = list(result.scalars().all())
        if rows:
            ids = [r.id for r in rows]
            await self.session.execute(
                update(GraphResolutionQueue)
                .where(GraphResolutionQueue.id.in_(ids))
                .values(status="in_progress", last_updated=func.now())
            )
            await self.session.commit()
        return rows

    async def get_by_entity_id(self, entity_id: str) -> Optional[GraphResolutionQueue]:
        result = await self.session.execute(
            select(GraphResolutionQueue).where(
                GraphResolutionQueue.entity_id == entity_id
            )
        )
        return result.scalar_one_or_none()

    async def mark_status(self, entity_id: str, status: str) -> None:
        await self.session.execute(
            update(GraphResolutionQueue)
            .where(GraphResolutionQueue.entity_id == entity_id)
            .values(status=status, last_updated=func.now())
        )
        await self.session.commit()

    async def delete_by_entity_id(self, entity_id: str) -> None:
        """Removes the queue row for an entity that no longer exists in Neo4j
        (merged away) — otherwise every future scan's existence check would mark
        it `failed` forever."""
        from sqlalchemy import delete as sa_delete

        await self.session.execute(
            sa_delete(GraphResolutionQueue).where(
                GraphResolutionQueue.entity_id == entity_id
            )
        )
        await self.session.commit()

    async def requeue_or_cap(self, entity_id: str, max_passes: int) -> bool:
        """Re-queues `entity_id` (status='idle', pass_count+1) if still under
        `max_passes`; otherwise force-marks it `needs_review` so a flip-flopping
        node stops looping forever. Returns True if re-queued, False if capped.
        No-op (returns False) if the row no longer exists.
        """
        row = await self.get_by_entity_id(entity_id)
        if not row:
            return False
        if row.pass_count >= max_passes:
            await self.mark_status(entity_id, "needs_review")
            return False
        await self.session.execute(
            update(GraphResolutionQueue)
            .where(GraphResolutionQueue.entity_id == entity_id)
            .values(
                status="idle",
                pass_count=GraphResolutionQueue.pass_count + 1,
                last_updated=func.now(),
            )
        )
        await self.session.commit()
        return True


class GraphResolutionReviewsRepository(BaseRepository[GraphResolutionReview]):
    """CRUD for the admin review queue (`graph_resolution_reviews`)."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, GraphResolutionReview)

    async def create_review(
        self,
        entity_a_id: str,
        entity_b_id: str,
        scope: str,
        evidence: Dict[str, Any],
        suggested_action: str,
    ) -> GraphResolutionReview:
        review = GraphResolutionReview(
            entity_a_id=entity_a_id,
            entity_b_id=entity_b_id,
            scope=scope,
            evidence=evidence,
            suggested_action=suggested_action,
        )
        self.session.add(review)
        await self.session.commit()
        await self.session.refresh(review)
        return review

    async def list_pending(
        self, skip: int = 0, limit: int = 20
    ) -> Tuple[List[GraphResolutionReview], int]:
        count_stmt = (
            select(func.count())
            .select_from(GraphResolutionReview)
            .where(GraphResolutionReview.status == "pending")
        )
        total = (await self.session.execute(count_stmt)).scalar_one()
        stmt = (
            select(GraphResolutionReview)
            .where(GraphResolutionReview.status == "pending")
            .order_by(GraphResolutionReview.created_at.asc())
            .offset(skip)
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows), total

    async def set_status(
        self, review_id: int, status: str, reviewed_by: Optional[str]
    ) -> Optional[GraphResolutionReview]:
        review = await self.get(review_id)
        if not review:
            return None
        review.status = status
        review.reviewed_by = reviewed_by
        review.reviewed_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(review)
        return review

    async def resolve_reviews_for_merge(
        self,
        keep_id: str,
        remove_id: str,
        reviewed_by: Optional[str] = None,
    ) -> None:
        """Resolves pending review queue entries when `remove_id` is merged into `keep_id`:
        1. Marks any pending reviews between keep_id and remove_id (in either order)
           as 'approved'.
        2. Re-points any remaining pending reviews involving remove_id to keep_id,
           or marks them 'approved' if a review for (keep_id, other_id) already exists.
        """
        try:
            keep_uuid = uuid.UUID(keep_id) if isinstance(keep_id, str) else keep_id
            remove_uuid = (
                uuid.UUID(remove_id) if isinstance(remove_id, str) else remove_id
            )
        except ValueError:
            return

        now = datetime.now(timezone.utc)

        # 1. Direct reviews between keep_id and remove_id
        direct_stmt = (
            update(GraphResolutionReview)
            .where(
                GraphResolutionReview.status == "pending",
                (
                    (GraphResolutionReview.entity_a_id == keep_uuid)
                    & (GraphResolutionReview.entity_b_id == remove_uuid)
                )
                | (
                    (GraphResolutionReview.entity_a_id == remove_uuid)
                    & (GraphResolutionReview.entity_b_id == keep_uuid)
                ),
            )
            .values(
                status="approved",
                reviewed_by=reviewed_by,
                reviewed_at=now,
            )
        )
        await self.session.execute(direct_stmt)

        # 2. Other pending reviews involving remove_id
        stmt = select(GraphResolutionReview).where(
            GraphResolutionReview.status == "pending",
            (GraphResolutionReview.entity_a_id == remove_uuid)
            | (GraphResolutionReview.entity_b_id == remove_uuid),
        )
        result = await self.session.execute(stmt)
        remaining_reviews = list(result.scalars().all())

        for review in remaining_reviews:
            other_id = (
                review.entity_b_id
                if review.entity_a_id == remove_uuid
                else review.entity_a_id
            )

            if other_id == keep_uuid:
                review.status = "approved"
                review.reviewed_by = reviewed_by
                review.reviewed_at = now
                continue

            existing_stmt = select(GraphResolutionReview).where(
                GraphResolutionReview.status == "pending",
                GraphResolutionReview.id != review.id,
                (
                    (GraphResolutionReview.entity_a_id == keep_uuid)
                    & (GraphResolutionReview.entity_b_id == other_id)
                )
                | (
                    (GraphResolutionReview.entity_a_id == other_id)
                    & (GraphResolutionReview.entity_b_id == keep_uuid)
                ),
            )
            existing_res = await self.session.execute(existing_stmt)
            existing_review = existing_res.scalar_one_or_none()

            if existing_review:
                review.status = "approved"
                review.reviewed_by = reviewed_by
                review.reviewed_at = now
            else:
                if review.entity_a_id == remove_uuid:
                    review.entity_a_id = keep_uuid
                if review.entity_b_id == remove_uuid:
                    review.entity_b_id = keep_uuid

        await self.session.commit()


class GraphMergeLogRepository(BaseRepository[GraphMergeLog]):
    """CRUD for the merge audit log (`graph_merge_log`), enabling unmerge."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, GraphMergeLog)

    async def log_merge(
        self,
        kept_entity_id: str,
        removed_entity_id: str,
        removed_entity_snapshot: Dict[str, Any],
        removed_edges_snapshot: List[Dict[str, Any]],
        performed_by: Optional[str],
    ) -> GraphMergeLog:
        entry = GraphMergeLog(
            kept_entity_id=kept_entity_id,
            removed_entity_id=removed_entity_id,
            removed_entity_snapshot=removed_entity_snapshot,
            removed_edges_snapshot=removed_edges_snapshot,
            performed_by=performed_by,
        )
        self.session.add(entry)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry

    async def mark_reverted(self, merge_log_id: int) -> Optional[GraphMergeLog]:
        entry = await self.get(merge_log_id)
        if not entry:
            return None
        entry.reverted_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry
