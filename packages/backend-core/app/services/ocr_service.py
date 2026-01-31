from __future__ import annotations

import random
import asyncio
import httpx
import fitz
from google.genai import types

from app.core.config import settings
from app.core.prompts import OCR_PROMPT
from app.services import genai_client
from app.utils.text import clean_uyghur_text


async def ocr_page_with_gemini(page: fitz.Page) -> str:
    pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
    img_bytes = pix.tobytes("jpeg")

    for attempt in range(settings.ocr_max_retries):
        try:
            response = await genai_client.generate_content(
                model=settings.gemini_model_name,
                contents=[
                    OCR_PROMPT,
                    types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                ],
            )
            text = response.text or ""
            return clean_uyghur_text(text)
        except Exception as exc:
            err_msg = str(exc)
            if ("503" in err_msg or "overloaded" in err_msg.lower()) and attempt < settings.ocr_max_retries - 1:
                await asyncio.sleep((2 ** (attempt + 1)) + random.uniform(0, 1))
                continue
            raise


async def ocr_page_with_local(page: fitz.Page, book_title: str, page_num: int) -> str:
    pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
    img_bytes = pix.tobytes("jpeg")

    url = f"{settings.local_ocr_url.rstrip('/')}/api/ocr/recognize"
    async with httpx.AsyncClient(timeout=60.0) as client:
        files = {"file": (f"page_{page_num}.jpg", img_bytes, "image/jpeg")}
        data = {
            "lang": "ukij",
            "mode": "line",
            "book_name": book_title,
            "page_num": page_num,
        }
        response = await client.post(url, files=files, data=data)
        response.raise_for_status()
        payload = response.json() or {}
        return clean_uyghur_text(payload.get("text", ""))


async def ocr_page(page: fitz.Page, book_title: str, page_num: int) -> str:
    if settings.ocr_provider == "local":
        return await ocr_page_with_local(page, book_title, page_num)
    return await ocr_page_with_gemini(page)
