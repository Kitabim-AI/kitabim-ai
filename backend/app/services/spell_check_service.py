"""
Spell checking service for Uyghur text using Gemini AI
"""
import google.generativeai as genai
import json
import os
from typing import List, Dict, Optional
from pydantic import BaseModel

class SpellCorrection(BaseModel):
    """Model for a single spelling correction"""
    original: str
    corrected: str
    position: Optional[int] = None  # Character position in text
    confidence: float  # 0-1 score
    reason: str
    context: Optional[str] = None  # Surrounding text for context

class PageSpellCheck(BaseModel):
    """Model for spell check results of a page"""
    pageNumber: int
    corrections: List[SpellCorrection]
    totalIssues: int
    checkedAt: str

class SpellCheckService:
    """Service for checking and correcting spelling in Uyghur books"""
    
    def __init__(self):
        self.model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.0-flash-exp")
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = genai.GenerativeModel(self.model_name)
    
    async def check_page_text(self, page_text: str, page_number: int, language: str = "Uyghur") -> PageSpellCheck:
        """
        Check a single page for spelling and OCR errors
        
        Args:
            page_text: The text content of the page
            page_number: The page number
            language: Language of the text (default: Uyghur)
            
        Returns:
            PageSpellCheck with corrections
        """
        if not page_text or not page_text.strip():
            return PageSpellCheck(
                pageNumber=page_number,
                corrections=[],
                totalIssues=0,
                checkedAt=""
            )
        
        prompt = f"""You are an expert {language} language and OCR error detection specialist.

Analyze the following text for:
1. Spelling errors
2. OCR recognition errors (common for scanned documents)
3. Grammar issues that might be OCR-related
4. Character confusion (similar-looking characters)

Text to analyze:
{page_text}

Return a JSON array of corrections. Each correction should have:
- "original": the incorrect text as it appears
- "corrected": the suggested correction
- "confidence": a number from 0 to 1 indicating how confident you are
- "reason": brief explanation of why this needs correction
- "context": a short snippet showing the surrounding text (max 50 chars)

Only include corrections where confidence >= 0.6.
If no issues found, return an empty array: []

Return ONLY the JSON array, no other text."""

        try:
            response = self.model.generate_content(prompt)
            result_text = response.text.strip()
            
            # Extract JSON from markdown code blocks if present
            if result_text.startswith("```"):
                lines = result_text.split("\n")
                result_text = "\n".join(lines[1:-1]) if len(lines) > 2 else result_text
                if result_text.startswith("json"):
                    result_text = result_text[4:].strip()
            
            corrections_data = json.loads(result_text)
            
            corrections = [
                SpellCorrection(**item) for item in corrections_data
            ]
            
            from datetime import datetime
            return PageSpellCheck(
                pageNumber=page_number,
                corrections=corrections,
                totalIssues=len(corrections),
                checkedAt=datetime.utcnow().isoformat()
            )
            
        except Exception as e:
            print(f"Error checking page {page_number}: {e}")
            from datetime import datetime
            return PageSpellCheck(
                pageNumber=page_number,
                corrections=[],
                totalIssues=0,
                checkedAt=datetime.utcnow().isoformat()
            )
    
    async def check_book(self, book_id: str, db) -> Dict[int, PageSpellCheck]:
        """
        Check all pages of a book for spelling errors
        
        Args:
            book_id: The book ID
            db: Database connection
            
        Returns:
            Dictionary mapping page numbers to their spell check results
        """
        book = await db.books.find_one({"_id": book_id})
        if not book:
            raise ValueError(f"Book {book_id} not found")
        
        results = {}
        for page_result in book.get("results", []):
            page_num = page_result.get("pageNumber")
            page_text = page_result.get("text", "")
            
            if page_text and page_result.get("status") == "success":
                spell_check = await self.check_page_text(page_text, page_num)
                if spell_check.totalIssues > 0:
                    results[page_num] = spell_check
        
        return results
    
    async def apply_corrections(
        self, 
        book_id: str, 
        page_number: int, 
        corrections: List[Dict],
        db
    ) -> bool:
        """
        Apply approved corrections to a page
        
        Args:
            book_id: The book ID
            page_number: The page number
            corrections: List of corrections to apply (from frontend)
            db: Database connection
            
        Returns:
            True if successful
        """
        book = await db.books.find_one({"_id": book_id})
        if not book:
            return False
        
        # Find the page in results
        results = book.get("results", [])
        page_idx = None
        for idx, page in enumerate(results):
            if page.get("pageNumber") == page_number:
                page_idx = idx
                break
        
        if page_idx is None:
            return False
        
        # Apply corrections to the text
        page_text = results[page_idx].get("text", "")
        
        # Sort corrections by position (if available) to apply from end to start
        # This prevents position shifts when replacing text
        sorted_corrections = sorted(
            corrections, 
            key=lambda x: x.get("position", 0),
            reverse=True
        )
        
        for correction in sorted_corrections:
            original = correction.get("original", "")
            corrected = correction.get("corrected", "")
            if original and corrected:
                # Replace all occurrences
                page_text = page_text.replace(original, corrected)
        
        # Update the page text and metadata
        results[page_idx]["text"] = page_text
        results[page_idx]["status"] = "completed"
        results[page_idx]["isVerified"] = True
        # Clear the old embedding so it gets regenerated
        if "embedding" in results[page_idx]:
            del results[page_idx]["embedding"]
        
        # Update the full content if it exists
        if book.get("content"):
            # Rebuild content from all pages
            all_text = "\n\n".join(
                page.get("text", "") for page in results 
                if page.get("status") == "completed"
            )
            await db.books.update_one(
                {"_id": book_id},
                {
                    "$set": {
                        "results": results,
                        "content": all_text,
                        "lastUpdated": datetime.utcnow()
                    }
                }
            )
        else:
            await db.books.update_one(
                {"_id": book_id},
                {
                    "$set": {
                        "results": results,
                        "lastUpdated": datetime.utcnow()
                    }
                }
            )
        
        return True

# Singleton instance
spell_check_service = SpellCheckService()
