import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.llm.models import GeminiEmbeddings, disabled_thinking_config


@pytest.mark.parametrize(
    "model_name,expected",
    [
        ("gemini-2.0-flash", {"thinking_budget": 0}),
        ("gemini-2.5-flash", {"thinking_budget": 0}),
        ("gemini-3.6-flash", {"thinking_level": "MINIMAL"}),
        ("models/gemini-3.0-pro", {"thinking_level": "MINIMAL"}),
        ("gemini-embedding-2", {"thinking_budget": 0}),
    ],
)
def test_disabled_thinking_config(model_name, expected):
    assert disabled_thinking_config(model_name) == expected


def test_gemini_embeddings_init():
    # Test initialization without prefix
    ge1 = GeminiEmbeddings("gemini-embedding-2")
    assert ge1.model_name == "gemini-embedding-2"

    # Test initialization with models/ prefix
    ge2 = GeminiEmbeddings("models/gemini-embedding-2")
    assert ge2.model_name == "gemini-embedding-2"

    with pytest.raises(ValueError):
        GeminiEmbeddings(None)


@pytest.mark.asyncio
@patch("app.llm.models._EMBED_BREAKER.call")
async def test_gemini_embeddings_aembed_query(mock_breaker_call):
    # Mock circuit breaker to just run the function
    async def side_effect(fn, *args, ignore_on_failure=None, **kwargs):
        return await fn(*args, **kwargs)

    mock_breaker_call.side_effect = side_effect

    # Mock response
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(return_value={"embedding": {"values": [0.1, 0.2, 0.3]}})

    # Mock response context manager
    mock_resp_cm = MagicMock()
    mock_resp_cm.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp_cm.__aexit__ = AsyncMock()

    # Mock session
    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_resp_cm)

    # Mock session context manager
    mock_session_cm = MagicMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_cm.__aexit__ = AsyncMock()

    with patch("aiohttp.ClientSession", return_value=mock_session_cm):
        ge = GeminiEmbeddings("gemini-embedding-2")
        result = await ge.aembed_query("hello")

        assert result == [0.1, 0.2, 0.3]

        # Verify URL and payload format
        mock_session.post.assert_called_once()
        args, kwargs = mock_session.post.call_args
        url = args[0]
        assert "v1beta/models/gemini-embedding-2" in url

        json_payload = kwargs["json"]
        assert json_payload["model"] == "models/gemini-embedding-2"
        assert json_payload["content"]["parts"][0]["text"] == "hello"


@pytest.mark.asyncio
@patch("app.llm.models._EMBED_BREAKER.call")
async def test_gemini_embeddings_aembed_documents(mock_breaker_call):
    async def side_effect(fn, *args, ignore_on_failure=None, **kwargs):
        return await fn(*args, **kwargs)

    mock_breaker_call.side_effect = side_effect

    # Mock response
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(
        return_value={"embeddings": [{"values": [0.1, 0.2]}, {"values": [0.3, 0.4]}]}
    )

    # Mock response context manager
    mock_resp_cm = MagicMock()
    mock_resp_cm.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp_cm.__aexit__ = AsyncMock()

    # Mock session
    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_resp_cm)

    # Mock session context manager
    mock_session_cm = MagicMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_cm.__aexit__ = AsyncMock()

    with patch("aiohttp.ClientSession", return_value=mock_session_cm):
        ge = GeminiEmbeddings("models/gemini-embedding-2")
        result = await ge.aembed_documents(["hello", "world"])

        assert result == [[0.1, 0.2], [0.3, 0.4]]

        mock_session.post.assert_called_once()
        args, kwargs = mock_session.post.call_args
        url = args[0]
        assert "v1beta/models/gemini-embedding-2" in url

        json_payload = kwargs["json"]
        requests = json_payload["requests"]
        assert len(requests) == 2
        assert requests[0]["model"] == "models/gemini-embedding-2"
        assert requests[0]["content"]["parts"][0]["text"] == "hello"
        assert requests[1]["model"] == "models/gemini-embedding-2"
        assert requests[1]["content"]["parts"][0]["text"] == "world"


@pytest.mark.asyncio
async def test_call_with_breaker_transient_vs_non_transient_logging(caplog):
    import logging
    from app.llm.models import _call_with_breaker, _TEXT_BREAKER

    # Mock rate limiters to avoid redis dependency in this test
    with (
        patch("app.llm.models._TEXT_LIMITER.wait", new_callable=AsyncMock),
        patch("app.llm.models._TEXT_BREAKER.call") as mock_breaker_call,
    ):
        # Mock the breaker call to just run the function and raise the error
        async def side_effect(fn, *args, ignore_on_failure=None, **kwargs):
            return await fn(*args, **kwargs)

        mock_breaker_call.side_effect = side_effect

        # 1. Test transient error (429 TOO_MANY_REQUESTS) logs as WARNING
        async def raise_429():
            raise ValueError("429 TOO_MANY_REQUESTS")

        caplog.clear()
        with pytest.raises(ValueError, match="429"):
            await _call_with_breaker(_TEXT_BREAKER, raise_429)

        # Check logs
        transient_logs = [r for r in caplog.records if r.message == "LLM call failed"]
        assert len(transient_logs) == 1
        assert transient_logs[0].levelno == logging.WARNING

        # 2. Test non-transient error logs as ERROR
        async def raise_generic():
            raise ValueError("Generic DB or code error")

        caplog.clear()
        with pytest.raises(ValueError, match="Generic"):
            await _call_with_breaker(_TEXT_BREAKER, raise_generic)

        non_transient_logs = [
            r for r in caplog.records if r.message == "LLM call failed"
        ]
        assert len(non_transient_logs) == 1
        assert non_transient_logs[0].levelno == logging.ERROR


@pytest.mark.asyncio
@patch("app.llm.models._get_text_client")
@patch("app.llm.models._TEXT_BREAKER.call")
@patch("app.llm.models._TEXT_LIMITER.wait", new_callable=AsyncMock)
async def test_protected_llm_timeout_propagation(
    mock_limiter_wait, mock_breaker_call, mock_get_client
):
    # Mock breaker call to just run the function
    async def side_effect(fn, *args, ignore_on_failure=None, **kwargs):
        return await fn(*args, **kwargs)

    mock_breaker_call.side_effect = side_effect

    # Mock client and its async methods
    mock_client = MagicMock()
    mock_generate_content = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.text = "mocked response"
    mock_generate_content.return_value = mock_resp
    mock_client.aio.models.generate_content = mock_generate_content
    mock_get_client.return_value = mock_client

    from app.llm.models import ProtectedLLM, _TEXT_BREAKER

    # Call ainvoke with a timeout
    llm = ProtectedLLM("gemini-2.0-flash", _TEXT_BREAKER)
    result = await llm.ainvoke("hello", timeout=45.0)

    assert result == "mocked response"
    mock_generate_content.assert_called_once()
    kwargs = mock_generate_content.call_args.kwargs
    assert "config" in kwargs
    config = kwargs["config"]
    assert config is not None
    assert config.http_options is not None
    assert config.http_options.timeout == 45000


@pytest.mark.asyncio
@patch("app.llm.models._get_text_client")
@patch("app.llm.models._stream_with_breaker")
async def test_protected_llm_astream_timeout_propagation(
    mock_stream_breaker, mock_get_client
):
    mock_chunk = MagicMock()
    mock_chunk.text = "stream chunk"

    # Mock client and generate_content_stream
    mock_client = MagicMock()
    mock_generate_stream = AsyncMock()

    async def mock_stream_func(*args, **kwargs):
        yield mock_chunk

    mock_generate_stream.return_value = mock_stream_func()
    mock_client.aio.models.generate_content_stream = mock_generate_stream
    mock_get_client.return_value = mock_client

    # Mock _stream_with_breaker to actually call the passed fn (which is _get_stream)
    async def mock_stream_breaker_side_effect(breaker, fn, *args, **kwargs):
        stream = await fn(*args, **kwargs)
        async for chunk in stream:
            yield chunk

    mock_stream_breaker.side_effect = mock_stream_breaker_side_effect

    from app.llm.models import ProtectedLLM, _TEXT_BREAKER

    llm = ProtectedLLM("gemini-2.0-flash", _TEXT_BREAKER)
    chunks = []
    async for chunk in llm.astream("hello", timeout=12.5):
        chunks.append(chunk)

    assert chunks == ["stream chunk"]
    mock_generate_stream.assert_called_once()
    kwargs = mock_generate_stream.call_args.kwargs
    assert "config" in kwargs
    config = kwargs["config"]
    assert config.http_options.timeout == 12500


@pytest.mark.asyncio
@patch("app.llm.models._get_ocr_client")
@patch("app.llm.models._OCR_BREAKER.call")
@patch("app.llm.models._OCR_LIMITER.wait", new_callable=AsyncMock)
async def test_generate_text_with_image_timeout_propagation(
    mock_limiter_wait, mock_breaker_call, mock_get_client
):
    async def side_effect(fn, *args, ignore_on_failure=None, **kwargs):
        return await fn(*args, **kwargs)

    mock_breaker_call.side_effect = side_effect

    mock_client = MagicMock()
    mock_generate_content = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.text = "ocr response"
    mock_generate_content.return_value = mock_resp
    mock_client.aio.models.generate_content = mock_generate_content
    mock_get_client.return_value = mock_client

    from app.llm.models import generate_text_with_image

    result = await generate_text_with_image(
        "prompt", b"image", "gemini-2.0-flash", timeout=150.0
    )

    assert result == "ocr response"
    mock_generate_content.assert_called_once()
    kwargs = mock_generate_content.call_args.kwargs
    assert "config" in kwargs
    config = kwargs["config"]
    assert config.http_options.timeout == 150000
    assert config.system_instruction == "prompt"
    assert "prompt" not in kwargs["contents"]
    assert config.thinking_config.thinking_budget == 0


@pytest.mark.asyncio
@patch("app.llm.models._get_ocr_client")
@patch("app.llm.models._OCR_BREAKER.call")
@patch("app.llm.models._OCR_LIMITER.wait", new_callable=AsyncMock)
async def test_generate_text_with_image_uses_thinking_level_for_v3_model(
    mock_limiter_wait, mock_breaker_call, mock_get_client
):
    async def side_effect(fn, *args, ignore_on_failure=None, **kwargs):
        return await fn(*args, **kwargs)

    mock_breaker_call.side_effect = side_effect

    mock_client = MagicMock()
    mock_generate_content = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.text = "ocr response"
    mock_generate_content.return_value = mock_resp
    mock_client.aio.models.generate_content = mock_generate_content
    mock_get_client.return_value = mock_client

    from app.llm.models import generate_text_with_image

    await generate_text_with_image("prompt", b"image", "gemini-3.6-flash")

    kwargs = mock_generate_content.call_args.kwargs
    config = kwargs["config"]
    assert config.thinking_config.thinking_level.value == "MINIMAL"
    assert config.thinking_config.thinking_budget is None


@pytest.mark.asyncio
@patch("app.llm.models._get_ocr_client")
@patch("app.llm.models._OCR_BREAKER.call")
@patch("app.llm.models._OCR_LIMITER.wait", new_callable=AsyncMock)
@patch("app.llm.models.get_system_config_timeout")
async def test_generate_text_with_image_timeout_fallback(
    mock_get_db_timeout, mock_limiter_wait, mock_breaker_call, mock_get_client
):
    async def side_effect(fn, *args, ignore_on_failure=None, **kwargs):
        return await fn(*args, **kwargs)

    mock_breaker_call.side_effect = side_effect

    mock_get_db_timeout.return_value = 180.0

    mock_client = MagicMock()
    mock_generate_content = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.text = "ocr response"
    mock_generate_content.return_value = mock_resp
    mock_client.aio.models.generate_content = mock_generate_content
    mock_get_client.return_value = mock_client

    from app.llm.models import generate_text_with_image

    result = await generate_text_with_image("prompt", b"image", "gemini-2.0-flash")

    assert result == "ocr response"
    mock_get_db_timeout.assert_called_once_with("ocr_gemini_timeout", 300.0)
    mock_generate_content.assert_called_once()
    kwargs = mock_generate_content.call_args.kwargs
    assert "config" in kwargs
    config = kwargs["config"]
    assert config.http_options.timeout == 180000
    assert config.system_instruction == "prompt"
    assert "prompt" not in kwargs["contents"]


@pytest.mark.asyncio
@patch("app.llm.models._get_text_client")
@patch("app.llm.models._TEXT_BREAKER.call")
@patch("app.llm.models._TEXT_LIMITER.wait", new_callable=AsyncMock)
@patch("app.llm.models.get_system_config_timeout")
async def test_protected_llm_timeout_fallback(
    mock_get_db_timeout, mock_limiter_wait, mock_breaker_call, mock_get_client
):
    async def side_effect(fn, *args, ignore_on_failure=None, **kwargs):
        return await fn(*args, **kwargs)

    mock_breaker_call.side_effect = side_effect

    mock_get_db_timeout.return_value = 45.0

    mock_client = MagicMock()
    mock_generate_content = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.text = "mocked response"
    mock_generate_content.return_value = mock_resp
    mock_client.aio.models.generate_content = mock_generate_content
    mock_get_client.return_value = mock_client

    from app.llm.models import ProtectedLLM, _TEXT_BREAKER

    llm = ProtectedLLM("gemini-2.0-flash", _TEXT_BREAKER)
    result = await llm.ainvoke("hello")

    assert result == "mocked response"
    mock_get_db_timeout.assert_called_once_with("rag_gemini_chat_timeout", 60.0)
    mock_generate_content.assert_called_once()
    kwargs = mock_generate_content.call_args.kwargs
    assert "config" in kwargs
    config = kwargs["config"]
    assert config.http_options.timeout == 45000
