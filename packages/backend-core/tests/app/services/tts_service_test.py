from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.user import User, UserRole
from app.services.tts_service import (
    TtsConfigError,
    TtsDisabledError,
    TtsNotFoundError,
    TtsQuotaExceededError,
    TtsService,
    compute_tts_content_hash,
)


def _make_user(user_id: str = "user-1", role: UserRole = UserRole.READER) -> User:
    now = datetime.now(timezone.utc)
    return User(
        id=user_id,
        email="reader@example.com",
        display_name="Reader",
        provider="google",
        provider_id="google-123",
        role=role,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def test_compute_tts_content_hash_changes_on_model_voice_or_style():
    h1 = compute_tts_content_hash(
        spoken_text="سالام",
        model="gemini-3.8-flash-tts",
        voice="Sadaltager",
        style="calm",
    )
    h2 = compute_tts_content_hash(
        spoken_text="سالام",
        model="gemini-4-flash-tts",
        voice="Sadaltager",
        style="calm",
    )
    h3 = compute_tts_content_hash(
        spoken_text="سالام",
        model="gemini-3.8-flash-tts",
        voice="Sulafat",
        style="calm",
    )
    assert h1 != h2
    assert h1 != h3
    assert len(h1) == 64


@pytest.mark.asyncio
async def test_get_runtime_config_raises_when_disabled():
    svc = TtsService()
    mock_session = AsyncMock()
    mock_repo = AsyncMock()
    mock_repo.get_value = AsyncMock(
        side_effect=lambda key, default=None: "false"
        if key == "tts_enabled"
        else default
    )

    with patch(
        "app.services.tts_service.SystemConfigsRepository", return_value=mock_repo
    ):
        with pytest.raises(TtsDisabledError):
            await svc.get_runtime_config(mock_session)


@pytest.mark.asyncio
async def test_get_runtime_config_raises_when_model_missing():
    svc = TtsService()
    mock_session = AsyncMock()

    async def fake_get_value(key, default=None):
        if key == "tts_enabled":
            return "true"
        if key == "tts_gemini_model":
            return None
        return default

    mock_repo = AsyncMock()
    mock_repo.get_value = AsyncMock(side_effect=fake_get_value)

    with patch(
        "app.services.tts_service.SystemConfigsRepository", return_value=mock_repo
    ):
        with pytest.raises(TtsConfigError, match="tts_gemini_model"):
            await svc.get_runtime_config(mock_session)


@pytest.mark.asyncio
async def test_resolve_answer_text_rejects_unowned_or_missing_message():
    svc = TtsService()
    user = _make_user("user-1")
    mock_session = AsyncMock()
    exec_result = MagicMock()
    exec_result.first.return_value = None
    mock_session.execute = AsyncMock(return_value=exec_result)

    with pytest.raises(TtsNotFoundError):
        await svc.resolve_answer_text(
            user=user, session=mock_session, message_id="msg-other-user"
        )


@pytest.mark.asyncio
async def test_prepare_answer_tts_returns_cached_mp3_without_checking_quota():
    svc = TtsService()
    user = _make_user("user-1")
    mock_session = AsyncMock()

    async def fake_get_value(key, default=None):
        vals = {
            "tts_enabled": "true",
            "tts_gemini_model": "gemini-3.8-flash-tts",
            "tts_default_voice": "Sadaltager",
            "tts_default_style": "calm",
            "tts_gemini_timeout": "90",
            "tts_max_chars": "5000",
        }
        return vals.get(key, default)

    mock_cfg_repo = AsyncMock()
    mock_cfg_repo.get_value = AsyncMock(side_effect=fake_get_value)

    cache_entry = SimpleNamespace(
        storage_path="tts/answers/ab/abcd.mp3",
        duration_sec=12.5,
        input_tokens=110,
        output_tokens=312,
        cost_usd=0.002863,
    )
    mock_cache_repo = AsyncMock()
    mock_cache_repo.get_by_hash = AsyncMock(return_value=cache_entry)
    mock_cache_repo.touch_hit = AsyncMock()

    mock_storage = MagicMock()
    mock_storage.exists.return_value = True
    mock_storage.read_bytes = AsyncMock(return_value=b"ID3-fake-mp3")

    mock_limit = AsyncMock()

    with (
        patch.object(
            svc, "resolve_answer_text", AsyncMock(return_value="بۇ بىر جاۋاب.")
        ),
        patch(
            "app.services.tts_service.SystemConfigsRepository",
            return_value=mock_cfg_repo,
        ),
        patch(
            "app.services.tts_service.TtsCacheRepository", return_value=mock_cache_repo
        ),
        patch("app.services.tts_service.storage", mock_storage),
        patch("app.services.tts_service.tts_limit_service", mock_limit),
        patch("app.services.tts_service.settings") as mock_settings,
    ):
        mock_settings.gemini_api_key = "test-key"
        res = await svc.prepare_answer_tts(
            user=user, session=mock_session, message_id="msg-1"
        )

    assert res.kind == "cached_mp3"
    assert res.audio_bytes == b"ID3-fake-mp3"
    assert res.duration_sec == 12.5
    assert res.input_tokens == 110
    assert res.output_tokens == 312
    assert res.cost_usd == 0.002863
    mock_limit.get_user_usage_status.assert_not_awaited()
    mock_cache_repo.touch_hit.assert_awaited_once()


@pytest.mark.asyncio
async def test_prepare_answer_tts_cache_miss_enforces_quota():
    svc = TtsService()
    user = _make_user("user-1")
    mock_session = AsyncMock()

    async def fake_get_value(key, default=None):
        vals = {
            "tts_enabled": "true",
            "tts_gemini_model": "gemini-3.8-flash-tts",
            "tts_default_voice": "Sadaltager",
            "tts_default_style": "calm",
            "tts_gemini_timeout": "90",
            "tts_max_chars": "5000",
        }
        return vals.get(key, default)

    mock_cfg_repo = AsyncMock()
    mock_cfg_repo.get_value = AsyncMock(side_effect=fake_get_value)
    mock_cache_repo = AsyncMock()
    mock_cache_repo.get_by_hash = AsyncMock(return_value=None)

    mock_limit = AsyncMock()
    mock_limit.get_user_usage_status = AsyncMock(
        return_value={"usage": 15, "limit": 15, "has_reached_limit": True}
    )

    with (
        patch.object(
            svc, "resolve_answer_text", AsyncMock(return_value="بۇ بىر جاۋاب.")
        ),
        patch(
            "app.services.tts_service.SystemConfigsRepository",
            return_value=mock_cfg_repo,
        ),
        patch(
            "app.services.tts_service.TtsCacheRepository", return_value=mock_cache_repo
        ),
        patch(
            "app.services.tts_service.cache_service.get_client",
            AsyncMock(return_value=None),
        ),
        patch("app.services.tts_service.tts_limit_service", mock_limit),
        patch("app.services.tts_service.settings") as mock_settings,
    ):
        mock_settings.gemini_api_key = "test-key"
        with pytest.raises(TtsQuotaExceededError):
            await svc.prepare_answer_tts(
                user=user, session=mock_session, message_id="msg-1"
            )


@pytest.mark.asyncio
async def test_get_cached_audio_for_eval_admin_raises_404_when_uncached():
    svc = TtsService()
    mock_session = AsyncMock()
    mock_session.get = AsyncMock(
        return_value=SimpleNamespace(id=77, answer="بۇ بىر جاۋاب.")
    )

    mock_cfg_repo = AsyncMock()
    mock_cfg_repo.get_value = AsyncMock(
        side_effect=lambda key, default=None: "gemini-3.8-flash-tts"
        if key == "tts_gemini_model"
        else default
    )
    mock_cache_repo = AsyncMock()
    mock_cache_repo.get_by_hash = AsyncMock(return_value=None)

    with (
        patch(
            "app.services.tts_service.SystemConfigsRepository",
            return_value=mock_cfg_repo,
        ),
        patch(
            "app.services.tts_service.TtsCacheRepository", return_value=mock_cache_repo
        ),
    ):
        with pytest.raises(TtsNotFoundError):
            await svc.get_cached_audio_for_eval_admin(77, mock_session)
