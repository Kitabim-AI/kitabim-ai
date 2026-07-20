from __future__ import annotations

import random
import asyncio
import fitz

from app.core.config import settings
from app.core.prompts import OCR_PROMPT
from app.db import session as db_session
from app.db.repositories.auto_correct_rules_repository import (
    AutoCorrectRulesRepository,
)
from app.llm.models import generate_text_with_image, is_transient_error
from app.utils.text import clean_uyghur_text


async def _build_ocr_prompt() -> str:
    async with db_session.async_session_factory() as session:
        frequent_corrections = await AutoCorrectRulesRepository(
            session
        ).get_frequent_corrections_block()
    return OCR_PROMPT.format(frequent_corrections=frequent_corrections)


async def ocr_page_with_gemini(
    page: fitz.Page, model_name: str = "gemini-2.0-flash", timeout: float | None = None
) -> str:
    pix = page.get_pixmap(
        matrix=fitz.Matrix(settings.ocr_page_zoom_factor, settings.ocr_page_zoom_factor)
    )
    img_bytes = pix.tobytes("jpeg")
    prompt = await _build_ocr_prompt()

    for attempt in range(settings.ocr_max_retries):
        try:
            text = await generate_text_with_image(
                prompt,
                img_bytes,
                model_name,
                timeout=timeout,
            )
            return clean_uyghur_text(text or "")
        except Exception as exc:
            if is_transient_error(exc) and attempt < settings.ocr_max_retries - 1:
                await asyncio.sleep((2 ** (attempt + 1)) + random.uniform(0, 1))
                continue
            raise
