from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional


async def record_book_error(
    db,
    book_id: str,
    kind: str,
    message: str,
    context: Optional[Dict[str, Any]] = None,
) -> None:
    if db is None or not book_id:
        return

    error_event = {
        "ts": datetime.utcnow(),
        "kind": kind,
        "message": message,
        "context": context or {},
    }

    await db.books.update_one(
        {"id": book_id},
        {
            "$push": {"errors": error_event},
            "$set": {"lastError": error_event, "lastUpdated": datetime.utcnow()},
        },
    )
