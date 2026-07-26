import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock, patch

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


class FakeUploadFile:
    def __init__(
        self,
        data: bytes,
        content_type: str = "audio/webm",
        filename: str = "voice.webm",
    ):
        self._data = data
        self._pos = 0
        self.content_type = content_type
        self.filename = filename

    async def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            chunk = self._data[self._pos :]
            self._pos = len(self._data)
            return chunk
        chunk = self._data[self._pos : self._pos + size]
        self._pos += len(chunk)
        return chunk


def make_user():
    from app.models.user import User

    user = MagicMock(spec=User)
    user.id = "user-123"
    user.role = "reader"
    return user


@pytest.mark.asyncio
async def test_transcribe_requires_audio_input():
    setup_paths()
    from api.endpoints.asr_router import transcribe_audio

    with pytest.raises(HTTPException) as exc_info:
        await transcribe_audio(file=None, payload=None, current_user=make_user())

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_transcribe_rejects_unsupported_content_type():
    setup_paths()
    from api.endpoints.asr_router import transcribe_audio

    fake_file = FakeUploadFile(
        b"x" * 1000, content_type="text/plain", filename="notes.txt"
    )

    with pytest.raises(HTTPException) as exc_info:
        await transcribe_audio(file=fake_file, payload=None, current_user=make_user())

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_transcribe_rejects_empty_audio():
    setup_paths()
    from api.endpoints.asr_router import transcribe_audio

    fake_file = FakeUploadFile(b"", content_type="audio/webm")

    with pytest.raises(HTTPException) as exc_info:
        await transcribe_audio(file=fake_file, payload=None, current_user=make_user())

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_transcribe_rejects_oversized_base64_payload():
    setup_paths()
    from api.endpoints.asr_router import transcribe_audio, TranscribeBase64Request

    with patch("api.endpoints.asr_router.settings") as mock_settings:
        mock_settings.asr_max_upload_bytes = 100
        oversized_b64 = "A" * 1000
        payload = TranscribeBase64Request(audioBase64=oversized_b64)

        with pytest.raises(HTTPException) as exc_info:
            await transcribe_audio(file=None, payload=payload, current_user=make_user())

    assert exc_info.value.status_code == 413


@pytest.mark.asyncio
async def test_transcribe_rejects_oversized_file_upload():
    setup_paths()
    from api.endpoints.asr_router import transcribe_audio

    with patch("api.endpoints.asr_router.settings") as mock_settings:
        mock_settings.asr_max_upload_bytes = 100
        fake_file = FakeUploadFile(b"x" * 1000, content_type="audio/webm")

        with pytest.raises(HTTPException) as exc_info:
            await transcribe_audio(
                file=fake_file, payload=None, current_user=make_user()
            )

    assert exc_info.value.status_code == 413


@pytest.mark.asyncio
async def test_transcribe_success_returns_service_result():
    setup_paths()
    from api.endpoints.asr_router import transcribe_audio

    fake_file = FakeUploadFile(b"x" * 1000, content_type="audio/webm")
    mock_service = MagicMock()
    mock_service.transcribe.return_value = {
        "text_uey": "سالام",
        "text_uly": "salam",
        "raw_pred": "salam",
    }

    with patch("api.endpoints.asr_router.UyghurASRService", return_value=mock_service):
        result = await transcribe_audio(
            file=fake_file, payload=None, current_user=make_user()
        )

    assert result["text_uly"] == "salam"
    mock_service.transcribe.assert_called_once()


@pytest.mark.asyncio
async def test_transcribe_service_runtime_error_returns_503():
    setup_paths()
    from api.endpoints.asr_router import transcribe_audio

    fake_file = FakeUploadFile(b"x" * 1000, content_type="audio/webm")
    mock_service = MagicMock()
    mock_service.transcribe.side_effect = RuntimeError("model unavailable")

    with patch("api.endpoints.asr_router.UyghurASRService", return_value=mock_service):
        with pytest.raises(HTTPException) as exc_info:
            await transcribe_audio(
                file=fake_file, payload=None, current_user=make_user()
            )

    assert exc_info.value.status_code == 503
