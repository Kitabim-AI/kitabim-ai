from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

import logging
from pydantic import BaseModel, Field
from langchain_core.output_parsers import PydanticOutputParser

from app.core.config import settings
from app.core.prompts import SPELL_CHECK_PROMPT
from app.langchain.chains import build_structured_chain
from app.utils.markdown import normalize_markdown, strip_markdown
from app.utils.observability import log_json


class SpellCorrection(BaseModel):
    original: str
    corrected: str
    position: Optional[int] = None
    confidence: float
    reason: str
    context: Optional[str] = None


class PageSpellCheck(BaseModel):
    pageNumber: int
    corrections: List[SpellCorrection]
    totalIssues: int
    checkedAt: str


class SpellCheckResponse(BaseModel):
    corrections: List[SpellCorrection] = Field(default_factory=list)


class SpellCheckService:
    def __init__(self) -> None:
        parser = PydanticOutputParser(pydantic_object=SpellCheckResponse)
        self.chain = build_structured_chain(
            SPELL_CHECK_PROMPT,
            settings.gemini_model_name,
            parser,
            run_name="spell_check_chain",
        )
        self.logger = logging.getLogger("app.spellcheck")

    async def check_page_text(self, page_text: str, page_number: int, language: str = "Uyghur") -> PageSpellCheck:
        if not page_text or not page_text.strip():
            return PageSpellCheck(pageNumber=page_number, corrections=[], totalIssues=0, checkedAt="")

        try:
            clean_text = strip_markdown(page_text)
            if not clean_text.strip():
                return PageSpellCheck(pageNumber=page_number, corrections=[], totalIssues=0, checkedAt="")
            response = await self.chain.ainvoke({"language": language, "text": clean_text})
            corrections = response.corrections if response else []
        except Exception as exc:
            log_json(self.logger, logging.WARNING, "Spell check parsing failed", error=str(exc))
            corrections = []
        return PageSpellCheck(
            pageNumber=page_number,
            corrections=corrections,
            totalIssues=len(corrections),
            checkedAt=datetime.utcnow().isoformat(),
        )

    async def check_book(self, book_id: str, db) -> Dict[int, PageSpellCheck]:
        pages_cursor = db.pages.find({"bookId": book_id, "status": "completed"})
        
        results: Dict[int, PageSpellCheck] = {}
        async for page_rec in pages_cursor:
            page_num = page_rec.get("pageNumber")
            page_text = page_rec.get("text", "")
            if not page_text:
                continue
            spell_check = await self.check_page_text(page_text, page_num)
            if spell_check.totalIssues > 0:
                results[page_num] = spell_check

        return results

    async def apply_corrections(
        self,
        book_id: str,
        page_number: int,
        corrections: List[Dict],
        db,
    ) -> bool:
        page_rec = await db.pages.find_one({"bookId": book_id, "pageNumber": page_number})
        if not page_rec:
            return False

        page_text = page_rec.get("text", "")
        sorted_corrections = sorted(corrections, key=lambda x: x.get("position", 0), reverse=True)
        for correction in sorted_corrections:
            original = correction.get("original", "")
            corrected = correction.get("corrected", "")
            if original and corrected:
                page_text = page_text.replace(original, corrected)

        new_text = normalize_markdown(page_text)
        
        await db.pages.update_one(
            {"bookId": book_id, "pageNumber": page_number},
            {
                "$set": {
                    "text": new_text,
                    "status": "completed",
                    "isVerified": True,
                    "lastUpdated": datetime.utcnow()
                },
                "$unset": {"embedding": ""}
            }
        )

        await db.books.update_one(
            {"id": book_id},
            {
                "$set": {
                    "lastUpdated": datetime.utcnow(),
                }
            },
        )
        return True


spell_check_service = SpellCheckService()
