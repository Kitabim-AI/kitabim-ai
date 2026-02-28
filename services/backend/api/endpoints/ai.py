from __future__ import annotations

import base64
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.core.prompts import OCR_PROMPT
from app.models.user import User
from app.langchain.models import generate_text_with_image
from app.utils.observability import log_json
from app.utils.text import clean_uyghur_text
from auth.dependencies import require_editor
from app.core.i18n import t

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
async def ocr_image(
    req: OcrRequest,
    current_user: User = Depends(require_editor),
):
    if not settings.gemini_api_key:
        raise HTTPException(status_code=500, detail=t("errors.ai.gemini_api_key_missing"))

    try:
        img_bytes = _decode_base64_image(req.imageBase64)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=t("errors.ai.invalid_base64_image", error=str(exc)))

    try:
        text = await generate_text_with_image(
            OCR_PROMPT,
            img_bytes,
            settings.gemini_model_name,
        )
        return {"text": clean_uyghur_text(text or "")}
    except Exception as exc:
        log_json(logger, logging.ERROR, "OCR image failed", error=str(exc))
        raise HTTPException(status_code=500, detail=t("errors.ai.ocr_failed", error=str(exc)))
