"""
Names Dictionary API — read-only access to Uyghur person names.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.db.models import NamesDictionary

router = APIRouter()


# ── Response schemas ──────────────────────────────────────────────────────────


class NameEntryOut(BaseModel):
    id: int
    name: str
    letter_group: str

    model_config = {"from_attributes": True}


class NamesStatsOut(BaseModel):
    total_entries: int


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/names-dictionary/stats", response_model=NamesStatsOut)
async def get_names_stats(
    letter_group: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    stmt = select(func.count()).select_from(NamesDictionary)
    if letter_group:
        stmt = stmt.where(NamesDictionary.letter_group == letter_group)
    res = await session.execute(stmt)
    return {"total_entries": res.scalar() or 0}


@router.get("/names-dictionary/letter-groups", response_model=List[str])
async def list_names_letter_groups(
    session: AsyncSession = Depends(get_session),
):
    stmt = select(distinct(NamesDictionary.letter_group)).order_by(
        NamesDictionary.letter_group
    )
    res = await session.execute(stmt)
    return [row for (row,) in res.all() if row]


@router.get("/names-dictionary/search", response_model=List[NameEntryOut])
async def search_names_dictionary(
    q: str,
    limit: int = 10,
    session: AsyncSession = Depends(get_session),
):
    q = q.strip()
    if not q:
        return []
    stmt = (
        select(NamesDictionary)
        .where(NamesDictionary.name.ilike(f"%{q}%"))
        .order_by(func.length(NamesDictionary.name), NamesDictionary.name)
        .limit(limit)
    )
    res = await session.execute(stmt)
    return res.scalars().all()


@router.get("/names-dictionary", response_model=List[NameEntryOut])
async def list_names_entries(
    skip: int = 0,
    limit: int = 20,
    letter_group: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    stmt = select(NamesDictionary).order_by(NamesDictionary.id.asc())
    if letter_group:
        stmt = stmt.where(NamesDictionary.letter_group == letter_group)
    stmt = stmt.offset(skip).limit(limit)
    res = await session.execute(stmt)
    return res.scalars().all()
