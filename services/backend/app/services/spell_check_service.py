from __future__ import annotations

import json
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel

from app.core.config import settings
from app.core.prompts import SPELL_CHECK_PROMPT
from app.langchain.chains import build_text_chain


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


class SpellCheckService:
    def __init__(self) -> None:
        self.chain = build_text_chain(
            SPELL_CHECK_PROMPT,
            settings.gemini_model_name,
            run_name="spell_check_chain",
        )

    async def check_page_text(self, page_text: str, page_number: int, language: str = "Uyghur") -> PageSpellCheck:
        if not page_text or not page_text.strip():
            return PageSpellCheck(pageNumber=page_number, corrections=[], totalIssues=0, checkedAt="")

        response_text = await self.chain.ainvoke({"language": language, "text": page_text})
        response_text = response_text.strip()

        if response_text.startswith("```"):
            lines = response_text.split("\n")
            response_text = "\n".join(lines[1:-1]) if len(lines) > 2 else response_text
            if response_text.startswith("json"):
                response_text = response_text[4:].strip()

        try:
            corrections_data = json.loads(response_text)
        except json.JSONDecodeError:
            corrections_data = []

        corrections = [SpellCorrection(**item) for item in corrections_data]
        return PageSpellCheck(
            pageNumber=page_number,
            corrections=corrections,
            totalIssues=len(corrections),
            checkedAt=datetime.utcnow().isoformat(),
        )

    async def check_book(self, book_id: str, db) -> Dict[int, PageSpellCheck]:
        book = await db.books.find_one({"id": book_id})
        if not book:
            raise ValueError(f"Book {book_id} not found")

        results: Dict[int, PageSpellCheck] = {}
        for page_result in book.get("results", []):
            page_num = page_result.get("pageNumber")
            page_text = page_result.get("text", "")
            if not page_text or page_result.get("status") != "completed":
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
        book = await db.books.find_one({"id": book_id})
        if not book:
            return False

        results = book.get("results", [])
        page_idx = None
        for idx, page in enumerate(results):
            if page.get("pageNumber") == page_number:
                page_idx = idx
                break

        if page_idx is None:
            return False

        page_text = results[page_idx].get("text", "")
        sorted_corrections = sorted(corrections, key=lambda x: x.get("position", 0), reverse=True)
        for correction in sorted_corrections:
            original = correction.get("original", "")
            corrected = correction.get("corrected", "")
            if original and corrected:
                page_text = page_text.replace(original, corrected)

        results[page_idx]["text"] = page_text
        results[page_idx]["status"] = "completed"
        results[page_idx]["isVerified"] = True
        results[page_idx].pop("embedding", None)

        all_text = "\n\n".join(
            page.get("text", "") for page in results if page.get("status") == "completed"
        )

        await db.books.update_one(
            {"id": book_id},
            {
                "$set": {
                    "results": results,
                    "content": all_text,
                    "lastUpdated": datetime.utcnow(),
                }
            },
        )
        return True


spell_check_service = SpellCheckService()
