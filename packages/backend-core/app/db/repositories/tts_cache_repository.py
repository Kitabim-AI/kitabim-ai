"""Repository for content-addressed TTS audio cache records."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TtsAudioCache
from app.db.repositories.base_repository import BaseRepository


class TtsCacheRepository(BaseRepository[TtsAudioCache]):
    """Repository for tts_audio_cache rows."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, TtsAudioCache)

    async def get_by_hash(self, content_hash: str) -> Optional[TtsAudioCache]:
        stmt = select(TtsAudioCache).where(TtsAudioCache.content_hash == content_hash)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_hashes(
        self, content_hashes: list[str]
    ) -> dict[str, TtsAudioCache]:
        if not content_hashes:
            return {}
        stmt = select(TtsAudioCache).where(
            TtsAudioCache.content_hash.in_(content_hashes)
        )
        result = await self.session.execute(stmt)
        return {row.content_hash: row for row in result.scalars().all()}

    async def upsert_entry(
        self,
        *,
        content_hash: str,
        storage_path: str,
        mime_type: str,
        model: str,
        voice: str,
        style: str,
        text_chars: int,
        duration_sec: Optional[float],
        size_bytes: int,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        now = datetime.now(timezone.utc)
        stmt = (
            pg_insert(TtsAudioCache)
            .values(
                content_hash=content_hash,
                storage_path=storage_path,
                mime_type=mime_type,
                model=model,
                voice=voice,
                style=style,
                text_chars=text_chars,
                duration_sec=duration_sec,
                size_bytes=size_bytes,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                hit_count=0,
                created_at=now,
                last_accessed_at=now,
            )
            .on_conflict_do_update(
                index_elements=[TtsAudioCache.content_hash],
                set_={
                    "storage_path": storage_path,
                    "mime_type": mime_type,
                    "duration_sec": duration_sec,
                    "size_bytes": size_bytes,
                    "last_accessed_at": now,
                },
            )
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def touch_hit(self, content_hash: str) -> None:
        stmt = (
            update(TtsAudioCache)
            .where(TtsAudioCache.content_hash == content_hash)
            .values(
                hit_count=TtsAudioCache.hit_count + 1,
                last_accessed_at=datetime.now(timezone.utc),
            )
        )
        await self.session.execute(stmt)
        await self.session.commit()
