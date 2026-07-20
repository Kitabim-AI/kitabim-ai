"""Auto-correction rules repository with SQLAlchemy"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import cache_config
from app.db.models import AutoCorrectRule
from app.db.repositories.base_repository import BaseRepository
from app.services.cache_service import cache_service


class AutoCorrectRulesRepository(BaseRepository[AutoCorrectRule]):
    """Repository for auto-correction rules"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, AutoCorrectRule)

    async def get_active_pairs(self) -> list[tuple[str, str]]:
        """All active (misspelled_word, corrected_word) pairs, ordered for stable output."""
        result = await self.session.execute(
            select(AutoCorrectRule.misspelled_word, AutoCorrectRule.corrected_word)
            .where(AutoCorrectRule.is_active)
            .order_by(AutoCorrectRule.misspelled_word)
        )
        return [(row.misspelled_word, row.corrected_word) for row in result]

    async def get_frequent_corrections_block(self) -> str:
        """The active rule set formatted for OCR_PROMPT's {frequent_corrections}
        placeholder, cached so every OCR page call doesn't hit the DB."""
        cached = await cache_service.get(cache_config.KEY_OCR_FREQUENT_CORRECTIONS)
        if cached is not None:
            return cached

        pairs = await self.get_active_pairs()
        block = _format_frequent_corrections(pairs)

        await cache_service.set(
            cache_config.KEY_OCR_FREQUENT_CORRECTIONS,
            block,
            ttl=cache_config.TTL_OCR_FREQUENT_CORRECTIONS,
        )
        return block


def _format_frequent_corrections(pairs: list[tuple[str, str]]) -> str:
    entries = [f"{wrong} -> {correct}" for wrong, correct in pairs]
    lines = [" | ".join(entries[i : i + 6]) for i in range(0, len(entries), 6)]
    return "\n".join(lines)


async def invalidate_frequent_corrections_cache() -> None:
    """Call after any create/update/delete on auto_correct_rules."""
    await cache_service.delete(cache_config.KEY_OCR_FREQUENT_CORRECTIONS)
