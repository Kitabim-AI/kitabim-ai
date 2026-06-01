from __future__ import annotations

import random
import asyncio
import fitz
import httpx

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


async def ocr_page_with_easyocr(page: fitz.Page) -> str:
    """
    OCR a page using the self-hosted EasyOCR microservice.

    Args:
        page: The fitz.Page to OCR
    """
    # 3.0 matrix scales the PDF page image resolution for OCR accuracy
    pix = page.get_pixmap(matrix=fitz.Matrix(3.0, 3.0))
    img_bytes = pix.tobytes("jpeg")

    async with httpx.AsyncClient(timeout=settings.ocr_service_timeout) as client:
        response = await client.post(
            f"{settings.ocr_service_url}/ocr",
            files={"image": ("page.jpg", img_bytes, "image/jpeg")},
        )
        response.raise_for_status()

    result = response.json()
    return clean_uyghur_text(result["text"] or "")


async def ocr_page(
    page: fitz.Page,
    book_title: str,
    page_num: int,
    provider: str = "gemini",
    model_name: str = "gemini-2.0-flash",
) -> str:
    """
    OCR a page using the configured provider (gemini or easyocr).
    """
    if provider == "easyocr":
        return await ocr_page_with_easyocr(page)
    return await ocr_page_with_gemini(page, model_name=model_name)

