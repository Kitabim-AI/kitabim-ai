"""
Auto-Correction Rules API — manage global substitution rules.

All endpoints require admin role.
"""
from __future__ import annotations

from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select, delete, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.db.models import AutoCorrectRule
from app.models.user import User
from app.services.auto_correct_service import get_auto_correction_stats
from auth.dependencies import require_editor

router = APIRouter()


# ── Response schemas ──────────────────────────────────────────────────────────

class AutoCorrectRuleOut(BaseModel):
    id: int
    misspelled_word: str
    corrected_word: str
    is_active: bool
    description: Optional[str]
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str]

    model_config = {"from_attributes": True}


class AutoCorrectRulePaginatedOut(BaseModel):
    items: List[AutoCorrectRuleOut]
    total: int
    skip: int
    limit: int


class AutoCorrectStatsOut(BaseModel):
    total_rules: int
    active_rules: int
    total_auto_corrected: int
    pending_corrections: int


class ApplyRulesResponse(BaseModel):
    queued_pages: int


# ── Request schemas ───────────────────────────────────────────────────────────

class CreateAutoCorrectRuleRequest(BaseModel):
    misspelled_word: str
    corrected_word: str
    is_active: bool = False
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


class UpdateAutoCorrectRuleRequest(BaseModel):
    corrected_word: Optional[str] = None
    is_active: Optional[bool] = None
    description: Optional[str] = None

    @field_validator('corrected_word')
    @classmethod
    def validate_not_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and (not v or not v.strip()):
            raise ValueError('Corrected word cannot be empty')
        return v.strip() if v else None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/auto-correct-rules", response_model=AutoCorrectRulePaginatedOut)
async def list_auto_correct_rules(
    skip: int = 0,
    limit: int = 20,
    search: Optional[str] = None,
    auto_apply_only: bool = False,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """
    List all auto-correction rules with pagination and search.

    Query params:
    - skip: Number of records to skip
    - limit: Maximum number of records to return
    - search: Search query (misspelled word, corrected word, or description)
    - auto_apply_only: If true, only return rules with is_active=True
    """
    stmt = select(AutoCorrectRule).order_by(func.lower(AutoCorrectRule.misspelled_word), AutoCorrectRule.id)
    count_stmt = select(func.count()).select_from(AutoCorrectRule)

    filters = []
    if auto_apply_only:
        filters.append(AutoCorrectRule.is_active)

    if search:
        search_filter = or_(
            AutoCorrectRule.misspelled_word.ilike(f"%{search}%"),
            AutoCorrectRule.corrected_word.ilike(f"%{search}%"),
            AutoCorrectRule.description.ilike(f"%{search}%")
        )
        filters.append(search_filter)

    if filters:
        stmt = stmt.where(*filters)
        count_stmt = count_stmt.where(*filters)

    # Get total count
    total_result = await session.execute(count_stmt)
    total = total_result.scalar() or 0

    # Get paginated results
    stmt = stmt.offset(skip).limit(limit)
    result = await session.execute(stmt)
    items = list(result.scalars().all())

    return {
        "items": items,
        "total": total,
        "skip": skip,
        "limit": limit
    }


@router.get("/auto-correct-rules/stats", response_model=AutoCorrectStatsOut)
async def get_auto_correct_stats_endpoint(
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Get statistics about auto-corrections."""
    stats = await get_auto_correction_stats(session)
    return AutoCorrectStatsOut(**stats)


@router.get("/auto-correct-rules/{word}", response_model=AutoCorrectRuleOut)
async def get_auto_correct_rule(
    word: str,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Get a specific auto-correction rule."""
    result = await session.execute(
        select(AutoCorrectRule)
        .where(AutoCorrectRule.misspelled_word == word)
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(status_code=404, detail="Auto-correction rule not found")

    return rule


@router.post("/auto-correct-rules", response_model=AutoCorrectRuleOut, status_code=201)
async def create_auto_correct_rule(
    body: CreateAutoCorrectRuleRequest,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """
    Create a new auto-correction rule.

    If a rule already exists for the misspelled word, it will be updated.
    """
    # Check if rule already exists
    existing = await session.execute(
        select(AutoCorrectRule)
        .where(AutoCorrectRule.misspelled_word == body.misspelled_word)
    )
    existing_rule = existing.scalar_one_or_none()

    if existing_rule:
        # Update existing rule
        existing_rule.corrected_word = body.corrected_word
        existing_rule.is_active = body.is_active
        existing_rule.description = body.description
        existing_rule.updated_at = func.now()
        await session.commit()
        await session.refresh(existing_rule)
        return existing_rule
    else:
        # Create new rule
        rule = AutoCorrectRule(
            misspelled_word=body.misspelled_word,
            corrected_word=body.corrected_word,
            is_active=body.is_active,
            description=body.description,
            created_by=current_user.id,
        )
        session.add(rule)
        await session.commit()
        await session.refresh(rule)
        return rule


@router.patch("/auto-correct-rules/{word}", response_model=AutoCorrectRuleOut)
async def update_auto_correct_rule(
    word: str,
    body: UpdateAutoCorrectRuleRequest,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """
    Update an existing auto-correction rule.

    Only provided fields will be updated.
    """
    result = await session.execute(
        select(AutoCorrectRule)
        .where(AutoCorrectRule.misspelled_word == word)
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(status_code=404, detail="Auto-correction rule not found")

    # Update only provided fields
    if body.corrected_word is not None:
        if body.corrected_word == word:
            raise HTTPException(
                status_code=400,
                detail="Corrected word must be different from misspelled word"
            )
        rule.corrected_word = body.corrected_word

    if body.is_active is not None:
        rule.is_active = body.is_active

    if body.description is not None:
        rule.description = body.description

    rule.updated_at = func.now()

    await session.commit()
    await session.refresh(rule)
    return rule


@router.delete("/auto-correct-rules/{word}", status_code=204)
async def delete_auto_correct_rule(
    word: str,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Delete an auto-correction rule."""
    result = await session.execute(
        delete(AutoCorrectRule)
        .where(AutoCorrectRule.misspelled_word == word)
        .returning(AutoCorrectRule.misspelled_word)
    )

    if not result.fetchone():
        raise HTTPException(status_code=404, detail="Auto-correction rule not found")

    await session.commit()
    return None


