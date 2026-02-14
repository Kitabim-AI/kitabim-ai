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

    # Note: $push for errors array not yet supported in PostgreSQL adapter
    # For now, just track the last error
    await db.books.update_one(
        {"id": book_id},
        {
            "$set": {"lastError": error_event, "lastUpdated": datetime.utcnow()},
        },
    )
