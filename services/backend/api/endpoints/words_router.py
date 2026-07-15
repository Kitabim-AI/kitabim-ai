"""
Words Management API — search and list words from the global spell check words list.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.db.models import Word

router = APIRouter()


# ── Response/Request schemas ──────────────────────────────────────────────────


class WordsStatsOut(BaseModel):
    total_words: int


class WordOut(BaseModel):
    id: int
    word: str

    model_config = {"from_attributes": True}


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/spell-check/words/search", response_model=List[WordOut])
async def search_words(
    q: str,
    limit: int = 10,
    session: AsyncSession = Depends(get_session),
):
    """Search for words in the spell check list (autocomplete)."""
    q = q.strip()
    if len(q) < 1:
        return []

    stmt = (
        select(Word)
        .where(Word.word.ilike(f"%{q}%"))
        .order_by(func.length(Word.word), Word.word)
        .limit(limit)
    )
    res = await session.execute(stmt)
    return res.scalars().all()


@router.get("/spell-check/words/stats", response_model=WordsStatsOut)
async def get_words_stats(
    letter_group: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    """Get total word count in the spell check list."""
    stmt = select(func.count()).select_from(Word)
    if letter_group:
        stmt = stmt.where(func.substr(Word.word, 1, len(letter_group)) == letter_group)
    res = await session.execute(stmt)
    return {"total_words": res.scalar() or 0}


@router.get("/spell-check/words/letter-groups", response_model=List[str])
async def list_letter_groups(
    session: AsyncSession = Depends(get_session),
):
    """Return all distinct first letters present in the words list."""
    col = func.substr(Word.word, 1, 1)
    stmt = select(col).group_by(col).order_by(col)
    res = await session.execute(stmt)
    return [row for (row,) in res.all() if row]


@router.get("/spell-check/words", response_model=List[WordOut])
async def list_words(
    skip: int = 0,
    limit: int = 20,
    letter_group: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    """List words in the spell check list with pagination, sorted alphabetically."""
    stmt = select(Word).order_by(Word.id.asc())
    if letter_group:
        stmt = stmt.where(func.substr(Word.word, 1, len(letter_group)) == letter_group)
    stmt = stmt.offset(skip).limit(limit)
    res = await session.execute(stmt)
    return res.scalars().all()
