"""Contact form submission API endpoints"""

from __future__ import annotations

from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.db.repositories.contact_submissions_repository import (
    ContactSubmissionsRepository,
)
from app.models.schemas import (
    ContactSubmissionCreate,
    ContactSubmissionPublic,
    ContactSubmissionAdmin,
    ContactSubmissionUpdate,
)
from auth.dependencies import require_admin

ContactStatusFilter = Literal["new", "reviewed", "contacted", "archived"]

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.post(
    "/submit",
    response_model=ContactSubmissionPublic,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("5/minute")
async def submit_contact_form(
    request: Request,
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
        message=submission.message,
    )

    await session.commit()

    return ContactSubmissionPublic.model_validate(contact)


@router.get("/admin/submissions", response_model=List[ContactSubmissionAdmin])
async def get_contact_submissions(
    status: Optional[ContactStatusFilter] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user=Depends(require_admin),
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

    submissions = await repo.find_many(status=status, skip=offset, limit=limit)

    return [ContactSubmissionAdmin.model_validate(sub) for sub in submissions]


@router.get(
    "/admin/submissions/{submission_id}",
    response_model=ContactSubmissionAdmin,
)
async def get_contact_submission(
    submission_id: int,
    current_user=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Get a single contact submission by ID (Admin-only)."""
    repo = ContactSubmissionsRepository(session)
    submission = await repo.get(submission_id)
    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact submission not found",
        )
    return ContactSubmissionAdmin.model_validate(submission)


@router.patch(
    "/admin/submissions/{submission_id}",
    response_model=ContactSubmissionAdmin,
)
async def update_contact_submission(
    submission_id: int,
    payload: ContactSubmissionUpdate,
    current_user=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Update status and/or admin notes of a contact submission (Admin-only)."""
    update_notes = "admin_notes" in payload.model_fields_set
    if payload.status is None and not update_notes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields provided to update",
        )

    repo = ContactSubmissionsRepository(session)
    updated = await repo.update_submission(
        submission_id,
        status=payload.status,
        admin_notes=payload.admin_notes,
        update_notes=update_notes,
        reviewed_by=current_user.id,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact submission not found",
        )

    await session.commit()
    return ContactSubmissionAdmin.model_validate(updated)


@router.delete(
    "/admin/submissions/{submission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_contact_submission(
    submission_id: int,
    current_user=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Delete a contact submission by ID (Admin-only)."""
    repo = ContactSubmissionsRepository(session)
    deleted = await repo.delete_one(submission_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact submission not found",
        )

    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
