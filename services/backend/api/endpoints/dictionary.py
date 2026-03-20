"""
Dictionary Management API — search, add, and remove words from the global dictionary.
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.db.models import Dictionary, PageSpellIssue
from app.models.user import User
from auth.dependencies import require_editor

router = APIRouter()


# ── Response/Request schemas ──────────────────────────────────────────────────

class AddToDictionaryRequest(BaseModel):
    word: str


class DictionaryStatsOut(BaseModel):
    total_words: int


class DictionaryWordOut(BaseModel):
    id: int
    word: str

    model_config = {"from_attributes": True}


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/spell-check/dictionary")
async def add_to_dictionary(
    body: AddToDictionaryRequest,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Add a word to the global spell check dictionary. Editor and Admin allowed."""
    word = body.word.strip()
    if not word:
        raise HTTPException(status_code=400, detail="Word cannot be empty")

    # Check if already exists
    stmt = select(Dictionary).where(Dictionary.word == word)
    res = await session.execute(stmt)
    if res.scalar_one_or_none():
        return {"added": 0, "message": "Word already in dictionary"}

    new_word = Dictionary(word=word)
    session.add(new_word)
    
    # Also mark all matching OPEN issues across the entire system as 'ignored'
    # since the word is now valid.
    await session.execute(
        update(PageSpellIssue)
        .where(PageSpellIssue.word == word, PageSpellIssue.status == "open")
        .values(status="ignored")
    )
    
    await session.commit()
    return {"added": 1}


@router.get("/spell-check/dictionary/search", response_model=List[DictionaryWordOut])
async def search_dictionary(
    q: str,
    limit: int = 10,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Search for words in the dictionary (autocomplete)."""
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


@router.get("/spell-check/dictionary/stats", response_model=DictionaryStatsOut)
async def get_dictionary_stats(
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Get total word count in the dictionary."""
    stmt = select(func.count()).select_from(Dictionary)
    res = await session.execute(stmt)
    return {"total_words": res.scalar() or 0}


@router.delete("/spell-check/dictionary/{word}")
async def delete_from_dictionary(
    word: str,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Remove a word from the dictionary. Only allowed for editors/admins."""
    word = word.strip()
    if not word:
        raise HTTPException(status_code=400, detail="Word cannot be empty")

    # Find the word
    stmt = select(Dictionary).where(Dictionary.word == word)
    res = await session.execute(stmt)
    entry = res.scalar_one_or_none()
    
    if not entry:
        raise HTTPException(status_code=404, detail="Word not found in dictionary")

    await session.delete(entry)
    await session.commit()
    
    return {"deleted": True, "word": word}
