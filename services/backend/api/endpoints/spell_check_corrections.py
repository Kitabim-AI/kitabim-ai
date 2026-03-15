"""
Spell Check Corrections API — manage auto-correction rules.

All endpoints require admin role.
"""
from __future__ import annotations

from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.db.models import SpellCheckCorrection
from app.models.user import User
from app.services.auto_correct_service import get_auto_correction_stats
from auth.dependencies import require_admin

router = APIRouter()


# ── Response schemas ──────────────────────────────────────────────────────────

class CorrectionRuleOut(BaseModel):
    misspelled_word: str
    corrected_word: str
    auto_apply: bool
    description: Optional[str]
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str]

    model_config = {"from_attributes": True}


class CorrectionStatsOut(BaseModel):
    total_rules: int
    active_rules: int
    total_auto_corrected: int
    pending_corrections: int


class ApplyCorrectionsResponse(BaseModel):
    queued_pages: int


# ── Request schemas ───────────────────────────────────────────────────────────

class CreateCorrectionRuleRequest(BaseModel):
    misspelled_word: str
    corrected_word: str
    auto_apply: bool = False
    description: Optional[str] = None

    @field_validator('misspelled_word', 'corrected_word')
    @classmethod
    def validate_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('Word cannot be empty')
        return v.strip()

    @field_validator('corrected_word')
    @classmethod
    def validate_different(cls, v: str, info) -> str:
        if 'misspelled_word' in info.data and v == info.data['misspelled_word']:
            raise ValueError('Corrected word must be different from misspelled word')
        return v


class UpdateCorrectionRuleRequest(BaseModel):
    corrected_word: Optional[str] = None
    auto_apply: Optional[bool] = None
    description: Optional[str] = None

    @field_validator('corrected_word')
    @classmethod
    def validate_not_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and (not v or not v.strip()):
            raise ValueError('Corrected word cannot be empty')
        return v.strip() if v else None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/spell-check-corrections", response_model=List[CorrectionRuleOut])
async def list_correction_rules(
    auto_apply_only: bool = False,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """
    List all correction rules.

    Query params:
    - auto_apply_only: If true, only return rules with auto_apply=True
    """
    stmt = select(SpellCheckCorrection).order_by(SpellCheckCorrection.misspelled_word)

    if auto_apply_only:
        stmt = stmt.where(SpellCheckCorrection.auto_apply == True)

    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("/spell-check-corrections/stats", response_model=CorrectionStatsOut)
async def get_correction_stats(
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Get statistics about auto-corrections."""
    stats = await get_auto_correction_stats(session)
    return CorrectionStatsOut(**stats)


@router.get("/spell-check-corrections/{word}", response_model=CorrectionRuleOut)
async def get_correction_rule(
    word: str,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Get a specific correction rule."""
    result = await session.execute(
        select(SpellCheckCorrection)
        .where(SpellCheckCorrection.misspelled_word == word)
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(status_code=404, detail="Correction rule not found")

    return rule


@router.post("/spell-check-corrections", response_model=CorrectionRuleOut, status_code=201)
async def create_correction_rule(
    body: CreateCorrectionRuleRequest,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """
    Create a new correction rule.

    If a rule already exists for the misspelled word, it will be updated.
    """
    # Check if rule already exists
    existing = await session.execute(
        select(SpellCheckCorrection)
        .where(SpellCheckCorrection.misspelled_word == body.misspelled_word)
    )
    existing_rule = existing.scalar_one_or_none()

    if existing_rule:
        # Update existing rule
        existing_rule.corrected_word = body.corrected_word
        existing_rule.auto_apply = body.auto_apply
        existing_rule.description = body.description
        existing_rule.updated_at = func.now()
        await session.commit()
        await session.refresh(existing_rule)
        return existing_rule
    else:
        # Create new rule
        rule = SpellCheckCorrection(
            misspelled_word=body.misspelled_word,
            corrected_word=body.corrected_word,
            auto_apply=body.auto_apply,
            description=body.description,
            created_by=current_user.id,
        )
        session.add(rule)
        await session.commit()
        await session.refresh(rule)
        return rule


@router.patch("/spell-check-corrections/{word}", response_model=CorrectionRuleOut)
async def update_correction_rule(
    word: str,
    body: UpdateCorrectionRuleRequest,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """
    Update an existing correction rule.

    Only provided fields will be updated.
    """
    result = await session.execute(
        select(SpellCheckCorrection)
        .where(SpellCheckCorrection.misspelled_word == word)
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(status_code=404, detail="Correction rule not found")

    # Update only provided fields
    if body.corrected_word is not None:
        if body.corrected_word == word:
            raise HTTPException(
                status_code=400,
                detail="Corrected word must be different from misspelled word"
            )
        rule.corrected_word = body.corrected_word

    if body.auto_apply is not None:
        rule.auto_apply = body.auto_apply

    if body.description is not None:
        rule.description = body.description

    rule.updated_at = func.now()

    await session.commit()
    await session.refresh(rule)
    return rule


@router.delete("/spell-check-corrections/{word}", status_code=204)
async def delete_correction_rule(
    word: str,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Delete a correction rule."""
    result = await session.execute(
        delete(SpellCheckCorrection)
        .where(SpellCheckCorrection.misspelled_word == word)
        .returning(SpellCheckCorrection.misspelled_word)
    )

    if not result.fetchone():
        raise HTTPException(status_code=404, detail="Correction rule not found")

    await session.commit()
    return None


@router.post("/spell-check-corrections/apply", response_model=ApplyCorrectionsResponse)
async def trigger_auto_corrections(
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """
    Manually trigger auto-correction job for all pages with auto-correctable issues.

    This will queue pages for processing by the background worker.
    Normally, the auto-correction scanner runs automatically every few minutes.
    """
    from app.services.auto_correct_service import find_pages_with_auto_correctable_issues

    # Find pages with auto-correctable issues
    batch_size = 50  # Could be made configurable
    page_ids = await find_pages_with_auto_correctable_issues(session, limit=batch_size)

    if not page_ids:
        return ApplyCorrectionsResponse(queued_pages=0)

    # In a production environment, we would enqueue a job here
    # For now, we just return the count
    # TODO: Integrate with Redis job queue when worker is running

    return ApplyCorrectionsResponse(queued_pages=len(page_ids))
