"""Endpoints for silent reading progress and user-created bookmarks"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.i18n import t
from app.db.session import get_session
from app.db.repositories.reading_progress_repository import ReadingProgressRepository
from app.db.repositories.bookmarks_repository import BookmarksRepository
from app.models.user import User
from auth.dependencies import require_reader

router = APIRouter()


class UpsertProgressRequest(BaseModel):
    page_number: int


class CreateBookmarkRequest(BaseModel):
    page_number: int
    name: str
    quote_text: Optional[str] = None


class RenameBookmarkRequest(BaseModel):
    name: str


@router.put("/progress/{book_id}")
async def upsert_progress_endpoint(
    book_id: str,
    req: UpsertProgressRequest,
    current_user: User = Depends(require_reader),
    session: AsyncSession = Depends(get_session),
):
    """Silently save this user's current page for a book"""
    repo = ReadingProgressRepository(session)
    progress = await repo.upsert(
        user_id=current_user.id, book_id=book_id, page_number=req.page_number
    )
    return {
        "bookId": progress.book_id,
        "pageNumber": progress.page_number,
        "updatedAt": progress.updated_at.isoformat(),
    }


@router.get("/progress/{book_id}")
async def get_progress_for_book_endpoint(
    book_id: str,
    current_user: User = Depends(require_reader),
    session: AsyncSession = Depends(get_session),
):
    """Fetch this user's saved page for a single book, used to resume on open"""
    repo = ReadingProgressRepository(session)
    progress = await repo.get_for_book(user_id=current_user.id, book_id=book_id)
    return {"pageNumber": progress.page_number if progress else None}


@router.get("/progress")
async def list_progress_endpoint(
    limit: int = 50,
    current_user: User = Depends(require_reader),
    session: AsyncSession = Depends(get_session),
):
    """List this user's books with saved progress, most recent first (Continue Reading tab)"""
    repo = ReadingProgressRepository(session)
    rows = await repo.list_recent(user_id=current_user.id, limit=limit)
    return {
        "items": [
            {
                "bookId": row.book_id,
                "bookTitle": row.book.title if row.book else None,
                "bookCoverUrl": row.book.cover_url if row.book else None,
                "pageNumber": row.page_number,
                "updatedAt": row.updated_at.isoformat(),
            }
            for row in rows
        ]
    }


def _serialize_bookmark(bookmark) -> dict:
    return {
        "id": bookmark.id,
        "bookId": bookmark.book_id,
        "bookTitle": bookmark.book.title if bookmark.book else None,
        "pageNumber": bookmark.page_number,
        "name": bookmark.name,
        "quoteText": bookmark.quote_text,
        "createdAt": bookmark.created_at.isoformat(),
    }


@router.post("/{book_id}")
async def create_bookmark_endpoint(
    book_id: str,
    req: CreateBookmarkRequest,
    current_user: User = Depends(require_reader),
    session: AsyncSession = Depends(get_session),
):
    """Create a whole-page or passage bookmark"""
    repo = BookmarksRepository(session)
    bookmark = await repo.create(
        user_id=current_user.id,
        book_id=book_id,
        page_number=req.page_number,
        name=req.name,
        quote_text=req.quote_text,
    )
    return _serialize_bookmark(bookmark)


@router.get("/")
async def list_bookmarks_endpoint(
    book_id: Optional[str] = None,
    current_user: User = Depends(require_reader),
    session: AsyncSession = Depends(get_session),
):
    """List this user's bookmarks, optionally scoped to one book"""
    repo = BookmarksRepository(session)
    bookmarks = await repo.list(user_id=current_user.id, book_id=book_id)
    return {"bookmarks": [_serialize_bookmark(b) for b in bookmarks]}


@router.patch("/{bookmark_id}")
async def rename_bookmark_endpoint(
    bookmark_id: str,
    req: RenameBookmarkRequest,
    current_user: User = Depends(require_reader),
    session: AsyncSession = Depends(get_session),
):
    """Rename a bookmark owned by this user"""
    repo = BookmarksRepository(session)
    bookmark = await repo.rename(
        bookmark_id=bookmark_id, user_id=current_user.id, name=req.name
    )
    if bookmark is None:
        raise HTTPException(status_code=404, detail=t("errors.bookmark_not_found"))
    return _serialize_bookmark(bookmark)


@router.delete("/{bookmark_id}")
async def delete_bookmark_endpoint(
    bookmark_id: str,
    current_user: User = Depends(require_reader),
    session: AsyncSession = Depends(get_session),
):
    """Delete a bookmark owned by this user"""
    repo = BookmarksRepository(session)
    deleted = await repo.delete(bookmark_id=bookmark_id, user_id=current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail=t("errors.bookmark_not_found"))
    return {"success": True}
