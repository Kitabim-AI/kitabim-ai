from __future__ import annotations

import random
import asyncio
import fitz

from app.core.config import settings
from app.core.prompts import OCR_PROMPT
from app.langchain.models import generate_text_with_image
from app.utils.text import clean_uyghur_text


async def ocr_page_with_gemini(page: fitz.Page, model_name: str = "gemini-2.0-flash") -> str:
    """
    OCR a page using Gemini Vision model.

    Args:
        page: The fitz.Page to OCR
        model_name: The Gemini model to use (should be fetched from system_configs)
    """
    pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
    img_bytes = pix.tobytes("jpeg")

    for attempt in range(settings.ocr_max_retries):
        try:
            text = await generate_text_with_image(
                OCR_PROMPT,
                img_bytes,
                model_name,
            )
            return clean_uyghur_text(text or "")
        except Exception as exc:
            err_msg = str(exc)
            if any(x in err_msg or x in err_msg.lower() for x in ["429", "503", "overloaded", "resource_exhausted"]) and attempt < settings.ocr_max_retries - 1:
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
