"""Contact submissions repository for Join Us form"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import ContactSubmission
from app.db.repositories.base_repository import BaseRepository


class ContactSubmissionsRepository(BaseRepository[ContactSubmission]):
    """Repository for contact form submissions"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, ContactSubmission)

    async def create_submission(
        self, name: str, email: str, interest: str, message: str
    ) -> ContactSubmission:
        """Create a new contact submission"""
        submission = ContactSubmission(
            name=name, email=email, interest=interest, message=message, status="new"
        )
        self.session.add(submission)
        await self.session.flush()
        await self.session.refresh(submission)
        return submission

    async def find_many(
        self, status: Optional[str] = None, skip: int = 0, limit: int = 100
    ) -> List[ContactSubmission]:
        """Find contact submissions with optional filtering by status"""
        stmt = select(ContactSubmission)

        if status:
            stmt = stmt.where(ContactSubmission.status == status)

        stmt = (
            stmt.order_by(ContactSubmission.created_at.desc()).offset(skip).limit(limit)
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, status: Optional[str] = None) -> int:
        """Count contact submissions, optionally filtered by status"""
        stmt = select(func.count()).select_from(ContactSubmission)

        if status:
            stmt = stmt.where(ContactSubmission.status == status)

        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def update_submission(
        self,
        submission_id: int,
        *,
        status: Optional[str] = None,
        admin_notes: Optional[str] = None,
        update_notes: bool = False,
        reviewed_by: Optional[str] = None,
    ) -> Optional[ContactSubmission]:
        """Update status and/or admin notes for a contact submission."""
        values: dict = {}
        if status is not None:
            values["status"] = status
            if status == "new":
                values["reviewed_by"] = None
                values["reviewed_at"] = None
            else:
                values["reviewed_by"] = reviewed_by
                values["reviewed_at"] = func.now()

        if update_notes:
            cleaned_notes = admin_notes.strip() if admin_notes else None
            values["admin_notes"] = cleaned_notes or None

        return await self.update_one(submission_id, **values)


def get_contact_submissions_repository(
    session: AsyncSession,
) -> ContactSubmissionsRepository:
    """Factory function for dependency injection"""
    return ContactSubmissionsRepository(session)
