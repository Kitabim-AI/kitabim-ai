import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

BACKEND_DIR = str(Path(__file__).resolve().parents[3])
BACKEND_CORE_DIR = str(
    Path(__file__).resolve().parents[5] / "packages" / "backend-core"
)


def setup_paths():
    for m in list(sys.modules.keys()):
        if m == "api" or m.startswith("api."):
            del sys.modules[m]
    for p in [BACKEND_CORE_DIR, BACKEND_DIR]:
        if p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)


def _make_user():
    from app.models.user import User, UserRole

    now = datetime.now(timezone.utc)
    return User(
        id="user-1",
        email="reader@example.com",
        display_name="Reader",
        provider="google",
        provider_id="google-123",
        role=UserRole.READER,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def test_answer_tts_request_requires_message_or_eval_id():
    setup_paths()
    from api.endpoints.tts_router import AnswerTtsRequest

    with pytest.raises(ValidationError):
        AnswerTtsRequest()

    req = AnswerTtsRequest(messageId="msg-123")
    assert req.message_id == "msg-123"
    assert req.eval_id is None


@pytest.mark.asyncio
async def test_synthesize_answer_tts_returns_503_when_disabled():
    setup_paths()
    from api.endpoints.tts_router import AnswerTtsRequest, synthesize_answer_tts
    from app.services.tts_service import TtsDisabledError

    with patch(
        "api.endpoints.tts_router.tts_service.prepare_answer_tts",
        AsyncMock(side_effect=TtsDisabledError("disabled")),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await synthesize_answer_tts(
                req=AnswerTtsRequest(messageId="msg-1"),
                current_user=_make_user(),
                session=AsyncMock(),
            )
    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_synthesize_answer_tts_returns_429_when_quota_exceeded():
    setup_paths()
    from api.endpoints.tts_router import AnswerTtsRequest, synthesize_answer_tts
    from app.services.tts_service import TtsQuotaExceededError

    with patch(
        "api.endpoints.tts_router.tts_service.prepare_answer_tts",
        AsyncMock(side_effect=TtsQuotaExceededError("limit")),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await synthesize_answer_tts(
                req=AnswerTtsRequest(messageId="msg-1"),
                current_user=_make_user(),
                session=AsyncMock(),
            )
    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_synthesize_answer_tts_returns_cached_mp3():
    setup_paths()
    from api.endpoints.tts_router import AnswerTtsRequest, synthesize_answer_tts
    from app.services.tts_service import TtsPreparedResponse

    prepared = TtsPreparedResponse(
        kind="cached_mp3",
        content_hash="abc123",
        truncated=False,
        duration_sec=14.2,
        audio_bytes=b"ID3-audio",
        input_tokens=110,
        output_tokens=355,
        cost_usd=0.00325,
    )

    with patch(
        "api.endpoints.tts_router.tts_service.prepare_answer_tts",
        AsyncMock(return_value=prepared),
    ):
        resp = await synthesize_answer_tts(
            req=AnswerTtsRequest(messageId="msg-1"),
            current_user=_make_user(),
            session=AsyncMock(),
        )

    assert resp.media_type == "audio/mpeg"
    assert resp.headers["X-TTS-Cache"] == "hit"
    assert resp.headers["X-TTS-Duration-Sec"] == "14.2"
    assert resp.headers["X-TTS-Cost-Usd"] == "0.003250"
    assert resp.headers["X-TTS-Input-Tokens"] == "110"
    assert resp.headers["X-TTS-Output-Tokens"] == "355"
    assert resp.body == b"ID3-audio"


@pytest.mark.asyncio
async def test_get_tts_cache_cost_returns_persisted_metrics():
    setup_paths()
    from api.endpoints.tts_router import get_tts_cache_cost

    valid_hash = "a" * 64
    with patch(
        "api.endpoints.tts_router.tts_service.get_cached_cost",
        AsyncMock(
            return_value={
                "ready": True,
                "inputTokens": 120,
                "outputTokens": 300,
                "costUsd": 0.00276,
                "durationSec": 12.0,
            }
        ),
    ):
        res = await get_tts_cache_cost(
            content_hash=valid_hash,
            current_user=_make_user(),
            session=AsyncMock(),
        )

    assert res["ready"] is True
    assert res["costUsd"] == 0.00276
    assert res["outputTokens"] == 300


def test_extract_message_cost_includes_attached_tts_cost():
    setup_paths()
    from types import SimpleNamespace
    from api.endpoints.chat_router import _extract_message_cost

    msg = SimpleNamespace(
        evaluation=SimpleNamespace(
            input_tokens=1000, output_tokens=200, cost_usd=0.0005
        ),
        agent_steps={
            "tts_cost": {
                "input_tokens": 110,
                "output_tokens": 355,
                "cost_usd": 0.00325,
            }
        },
    )
    cost = _extract_message_cost(msg)
    assert cost == {
        "inputTokens": 1000,
        "outputTokens": 200,
        "costUsd": 0.0005,
        "ttsInputTokens": 110,
        "ttsOutputTokens": 355,
        "ttsCostUsd": 0.00325,
    }


@pytest.mark.asyncio
async def test_synthesize_answer_tts_streams_pcm_on_miss():
    setup_paths()
    from api.endpoints.tts_router import AnswerTtsRequest, synthesize_answer_tts
    from app.services.tts_service import TtsPreparedResponse

    async def fake_pcm():
        yield b"\x01\x02\x03\x04"
        yield b"\x05\x06"

    prepared = TtsPreparedResponse(
        kind="stream_pcm",
        content_hash="def456",
        truncated=False,
        sample_rate=24000,
        pcm_stream=fake_pcm(),
    )

    with patch(
        "api.endpoints.tts_router.tts_service.prepare_answer_tts",
        AsyncMock(return_value=prepared),
    ):
        resp = await synthesize_answer_tts(
            req=AnswerTtsRequest(evalId=42),
            current_user=_make_user(),
            session=AsyncMock(),
        )

    assert resp.media_type.startswith("audio/pcm")
    assert resp.headers["X-TTS-Cache"] == "miss"
    assert resp.headers["X-TTS-Sample-Rate"] == "24000"
    collected = bytearray()
    async for chunk in resp.body_iterator:
        collected.extend(chunk)
    assert bytes(collected) == b"\x01\x02\x03\x04\x05\x06"


@pytest.mark.asyncio
async def test_get_tts_usage_returns_status():
    setup_paths()
    from api.endpoints.tts_router import get_tts_usage

    with patch(
        "api.endpoints.tts_router.tts_limit_service.get_user_usage_status",
        AsyncMock(return_value={"usage": 3, "limit": 15, "has_reached_limit": False}),
    ):
        res = await get_tts_usage(
            current_user=_make_user(),
            session=AsyncMock(),
        )

    assert res.usage == 3
    assert res.limit == 15
    assert res.has_reached_limit is False
