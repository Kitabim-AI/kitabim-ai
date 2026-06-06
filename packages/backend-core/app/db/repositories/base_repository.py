"""Base repository with common CRUD operations"""
from __future__ import annotations

from typing import Generic, TypeVar, Type, List, Optional, Any

from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Base


ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """
    Base repository with common database operations.

    Provides standard CRUD operations that can be inherited by specific repositories.
    """

    def __init__(self, session: AsyncSession, model: Type[ModelType]):
        self.session = session
        self.model = model

    async def get(self, id: Any) -> Optional[ModelType]:
        """Get single record by primary key"""
        from sqlalchemy import inspect
        pk_column = inspect(self.model).primary_key[0]
        result = await self.session.execute(
            select(self.model).where(pk_column == id)
        )
        return result.scalar_one_or_none()

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        order_by: str = "id"
    ) -> List[ModelType]:
        """Get all records with pagination"""
        stmt = select(self.model).offset(skip).limit(limit)

        if hasattr(self.model, order_by):
            order_col = getattr(self.model, order_by)
            stmt = stmt.order_by(order_col)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, **kwargs) -> ModelType:
        """Create new record"""
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()  # Get ID without committing
        await self.session.refresh(instance)
        return instance

    async def update_one(self, id: Any, **kwargs) -> Optional[ModelType]:
        """Update record by primary key"""
        from sqlalchemy import inspect
        pk_column = inspect(self.model).primary_key[0]
        stmt = (
            update(self.model)
            .where(pk_column == id)
            .values(**kwargs)
            .returning(self.model)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.scalar_one_or_none()

    async def delete_one(self, id: Any) -> bool:
        """Delete record by primary key"""
        from sqlalchemy import inspect
        pk_column = inspect(self.model).primary_key[0]
        stmt = delete(self.model).where(pk_column == id)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0

    async def count(self, **filters) -> int:
        """Count records with optional filters"""
        stmt = select(func.count()).select_from(self.model)

        if filters:
            for key, value in filters.items():
                if hasattr(self.model, key):
                    stmt = stmt.where(getattr(self.model, key) == value)

        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def exists(self, id: Any) -> bool:
        """Check if record exists by primary key"""
        from sqlalchemy import inspect
        pk_column = inspect(self.model).primary_key[0]
        result = await self.session.execute(
            select(func.count()).select_from(self.model).where(pk_column == id)
        )
        return result.scalar_one() > 0
