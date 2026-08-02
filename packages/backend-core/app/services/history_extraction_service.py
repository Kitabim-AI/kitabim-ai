"""Service for extracting and enriching Uyghur historical terms from book pages."""

from __future__ import annotations

import json
import logging
from typing import Any, List, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import SystemConfig
from app.db.repositories.dictionary_repository import DictionaryRepository

logger = logging.getLogger(__name__)


EXTRACTION_PROMPT_TEMPLATE = """سەن ئۇيغۇر تارىخى تەتقىقاتچىسى ئېكىسپېرت. تۆۋەندىكى كىتاب بەتلىرىدىن مۇھىم تارىخىي ئاتالغۇلارنى (شەخسلەر، ۋەقە-ھادىسىلەر، خانلىقلار/سۇلالىلەر، ئاتالغۇ-جاي-ئورۇنلار) ئاجرىتىپ چىقاردىغان ۋەزىپىنى ئۆتەيسەن.

ھەر بىر تارىخىي ئاتالغۇ ئۈچۈن تۆۋەندىكى شەكىلدە JSON ئوبيېكتى قايتۇرىسەن:
- term: تارىخىي ئاتالغۇنىڭ ئىسمى (مەسىلەن: "سۇلتان سۇتۇق بۇغراخان", "قاراخانىيلار خاندانلىقى")
- transliteration: لاتىنچە كۆچۈرۈلمىسى ياكى يىل-دەۋرى (مەسىلەن: "Sultan Sutuk Bughra Khan, ? - 955")
- definition: ئاتالغۇنىڭ تولۇق بايانى ۋە تارىخىي مەزمۇنى (مەنبە كۆرسەتمىسى ئىپادىسى [1] بىلەن بىللە)
- category: "figure" (شەخس), "event" (ۋەقە-ھادىسە), "dynasty" (خانلىق), ياكى "concept" (ئاتالغۇ/جاي)
- significance_score: 1 دىن 10 غىچە بولغان تارىخىي مۇھىملىق دەرىجىسى (10: ئەڭ مۇھىم خاقان/ۋەقە/كلاسسىك ئەسەر, 1-4: ئادەتتىكى ئۇسۇل ياكى كىچىك ئىسىم - چىقىرىۋېتىلىدۇ)
- significance_reason: تارىخىي مۇھىملىق باھاسىنىڭ 1 جۈملىلىك سەۋەبى
- pages: بەت نومۇرلىرى تىزىملىكى (مەسىلەن: [45, 46])

كىتاب بەتلىرى:
{pages_text}

JSON FORMAT REQUIRED:
{{
  "entities": [
    {{
      "term": "...",
      "transliteration": "...",
      "definition": "...",
      "category": "figure",
      "significance_score": 9,
      "significance_reason": "...",
      "pages": [45, 46]
    }}
  ]
}}
"""

ENRICHMENT_PROMPT_TEMPLATE = """سەن ئۇيغۇر تارىخى تەتقىقاتچىسى. بىر تارىخىي ئاتالغۇ ئۈچۈن مەۋجۇت بايان بىلەن يېڭى كىتاب بەتلىرىدىن تېپىلغان يېڭى پاكىتلار بېرىلدى.

ئاتالغۇ: {term}
مەۋجۇت بايان: {existing_definition}

يېڭى مەنبە تېكىستى ({new_source_title}, {new_pages}):
{new_text}

ئىككى مەنبەدىكى پاكىتلارنى بىرPlatform قىلىپ، تەپسىلىي، مۇكەممەل بىر بايان يېزىپ چىق. بارلىق يېڭى پاكىتلارنى كىرگۈز. ئىچكى مەنبە بەلگىسى [{source_index}] نى ئىشلەت.
JSON format:
{{
  "enriched_definition": "..."
}}
"""


class HistoryExtractionService:
    def __init__(self, session: AsyncSession, gemini_client: Any = None):
        self.session = session
        self.repo = DictionaryRepository(session)
        self.gemini_client = gemini_client

    async def _get_system_config_model(self) -> str:
        """Fetch the dynamic history extraction model name from system_config."""
        stmt = select(SystemConfig).where(
            SystemConfig.key == "history_extraction_model"
        )
        res = await self.session.execute(stmt)
        config = res.scalar_one_or_none()
        if config and config.value.strip():
            return config.value.strip()
        return "gemini-2.5-flash"

    async def _call_llm_extraction(
        self, pages_text: str, model_name: str
    ) -> List[Dict[str, Any]]:
        """Call Gemini API for structured JSON extraction."""
        prompt = EXTRACTION_PROMPT_TEMPLATE.format(pages_text=pages_text)
        if self.gemini_client and hasattr(self.gemini_client, "generate_structured"):
            res = await self.gemini_client.generate_structured(prompt, model=model_name)
            return res.get("entities", [])

        # Fallback or standard call via internal LLM service
        try:
            from app.services.rag.agent.tools import call_gemini_api

            raw_res = await call_gemini_api(
                prompt, model=model_name, response_format="json"
            )
            data = json.loads(raw_res)
            return data.get("entities", [])
        except Exception as e:
            logger.warning(f"Fallback LLM extraction call failed/mocked: {e}")
            return []

    async def process_book_pages(
        self,
        book_id: str,
        book_title: str,
        pages_data: List[Dict[str, Any]],
        volume: int | None = None,
        min_significance: int = 5,
        batch_size: int = 15,
        overlap: int = 2,
    ) -> List[Dict[str, Any]]:
        """Process OCR book pages with sliding overlap window and stage candidates."""
        model_name = await self._get_system_config_model()
        staged_results = []

        if not pages_data:
            return staged_results

        # Sort pages by page_number
        pages_data = sorted(pages_data, key=lambda x: x.get("page_number", 0))

        # Sliding window batching
        i = 0
        while i < len(pages_data):
            batch = pages_data[i : i + batch_size]
            if not batch:
                break

            # Construct pages_text
            text_blocks = []
            for p in batch:
                p_num = p.get("page_number", 0)
                content = p.get("content", "").strip()
                if content:
                    text_blocks.append(f"--- PAGE {p_num} ---\n{content}")

            pages_text = "\n\n".join(text_blocks)
            if pages_text.strip():
                entities = await self._call_llm_extraction(pages_text, model_name)
                for ent in entities:
                    score = ent.get("significance_score", 5)
                    if score < min_significance:
                        continue

                    staged_item = await self._stage_entity(
                        book_id=book_id,
                        book_title=book_title,
                        volume=volume,
                        entity=ent,
                        model_name=model_name,
                    )
                    if staged_item:
                        staged_results.append(staged_item)

            # Move window by (batch_size - overlap)
            step = max(1, batch_size - overlap)
            i += step

        return staged_results

    async def _stage_entity(
        self,
        book_id: str,
        book_title: str,
        volume: int | None,
        entity: Dict[str, Any],
        model_name: str,
    ) -> Dict[str, Any] | None:
        term = entity.get("term", "").strip()
        if not term:
            return None

        pages = entity.get("pages", [])
        category = entity.get("category", "general")
        score = entity.get("significance_score", 5)
        reason = entity.get("significance_reason", "")
        definition = entity.get("definition", "").strip()
        transliteration = entity.get("transliteration", "")
        letter_group = term[0].upper() if term else "A"

        # Check existing published record or pending staging record
        existing_live = await self.repo.find_matching_history_term(term)
        existing_staging = await self.repo.find_matching_staging_term(term)

        if existing_live or existing_staging:
            # Incremental enrichment workflow
            existing_def = (
                existing_live.definition
                if existing_live
                else existing_staging.definition
            )
            existing_sources = (
                existing_live.sources if existing_live else existing_staging.sources
            )
            existing_id = existing_live.id if existing_live else None

            # Generate new source index
            new_source_idx = len(existing_sources) + 1
            new_source = {
                "id": new_source_idx,
                "book_id": book_id,
                "book_title": book_title,
                "volume": volume,
                "pages": pages,
            }

            merged_sources = list(existing_sources)
            # Add or update source entry
            found = False
            for s in merged_sources:
                if s.get("book_id") == book_id:
                    s["pages"] = sorted(list(set(s.get("pages", []) + pages)))
                    found = True
                    break
            if not found:
                merged_sources.append(new_source)

            staged = await self.repo.create_staging_term(
                book_id=book_id,
                term=term,
                transliteration=transliteration
                or (
                    existing_live.transliteration
                    if existing_live
                    else existing_staging.transliteration
                ),
                definition=definition,
                original_definition=existing_def,
                category=category,
                significance_score=score,
                significance_reason=reason,
                is_ai_generated=True,
                entry_type="enrichment",
                existing_dictionary_id=existing_id,
                letter_group=letter_group,
                sources=merged_sources,
            )
        else:
            # New candidate
            source_item = {
                "id": 1,
                "book_id": book_id,
                "book_title": book_title,
                "volume": volume,
                "pages": pages,
            }
            staged = await self.repo.create_staging_term(
                book_id=book_id,
                term=term,
                transliteration=transliteration,
                definition=definition,
                category=category,
                significance_score=score,
                significance_reason=reason,
                is_ai_generated=True,
                entry_type="new",
                letter_group=letter_group,
                sources=[source_item],
            )

        return {
            "id": staged.id,
            "term": staged.term,
            "category": staged.category,
            "significanceScore": staged.significance_score,
            "entryType": staged.entry_type,
        }
