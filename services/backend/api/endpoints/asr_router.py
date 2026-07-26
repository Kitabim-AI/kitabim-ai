from __future__ import annotations

import asyncio
import base64
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.core.config import settings
from app.core.i18n import t
from app.models.user import User
from app.services.asr_service import UyghurASRService
from app.utils.observability import log_json
from auth.dependencies import require_reader

router = APIRouter()
logger = logging.getLogger("app.asr")

ALLOWED_AUDIO_CONTENT_TYPES = {
    "audio/webm",
    "audio/ogg",
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/mpeg",
    "audio/mp4",
    "audio/m4a",
    "audio/x-m4a",
}
ALLOWED_AUDIO_EXTENSIONS = (".webm", ".ogg", ".wav", ".mp3", ".mp4", ".m4a")


class TranscribeBase64Request(BaseModel):
    audioBase64: str


class TranscribeResponse(BaseModel):
    text_uey: str
    text_uly: str
    raw_pred: str


def _validate_upload_content_type(file: UploadFile) -> None:
    content_type = (file.content_type or "").lower()
    filename = (file.filename or "").lower()
    has_allowed_type = content_type in ALLOWED_AUDIO_CONTENT_TYPES
    has_allowed_extension = filename.endswith(ALLOWED_AUDIO_EXTENSIONS)
    if not (has_allowed_type or has_allowed_extension):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=t("errors.asr_invalid_audio_type"),
        )


async def _read_upload_limited(file: UploadFile, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=t("errors.asr_audio_too_large"),
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(
    file: Optional[UploadFile] = File(None),
    payload: Optional[TranscribeBase64Request] = None,
    current_user: User = Depends(require_reader),
):
    """
    Transcribe audio file (WebM / OGG / WAV / MP3) into Uyghur text (UEY & ULY).
    Accepts either multipart file upload or JSON payload with base64 audio.
    """
    audio_bytes: bytes = b""
    max_bytes = settings.asr_max_upload_bytes

    if file is not None:
        _validate_upload_content_type(file)
        try:
            audio_bytes = await _read_upload_limited(file, max_bytes)
        except HTTPException:
            raise
        except Exception as e:
            log_json(logger, logging.ERROR, "Failed to read audio file", error=str(e))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=t("errors.asr_read_failed"),
            )
    elif payload is not None and payload.audioBase64:
        b64_data = payload.audioBase64
        if "," in b64_data:
            _, b64_data = b64_data.split(",", 1)
        # base64 expands raw bytes by ~4/3 — bound the encoded length before decoding
        if len(b64_data) > (max_bytes * 4 // 3) + 1024:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=t("errors.asr_audio_too_large"),
            )
        try:
            audio_bytes = base64.b64decode(b64_data)
        except Exception as e:
            log_json(
                logger, logging.ERROR, "Failed to decode base64 audio", error=str(e)
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=t("errors.asr_invalid_base64"),
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=t("errors.asr_missing_audio"),
        )

    if not audio_bytes or len(audio_bytes) < 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=t("errors.asr_audio_empty"),
        )

    if len(audio_bytes) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=t("errors.asr_audio_too_large"),
        )

    try:
        asr_service = UyghurASRService()
        result = await asyncio.to_thread(asr_service.transcribe, audio_bytes)
        log_json(
            logger,
            logging.INFO,
            "ASR transcribe success",
            user_id=current_user.id,
            audio_bytes=len(audio_bytes),
            text_uey=result.get("text_uey"),
            text_uly=result.get("text_uly"),
        )
        return result

    except RuntimeError as rerr:
        log_json(logger, logging.ERROR, "ASR runtime error", error=str(rerr))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=t("errors.asr_service_unavailable"),
        )
    except Exception as exc:
        log_json(logger, logging.ERROR, "ASR transcription failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=t("errors.asr_transcription_failed"),
        )
