"""
Proverbs Management API — search and list proverbs.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.db.models import Proverb
from auth.dependencies import require_editor
from app.models.user import User
from app.services.cache_service import cache_service

router = APIRouter()


# ── Response/Request schemas ──────────────────────────────────────────────────


class ProverbsStatsOut(BaseModel):
    total_entries: int


class ProverbEntryOut(BaseModel):
    id: int
    text: str
    volume: Optional[int] = None
    page_number: Optional[int] = None

    model_config = {"from_attributes": True}


class ProverbUpdate(BaseModel):
    text: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/proverbs/search", response_model=List[ProverbEntryOut])
async def search_proverbs(
    q: str,
    limit: int = 10,
    session: AsyncSession = Depends(get_session),
):
    """Search for proverbs (autocomplete)."""
    q = q.strip()
    if len(q) < 1:
        return []

    stmt = (
        select(Proverb)
        .where(Proverb.text.ilike(f"%{q}%"))
        .order_by(func.length(Proverb.text), Proverb.text)
        .limit(limit)
    )
    res = await session.execute(stmt)
    return res.scalars().all()


@router.get("/proverbs/stats", response_model=ProverbsStatsOut)
async def get_proverbs_stats(
    letter_group: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    """Get total entry count in the proverbs list."""
    stmt = select(func.count()).select_from(Proverb)
    if letter_group:
        stmt = stmt.where(
            func.substr(Proverb.text, 1, len(letter_group)) == letter_group
        )
    res = await session.execute(stmt)
    return {"total_entries": res.scalar() or 0}


@router.get("/proverbs", response_model=List[ProverbEntryOut])
async def list_proverbs_entries(
    skip: int = 0,
    limit: int = 20,
    letter_group: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    """List proverbs with pagination, sorted alphabetically."""
    stmt = select(Proverb).order_by(Proverb.id.asc())
    if letter_group:
        stmt = stmt.where(
            func.substr(Proverb.text, 1, len(letter_group)) == letter_group
        )
    stmt = stmt.offset(skip).limit(limit)
    res = await session.execute(stmt)
    return res.scalars().all()


@router.put("/proverbs/{proverb_id}", response_model=ProverbEntryOut)
async def update_proverb(
    proverb_id: int,
    body: ProverbUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_editor),
):
    """Update a proverb's text (Admin / Editor only). Volume and page number are
    source references and are never changed by this endpoint."""
    stmt = select(Proverb).where(Proverb.id == proverb_id)
    res = await session.execute(stmt)
    proverb = res.scalar_one_or_none()
    if not proverb:
        raise HTTPException(status_code=404, detail="Proverb not found")

    if body.text is not None:
        proverb.text = body.text.strip()

    await session.commit()
    await session.refresh(proverb)

    # Invalidate Redis proverbs cache
    await cache_service.delete_pattern("proverb:*")
    await cache_service.delete_pattern("proverbs:*")

    return proverb
