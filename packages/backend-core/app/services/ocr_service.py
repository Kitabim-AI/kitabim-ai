from __future__ import annotations

import random
import asyncio
import fitz

from app.core.config import settings
from app.core.prompts import OCR_PROMPT
from app.llm.models import generate_text_with_image, is_transient_error
from app.utils.text import clean_uyghur_text


async def ocr_page_with_gemini(
    page: fitz.Page, model_name: str = "gemini-2.0-flash", timeout: float | None = None
) -> str:
    pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
    img_bytes = pix.tobytes("jpeg")

    for attempt in range(settings.ocr_max_retries):
        try:
            text = await generate_text_with_image(
                OCR_PROMPT,
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
