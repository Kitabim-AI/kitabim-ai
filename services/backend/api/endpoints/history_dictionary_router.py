"""
History Dictionary API — read-only access to Uyghur historical vocabulary entries.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.db.models import HistoryDictionary

router = APIRouter()


# ── Response schemas ──────────────────────────────────────────────────────────


class HistoryEntryOut(BaseModel):
    id: int
    term: str
    transliteration: Optional[str] = None
    definition: Optional[str] = None
    letter_group: str

    model_config = {"from_attributes": True}


class HistoryStatsOut(BaseModel):
    total_entries: int


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/history-dictionary/stats", response_model=HistoryStatsOut)
async def get_history_stats(
    letter_group: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    stmt = select(func.count()).select_from(HistoryDictionary)
    if letter_group:
        stmt = stmt.where(HistoryDictionary.letter_group == letter_group)
    res = await session.execute(stmt)
    return {"total_entries": res.scalar() or 0}


@router.get("/history-dictionary/letter-groups", response_model=List[str])
async def list_history_letter_groups(
    session: AsyncSession = Depends(get_session),
):
    stmt = select(distinct(HistoryDictionary.letter_group)).order_by(
        HistoryDictionary.letter_group
    )
    res = await session.execute(stmt)
    return [row for (row,) in res.all() if row]


@router.get("/history-dictionary/search", response_model=List[HistoryEntryOut])
async def search_history_dictionary(
    q: str,
    limit: int = 10,
    session: AsyncSession = Depends(get_session),
):
    q = q.strip()
    if not q:
        return []
    stmt = (
        select(HistoryDictionary)
        .where(HistoryDictionary.term.ilike(f"%{q}%"))
        .order_by(func.length(HistoryDictionary.term), HistoryDictionary.term)
        .limit(limit)
    )
    res = await session.execute(stmt)
    return res.scalars().all()


@router.get("/history-dictionary", response_model=List[HistoryEntryOut])
async def list_history_entries(
    skip: int = 0,
    limit: int = 20,
    letter_group: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    stmt = select(HistoryDictionary).order_by(HistoryDictionary.id.asc())
    if letter_group:
        stmt = stmt.where(HistoryDictionary.letter_group == letter_group)
    stmt = stmt.offset(skip).limit(limit)
    res = await session.execute(stmt)
    return res.scalars().all()
