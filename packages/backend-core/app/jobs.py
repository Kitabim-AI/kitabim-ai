from __future__ import annotations

from datetime import datetime
from typing import Any, Optional


async def create_or_reset_job(db, job_key: str, job_type: str, book_id: str, metadata: Optional[dict] = None):
    now = datetime.utcnow()
    existing = await db.jobs.find_one({"jobKey": job_key})
    payload = {
        "jobKey": job_key,
        "type": job_type,
        "bookId": book_id,
        "status": "queued",
        "attempts": 0,
        "lastError": None,
        "updatedAt": now,
    }

    if existing:
        if existing.get("status") in {"queued", "running"}:
            return existing
        await db.jobs.update_one(
            {"jobKey": job_key},
            {
                "$set": payload,
                "$setOnInsert": {"createdAt": existing.get("createdAt") or now},
                "$push": {"history": {"status": existing.get("status"), "ts": now}},
            },
        )
        return await db.jobs.find_one({"jobKey": job_key})

    payload["createdAt"] = now
    payload["metadata"] = metadata or {}
    await db.jobs.insert_one(payload)
    return payload


async def update_job_status(db, job_key: str, status: str, error: Optional[str] = None) -> None:
    update: dict[str, Any] = {"status": status, "updatedAt": datetime.utcnow()}
    if error:
        update["lastError"] = error
    await db.jobs.update_one(
        {"jobKey": job_key},
        {
            "$set": update,
            "$push": {"history": {"status": status, "ts": datetime.utcnow(), "error": error}},
        },
    )


async def increment_attempts(db, job_key: str) -> None:
    await db.jobs.update_one(
        {"jobKey": job_key},
        {"$inc": {"attempts": 1}, "$set": {"updatedAt": datetime.utcnow()}},
    )
