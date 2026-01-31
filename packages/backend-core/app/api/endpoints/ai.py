from __future__ import annotations

import base64
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from google.genai import types

from app.core.config import settings
from app.core.prompts import OCR_PROMPT
from app.services import genai_client
from app.utils.observability import log_json
from app.utils.text import clean_uyghur_text

router = APIRouter()
logger = logging.getLogger("app.ai")


class OcrRequest(BaseModel):
    imageBase64: str


class OcrResponse(BaseModel):
    text: str


def _decode_base64_image(data: str) -> bytes:
    if not data:
        raise ValueError("Missing image data")
    if "," in data:
        _, data = data.split(",", 1)
    return base64.b64decode(data)


@router.post("/ocr", response_model=OcrResponse)
async def ocr_image(req: OcrRequest):
    if not settings.gemini_api_key:
        raise HTTPException(status_code=500, detail="Gemini API key not configured")

    try:
        img_bytes = _decode_base64_image(req.imageBase64)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid base64 image: {exc}")

    try:
        response = await genai_client.generate_content(
            model=settings.gemini_model_name,
            contents=[
                OCR_PROMPT,
                types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
            ],
        )
        text = response.text or ""
        return {"text": clean_uyghur_text(text)}
    except Exception as exc:
        log_json(logger, logging.ERROR, "OCR image failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"OCR failed: {exc}")
