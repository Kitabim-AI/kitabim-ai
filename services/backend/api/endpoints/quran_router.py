"""
Quran API — search and list Quran verses.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.db.models import Quran

router = APIRouter()


# ── Response/Request schemas ──────────────────────────────────────────────────


class QuranStatsOut(BaseModel):
    total_entries: int


class SurahOut(BaseModel):
    surah: int
    surah_name_en: str
    surah_name_ar: str
    surah_name_ug: str

    model_config = {"from_attributes": True}


class QuranAyahOut(BaseModel):
    id: int
    surah: int
    surah_name_en: str
    surah_name_ar: str
    surah_name_ug: str
    ayah: int
    text_ar: str
    text_en: str
    text_ug: str

    model_config = {"from_attributes": True}


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/quran/surahs", response_model=List[SurahOut])
async def list_surahs(
    session: AsyncSession = Depends(get_session),
):
    """Get distinct list of all surahs with their names."""
    stmt = (
        select(
            Quran.surah,
            Quran.surah_name_en,
            Quran.surah_name_ar,
            Quran.surah_name_ug,
        )
        .distinct()
        .order_by(Quran.surah.asc())
    )
    res = await session.execute(stmt)
    return [
        SurahOut(
            surah=row[0],
            surah_name_en=row[1],
            surah_name_ar=row[2],
            surah_name_ug=row[3],
        )
        for row in res.all()
    ]


@router.get("/quran/search", response_model=List[QuranAyahOut])
async def search_quran(
    q: str,
    limit: int = 15,
    session: AsyncSession = Depends(get_session),
):
    """Search for verses in Arabic, English or Uyghur."""
    q = q.strip()
    if len(q) < 1:
        return []

    stmt = (
        select(Quran)
        .where(
            Quran.text_ug.ilike(f"%{q}%")
            | Quran.text_en.ilike(f"%{q}%")
            | Quran.text_ar.ilike(f"%{q}%")
        )
        .order_by(Quran.surah.asc(), Quran.ayah.asc())
        .limit(limit)
    )
    res = await session.execute(stmt)
    return res.scalars().all()


@router.get("/quran/stats", response_model=QuranStatsOut)
async def get_quran_stats(
    surah: Optional[int] = None,
    session: AsyncSession = Depends(get_session),
):
    """Get total ayah count in the quran list, optionally filtered by surah."""
    stmt = select(func.count()).select_from(Quran)
    if surah is not None:
        stmt = stmt.where(Quran.surah == surah)
    res = await session.execute(stmt)
    return {"total_entries": res.scalar() or 0}


@router.get("/quran", response_model=List[QuranAyahOut])
async def list_quran_entries(
    skip: int = 0,
    limit: int = 50,
    surah: Optional[int] = None,
    session: AsyncSession = Depends(get_session),
):
    """List quran verses, sorted by surah and ayah. Optionally filtered by surah."""
    stmt = select(Quran).order_by(Quran.surah.asc(), Quran.ayah.asc())
    if surah is not None:
        stmt = stmt.where(Quran.surah == surah)
    stmt = stmt.offset(skip).limit(limit)
    res = await session.execute(stmt)
    return res.scalars().all()
