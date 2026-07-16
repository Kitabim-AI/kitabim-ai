"""
English-Uyghur Dictionary API — read-only access to English-Uyghur dictionary entries.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.db.models import EnglishUyghurDictionary

router = APIRouter()


# ── Response schemas ──────────────────────────────────────────────────────────


class EnglishUyghurEntryOut(BaseModel):
    id: int
    english: str
    uyghur: str
    letter_group: str

    model_config = {"from_attributes": True}


class EnglishUyghurStatsOut(BaseModel):
    total_entries: int


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/english-uyghur-dictionary/stats", response_model=EnglishUyghurStatsOut)
async def get_english_uyghur_stats(
    letter_group: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    stmt = select(func.count()).select_from(EnglishUyghurDictionary)
    if letter_group:
        stmt = stmt.where(EnglishUyghurDictionary.letter_group == letter_group)
    res = await session.execute(stmt)
    return {"total_entries": res.scalar() or 0}


@router.get("/english-uyghur-dictionary/letter-groups", response_model=List[str])
async def list_english_uyghur_letter_groups(
    session: AsyncSession = Depends(get_session),
):
    stmt = select(distinct(EnglishUyghurDictionary.letter_group)).order_by(
        EnglishUyghurDictionary.letter_group
    )
    res = await session.execute(stmt)
    return [row for (row,) in res.all() if row]


@router.get(
    "/english-uyghur-dictionary/search", response_model=List[EnglishUyghurEntryOut]
)
async def search_english_uyghur_dictionary(
    q: str,
    limit: int = 10,
    session: AsyncSession = Depends(get_session),
):
    q = q.strip()
    if not q:
        return []
    stmt = (
        select(EnglishUyghurDictionary)
        .where(EnglishUyghurDictionary.english.ilike(f"%{q}%"))
        .order_by(
            func.length(EnglishUyghurDictionary.english),
            EnglishUyghurDictionary.english,
        )
        .limit(limit)
    )
    res = await session.execute(stmt)
    return res.scalars().all()


@router.get("/english-uyghur-dictionary", response_model=List[EnglishUyghurEntryOut])
async def list_english_uyghur_entries(
    skip: int = 0,
    limit: int = 20,
    letter_group: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    stmt = select(EnglishUyghurDictionary).order_by(EnglishUyghurDictionary.id.asc())
    if letter_group:
        stmt = stmt.where(EnglishUyghurDictionary.letter_group == letter_group)
    stmt = stmt.offset(skip).limit(limit)
    res = await session.execute(stmt)
    return res.scalars().all()
