from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional


from sqlalchemy.ext.asyncio import AsyncSession
from app.db.repositories.books import BooksRepository


async def record_book_error(
    session: AsyncSession,
    book_id: str,
    kind: str,
    message: str,
    context: Optional[Dict[str, Any]] = None,
) -> None:
    if session is None or not book_id:
        return

    error_event_json = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "message": message,
        "context": context or {},
    }

    # Track the last error and update timestamp
    repo = BooksRepository(session)
    await repo.update_one(
        book_id,
        last_error=message, # Store message string in last_error
        # Note: 'errors' is a JSONB array in the model
        # For now, we just keep the last error message in last_error field
        # TODO: Implement proper error history in JSONB array if needed
        last_updated=datetime.now(timezone.utc),
    )
    await session.flush()
