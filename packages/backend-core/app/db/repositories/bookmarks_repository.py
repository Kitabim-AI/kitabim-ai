"""Repository for user-created page and passage bookmarks"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select, delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Bookmark
from app.db.repositories.base_repository import BaseRepository


class BookmarksRepository(BaseRepository[Bookmark]):
    """Repository for bookmark rows, always scoped to the owning user"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, Bookmark)

    async def create(
        self,
        user_id: str,
        book_id: str,
        page_number: int,
        name: str,
        quote_text: Optional[str] = None,
    ) -> Bookmark:
        """Create a new bookmark"""
        bookmark = Bookmark(
            user_id=user_id,
            book_id=book_id,
            page_number=page_number,
            name=name,
            quote_text=quote_text,
        )
        self.session.add(bookmark)
        await self.session.commit()
        await self.session.refresh(bookmark)
        return bookmark

    async def list(self, user_id: str, book_id: Optional[str] = None) -> List[Bookmark]:
        """List this user's bookmarks, optionally scoped to one book"""
        stmt = select(Bookmark).where(Bookmark.user_id == user_id)
        if book_id is not None:
            stmt = stmt.where(Bookmark.book_id == book_id).order_by(
                Bookmark.page_number.asc()
            )
        else:
            stmt = stmt.order_by(Bookmark.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get(self, bookmark_id: str, user_id: str) -> Optional[Bookmark]:
        """Fetch a bookmark by id, only if owned by this user"""
        stmt = select(Bookmark).where(
            Bookmark.id == bookmark_id, Bookmark.user_id == user_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def rename(
        self, bookmark_id: str, user_id: str, name: str
    ) -> Optional[Bookmark]:
        """Rename a bookmark if owned by this user"""
        bookmark = await self.get(bookmark_id, user_id)
        if bookmark is None:
            return None
        bookmark.name = name
        await self.session.commit()
        await self.session.refresh(bookmark)
        return bookmark

    async def delete(self, bookmark_id: str, user_id: str) -> bool:
        """Delete a bookmark if owned by this user. Returns True if a row was deleted"""
        stmt = sql_delete(Bookmark).where(
            Bookmark.id == bookmark_id, Bookmark.user_id == user_id
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0


def get_bookmarks_repository(session: AsyncSession) -> BookmarksRepository:
    """Factory helper for BookmarksRepository"""
    return BookmarksRepository(session)
