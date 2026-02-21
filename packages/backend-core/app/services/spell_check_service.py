from __future__ import annotations

from datetime import datetime, timezone
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
            checkedAt=datetime.now(timezone.utc).isoformat(),
        )

    async def check_book(self, book_id: str, session: AsyncSession) -> Dict[int, PageSpellCheck]:
        from app.db.repositories.pages import PagesRepository
        pages_repo = PagesRepository(session)
        
        pages = await pages_repo.find_by_book(book_id)
        
        results: Dict[int, PageSpellCheck] = {}
        for page_rec in pages:
            if page_rec.status != "ocr_done":
                continue
            page_num = page_rec.page_number
            page_text = page_rec.text or ""
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
        session: AsyncSession,
        user_email: Optional[str] = None
    ) -> bool:
        from app.db.repositories.books import BooksRepository
        from app.db.repositories.pages import PagesRepository
        books_repo = BooksRepository(session)
        pages_repo = PagesRepository(session)

        page_rec = await pages_repo.find_one(book_id, page_number)
        if not page_rec:
            return False

        page_text = page_rec.text or ""
        sorted_corrections = sorted(corrections, key=lambda x: x.get("position", 0), reverse=True)
        for correction in sorted_corrections:
            original = correction.get("original", "")
            corrected = correction.get("corrected", "")
            if original and corrected:
                page_text = page_text.replace(original, corrected)

        new_text = normalize_markdown(page_text)
        
        # Update page using raw SQL for embedding = NULL (consistent with books.py endpoints)
        from sqlalchemy import text
        await session.execute(
            text("""
                UPDATE pages
                SET text = :text,
                    status = 'ocr_done',
                    is_verified = TRUE,
                    is_indexed = FALSE,
                    last_updated = :now,
                    updated_by = :updated_by
                WHERE book_id = :book_id AND page_number = :page_number
            """),
            {
                "text": new_text,
                "now": datetime.now(timezone.utc),
                "updated_by": user_email,
                "book_id": book_id,
                "page_number": page_number
            }
        )

        # Update book last_updated
        await books_repo.update_one(
            book_id,
            last_updated=datetime.now(timezone.utc),
            updated_by=user_email
        )
        
        # Flush or commit? Usually the controller (api endpoint) handles the final commit
        await session.flush()
        return True


spell_check_service = SpellCheckService()
