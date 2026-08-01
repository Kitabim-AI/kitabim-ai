"""
Dictionary Management API — search and list entries from the new definition dictionary.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.db.models import Dictionary
from app.db.repositories.dictionary_repository import DictionaryRepository

router = APIRouter()


# ── Response/Request schemas ──────────────────────────────────────────────────


class DictionaryStatsOut(BaseModel):
    total_words: int


class DictionaryEntryOut(BaseModel):
    id: int
    word: str
    definition: Optional[str] = None
    audio: Optional[str] = None

    model_config = {"from_attributes": True}


class SpellingSuggestionOut(BaseModel):
    id: int
    word: str
    score: Optional[float] = None


class SpellingCheckOut(BaseModel):
    is_known: bool
    word: Optional[str] = None
    suggestions: List[SpellingSuggestionOut]


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/dictionary/check-spelling", response_model=SpellingCheckOut)
async def check_spelling(
    word: str,
    session: AsyncSession = Depends(get_session),
):
    """Check whether a Uyghur word exists in the spelling word list.

    Public read-only lookup used by the home search box's "Spell Check" tab
    and the equivalent `check_word_spelling` chat tool.
    """
    repo = DictionaryRepository(session)
    result = await repo.check_word_spelling(word)
    return SpellingCheckOut(**result)


@router.get("/dictionary/search", response_model=List[DictionaryEntryOut])
async def search_dictionary(
    q: str,
    limit: int = 10,
    session: AsyncSession = Depends(get_session),
):
    """Search for entries in the dictionary (autocomplete)."""
    q = q.strip()
    if len(q) < 1:
        return []

    stmt = (
        select(Dictionary)
        .where(Dictionary.word.ilike(f"%{q}%"))
        .order_by(func.length(Dictionary.word), Dictionary.word)
        .limit(limit)
    )
    res = await session.execute(stmt)
    return res.scalars().all()


@router.get("/dictionary/stats", response_model=DictionaryStatsOut)
async def get_dictionary_stats(
    letter_group: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    """Get total entry count in the dictionary."""
    stmt = select(func.count()).select_from(Dictionary)
    if letter_group:
        stmt = stmt.where(
            func.substr(Dictionary.word, 1, len(letter_group)) == letter_group
        )
    res = await session.execute(stmt)
    return {"total_words": res.scalar() or 0}


@router.get("/dictionary/letter-groups", response_model=List[str])
async def list_letter_groups(
    session: AsyncSession = Depends(get_session),
):
    """Return all distinct first letters present in the dictionary."""
    col = func.substr(Dictionary.word, 1, 1)
    stmt = select(col).group_by(col).order_by(col)
    res = await session.execute(stmt)
    return [row for (row,) in res.all() if row]


@router.get("/dictionary", response_model=List[DictionaryEntryOut])
async def list_dictionary_entries(
    skip: int = 0,
    limit: int = 20,
    letter_group: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    """List dictionary entries with pagination, sorted alphabetically."""
    stmt = select(Dictionary).order_by(Dictionary.id.asc())
    if letter_group:
        stmt = stmt.where(
            func.substr(Dictionary.word, 1, len(letter_group)) == letter_group
        )
    stmt = stmt.offset(skip).limit(limit)
    res = await session.execute(stmt)
    return res.scalars().all()
