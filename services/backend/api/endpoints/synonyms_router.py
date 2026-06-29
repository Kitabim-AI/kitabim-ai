"""
Synonyms API — read-only lookup and search for the Uyghur synonym dictionary.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.db.models import Synonym
from app.models.user import User
from auth.dependencies import require_editor

router = APIRouter()


# ── Response schemas ──────────────────────────────────────────────────────────


class SynonymEntryOut(BaseModel):
    id: int
    word: str
    letter_group: str
    synonyms: List[str]

    model_config = {"from_attributes": True}


class SynonymStatsOut(BaseModel):
    total_words: int


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/synonyms/search", response_model=List[SynonymEntryOut])
async def search_synonyms(
    q: str,
    limit: int = 10,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Search synonyms by word prefix/substring (autocomplete)."""
    q = q.strip()
    if not q:
        return []

    stmt = (
        select(Synonym)
        .where(Synonym.word.ilike(f"%{q}%"))
        .order_by(func.length(Synonym.word), Synonym.word)
        .limit(limit)
    )
    res = await session.execute(stmt)
    return res.scalars().all()


@router.get("/synonyms/lookup", response_model=SynonymEntryOut)
async def lookup_synonym(
    word: str,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Exact lookup — returns the entry and its synonyms for the given word."""
    word = word.strip()
    stmt = select(Synonym).where(Synonym.word == word)
    res = await session.execute(stmt)
    entry = res.scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=404, detail="Word not found")
    return entry


@router.get("/synonyms/letter-groups", response_model=List[str])
async def list_letter_groups(
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Return all distinct letter groups in alphabetical order."""
    stmt = select(distinct(Synonym.letter_group)).order_by(Synonym.letter_group)
    res = await session.execute(stmt)
    return res.scalars().all()


@router.get("/synonyms/stats", response_model=SynonymStatsOut)
async def get_synonym_stats(
    letter_group: Optional[str] = None,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Return total word count in the synonym dictionary."""
    stmt = select(func.count()).select_from(Synonym)
    if letter_group:
        stmt = stmt.where(Synonym.letter_group == letter_group)
    res = await session.execute(stmt)
    return {"total_words": res.scalar() or 0}


@router.get("/synonyms", response_model=List[SynonymEntryOut])
async def list_synonyms(
    letter_group: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """List synonym entries with optional letter-group filter and pagination."""
    stmt = select(Synonym)
    if letter_group:
        stmt = stmt.where(Synonym.letter_group == letter_group)
    stmt = stmt.order_by(Synonym.word).offset(skip).limit(limit)
    res = await session.execute(stmt)
    return res.scalars().all()
