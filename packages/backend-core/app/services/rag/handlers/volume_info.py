"""VolumeInfoHandler — returns volume and page-count info for a book title."""
from __future__ import annotations

from typing import AsyncIterator

from app.core.i18n import t
from app.services.rag.base_handler import QueryHandler
from app.services.rag.context import QueryContext
from app.services.rag.utils import normalize_uyghur

_VOLUME_KEYWORDS = [
    "نەچچە تومدىن", "قانچە تومدىن", "نەچچە توم", "قانچە توم",
    "توملار سانى", "قانچە بەتتىن", "نەچچە بەتتىن",
    "قانچە بەت", "نەچچە بەت",
    "توملىرى قانچە", "توملىرى نەچچە",
    "نەچچە قىسىمدىن", "قانچە قىسىمدىن", "نەچچە قىسىم", "قانچە قىسىم",
    "قىسىملار سانى", "قانچە بەتتىن", "نەچچە بەتتىن",
    "قانچە بەت", "نەچچە بەت",
    "قىسىملېرى قانچە", "قىسىملېرى نەچچە",
]
_VOLUME_KEYWORDS_NORM = [normalize_uyghur(k) for k in _VOLUME_KEYWORDS]


class VolumeInfoHandler(QueryHandler):
    """Returns structured volume / page-count info for a book title in the question.

    Falls back to CatalogHandler when no matching title is found.
    """

    intent_name = "volume_info"
    priority = 22

    def can_handle(self, ctx: QueryContext) -> bool:
        q = normalize_uyghur(ctx.question.strip())
        return any(k in q for k in _VOLUME_KEYWORDS_NORM)

    async def handle(self, ctx: QueryContext) -> str:
        from app.db.repositories.books import BooksRepository
        repo = BooksRepository(ctx.session)
        volumes = await repo.find_volume_info_by_title_in_question(
            ctx.question, ctx.character_categories or None
        )
        if volumes:
            ctx.retrieved_count = len(volumes)
            return self._format(volumes)

        from app.services.rag.handlers.catalog import CatalogHandler
        return await CatalogHandler().handle(ctx)

    async def handle_stream(self, ctx: QueryContext) -> AsyncIterator[str]:
        from app.db.repositories.books import BooksRepository
        repo = BooksRepository(ctx.session)
        volumes = await repo.find_volume_info_by_title_in_question(
            ctx.question, ctx.character_categories or None
        )
        if volumes:
            ctx.retrieved_count = len(volumes)
            yield self._format(volumes)
            return

        from app.services.rag.handlers.catalog import CatalogHandler
        async for chunk in CatalogHandler().handle_stream(ctx):
            yield chunk

    @staticmethod
    def _format(volumes: list) -> str:
        title = volumes[0]["title"]
        lines = [t("rag.volume_info_header", title=title)]
        for v in volumes:
            vol_label = t("rag.volume_label", volume=v["volume"]) if v["volume"] is not None else t("rag.volume_unknown")
            pages = t("rag.pages_suffix", pages=v["total_pages"]) if v["total_pages"] else ""
            lines.append(f"- {vol_label}{pages}")
        return "\n".join(lines)
