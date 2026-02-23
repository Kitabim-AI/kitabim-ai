"""Contact form submission API endpoints"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.db.repositories.contact_submissions import ContactSubmissionsRepository
from app.models.schemas import (
    ContactSubmissionCreate,
    ContactSubmissionPublic,
    ContactSubmissionAdmin
)
from app.auth.dependencies import require_admin

router = APIRouter()


@router.post("/submit", response_model=ContactSubmissionPublic, status_code=status.HTTP_201_CREATED)
async def submit_contact_form(
    submission: ContactSubmissionCreate,
    session: AsyncSession = Depends(get_session),
):
    """
    Submit a contact form from the Join Us page.

    Public endpoint - no authentication required.
    """
    repo = ContactSubmissionsRepository(session)

    contact = await repo.create_submission(
        name=submission.name,
        email=submission.email,
        interest=submission.interest,
        message=submission.message
    )

    await session.commit()

    return ContactSubmissionPublic.model_validate(contact)


@router.get("/admin/submissions", response_model=List[ContactSubmissionAdmin])
async def get_contact_submissions(
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    current_user = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """
    Get all contact submissions with optional filtering.

    Admin-only endpoint.

    Query params:
    - status: Filter by submission status (new, reviewed, contacted, archived)
    - limit: Maximum number of results to return (default 100)
    - offset: Number of results to skip (default 0)
    """
    repo = ContactSubmissionsRepository(session)

    submissions = await repo.find_many(
        status=status,
        skip=offset,
        limit=limit
    )

    return [ContactSubmissionAdmin.model_validate(sub) for sub in submissions]
