from __future__ import annotations

import random
import asyncio
import fitz

from app.core.config import settings
from app.core.prompts import OCR_PROMPT
from app.langchain.models import generate_text_with_image
from app.utils.text import clean_uyghur_text


async def ocr_page_with_gemini(page: fitz.Page) -> str:
    pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
    img_bytes = pix.tobytes("jpeg")

    for attempt in range(settings.ocr_max_retries):
        try:
            text = await generate_text_with_image(
                OCR_PROMPT,
                img_bytes,
                settings.gemini_model_name,
            )
            return clean_uyghur_text(text or "")
        except Exception as exc:
            err_msg = str(exc)
            if ("503" in err_msg or "overloaded" in err_msg.lower()) and attempt < settings.ocr_max_retries - 1:
                await asyncio.sleep((2 ** (attempt + 1)) + random.uniform(0, 1))
                continue
            raise


async def ocr_page(
    page: fitz.Page,
    book_title: str,
    page_num: int,
    provider: str | None = None,
) -> str:
    # We now exclusively use Gemini for OCR
    return await ocr_page_with_gemini(page)
