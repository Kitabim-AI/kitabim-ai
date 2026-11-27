"""TTS API endpoints — strictly scoped to Q&A answers in Global and Reader chat."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.i18n import t
from app.db.session import get_session
from app.models.user import User
from app.services.tts_limit_service import tts_limit_service
from app.services.tts_service import (
    TtsConfigError,
    TtsDisabledError,
    TtsEmptyTextError,
    TtsNotFoundError,
    TtsQuotaExceededError,
    tts_service,
)
from app.utils.circuit_breaker import CircuitBreakerOpen
from app.utils.observability import log_json
from auth.dependencies import require_admin, require_reader

router = APIRouter()
logger = logging.getLogger("app.tts.router")


class AnswerTtsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    message_id: Optional[str] = Field(default=None, alias="messageId")
    eval_id: Optional[int] = Field(default=None, alias="evalId")

    @model_validator(mode="after")
    def _require_identifier(self) -> "AnswerTtsRequest":
        if not self.message_id and self.eval_id is None:
            raise ValueError("Either messageId or evalId must be provided")
        return self


class TtsUsageResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    usage: int
    limit: Optional[int] = None
    has_reached_limit: bool = Field(alias="hasReachedLimit")


@router.get("/usage", response_model=TtsUsageResponse)
async def get_tts_usage(
    current_user: User = Depends(require_reader),
    session: AsyncSession = Depends(get_session),
):
    """Get current user's daily uncached TTS usage and limit status."""
    status = await tts_limit_service.get_user_usage_status(current_user, session)
    return TtsUsageResponse(**status)


@router.post("/answer")
async def synthesize_answer_tts(
    req: AnswerTtsRequest,
    current_user: User = Depends(require_reader),
    session: AsyncSession = Depends(get_session),
):
    """Synthesize or serve cached TTS audio for a Global/Reader chat Q&A answer.

    - Cache hit: returns 200 `audio/mpeg` (64 kbps MP3), free & unlimited.
    - Cache miss: streams 200 `audio/pcm` (24 kHz, 16-bit signed LE mono) while
      transcoding and caching MP3 in the background.
    """
    log_json(
        logger,
        logging.INFO,
        "Answer TTS requested",
        user_id=current_user.id,
        message_id=req.message_id,
        eval_id=req.eval_id,
    )

    try:
        prepared = await tts_service.prepare_answer_tts(
            user=current_user,
            session=session,
            message_id=req.message_id,
            eval_id=req.eval_id,
        )
    except TtsDisabledError:
        raise HTTPException(status_code=503, detail=t("errors.tts.disabled"))
    except TtsConfigError as exc:
        log_json(logger, logging.ERROR, "TTS misconfiguration", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
    except TtsNotFoundError:
        raise HTTPException(status_code=404, detail=t("errors.tts.answer_not_found"))
    except TtsEmptyTextError:
        raise HTTPException(status_code=422, detail=t("errors.tts.empty_text"))
    except TtsQuotaExceededError:
        raise HTTPException(status_code=429, detail=t("errors.tts.daily_limit_reached"))
    except CircuitBreakerOpen:
        raise HTTPException(status_code=503, detail=t("errors.system_busy"))
    except Exception as exc:
        log_json(logger, logging.ERROR, "TTS preparation failed", error=str(exc))
        raise HTTPException(status_code=500, detail=t("errors.tts.synthesis_failed"))

    base_headers = {
        "X-TTS-Content-Hash": prepared.content_hash,
        "X-TTS-Truncated": "true" if prepared.truncated else "false",
    }

    if prepared.kind == "cached_mp3":
        headers = {
            **base_headers,
            "X-TTS-Cache": "hit",
            "X-TTS-Cost-Usd": f"{prepared.cost_usd:.6f}",
            "X-TTS-Input-Tokens": str(prepared.input_tokens),
            "X-TTS-Output-Tokens": str(prepared.output_tokens),
            "Cache-Control": "private, max-age=86400",
        }
        if prepared.duration_sec is not None:
            headers["X-TTS-Duration-Sec"] = str(prepared.duration_sec)
        return Response(
            content=prepared.audio_bytes or b"",
            media_type="audio/mpeg",
            headers=headers,
        )

    assert prepared.pcm_stream is not None
    headers = {
        **base_headers,
        "X-TTS-Cache": "miss",
        "X-TTS-Sample-Rate": str(prepared.sample_rate),
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(
        prepared.pcm_stream,
        media_type=f"audio/pcm; rate={prepared.sample_rate}; channels=1; encoding=s16le",
        headers=headers,
    )


@router.get("/cache/{content_hash}/cost")
async def get_tts_cache_cost(
    content_hash: str,
    current_user: User = Depends(require_reader),
    session: AsyncSession = Depends(get_session),
):
    """Fetch persisted TTS token & USD generation cost for a synthesized content hash."""
    if len(content_hash) != 64 or not all(
        c in "0123456789abcdef" for c in content_hash
    ):
        raise HTTPException(status_code=400, detail="Invalid content hash")

    cost_info = await tts_service.get_cached_cost(content_hash, session)
    if cost_info is None:
        return {
            "ready": False,
            "inputTokens": 0,
            "outputTokens": 0,
            "costUsd": 0.0,
            "durationSec": None,
        }
    return cost_info


@router.get("/admin/eval/{eval_id}/audio")
async def get_admin_cached_eval_audio(
    eval_id: int,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Admin-only, strictly cache-only MP3 playback for reviewing answers ($0 cost).

    Never triggers Gemini TTS synthesis. Returns 404 if no cached audio exists.
    """
    try:
        prepared = await tts_service.get_cached_audio_for_eval_admin(eval_id, session)
    except TtsNotFoundError:
        raise HTTPException(status_code=404, detail=t("errors.tts.answer_not_found"))

    headers = {
        "X-TTS-Cache": "hit",
        "X-TTS-Content-Hash": prepared.content_hash,
        "X-TTS-Truncated": "true" if prepared.truncated else "false",
        "X-TTS-Cost-Usd": f"{prepared.cost_usd:.6f}",
        "X-TTS-Input-Tokens": str(prepared.input_tokens),
        "X-TTS-Output-Tokens": str(prepared.output_tokens),
        "Cache-Control": "private, max-age=86400",
    }
    if prepared.duration_sec is not None:
        headers["X-TTS-Duration-Sec"] = str(prepared.duration_sec)
    return Response(
        content=prepared.audio_bytes or b"",
        media_type="audio/mpeg",
        headers=headers,
    )
