"""
History Dictionary API — access to Uyghur historical vocabulary entries, admin delete.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select, func, distinct, delete, or_, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.i18n import t
from app.db.session import get_session
from app.db.models import HistoryDictionary
from app.db.repositories.dictionary_repository import DictionaryRepository
from app.models.user import User
from auth.dependencies import require_admin

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


class HistoryEntryCreate(BaseModel):
    term: str
    transliteration: Optional[str] = None
    definition: Optional[str] = None

    @field_validator("term")
    @classmethod
    def validate_term_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Term cannot be empty")
        return v.strip()


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
    pattern = f"%{q}%"
    stmt = (
        select(HistoryDictionary)
        .where(
            or_(
                HistoryDictionary.term.ilike(pattern),
                HistoryDictionary.definition.ilike(pattern),
            )
        )
        .order_by(
            case((HistoryDictionary.term.ilike(pattern), 0), else_=1),
            func.length(HistoryDictionary.term),
            HistoryDictionary.term,
        )
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


@router.post("/history-dictionary", response_model=HistoryEntryOut, status_code=201)
async def create_history_entry(
    body: HistoryEntryCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_admin),
):
    """Create a new live history dictionary entry (Admin only)."""
    repo = DictionaryRepository(session)
    existing = await repo.find_matching_history_term(body.term)
    if existing:
        raise HTTPException(
            status_code=409,
            detail={
                "message": t("errors.history_entry_duplicate_term"),
                "existing_id": existing.id,
                "existing_term": existing.term,
            },
        )
    letter_group = body.term[0].upper()
    entry = await repo.create_history_dictionary_entry(
        term=body.term,
        transliteration=body.transliteration,
        definition=body.definition,
        letter_group=letter_group,
    )
    await session.commit()
    return entry


@router.delete("/history-dictionary/{entry_id}", status_code=204)
async def delete_history_entry(
    entry_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_admin),
):
    """Delete a history dictionary entry (Admin only)."""
    result = await session.execute(
        delete(HistoryDictionary)
        .where(HistoryDictionary.id == entry_id)
        .returning(HistoryDictionary.id)
    )
    if not result.fetchone():
        raise HTTPException(status_code=404, detail="Entry not found")
    await session.commit()
    return None
