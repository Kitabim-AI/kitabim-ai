import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.llm.models import GeminiEmbeddings


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
    with patch("app.llm.models._TEXT_LIMITER.wait", new_callable=AsyncMock), patch(
        "app.llm.models._TEXT_BREAKER.call"
    ) as mock_breaker_call:
        # Mock the breaker call to just run the function and raise the error
        async def side_effect(fn, *args, ignore_on_failure=None, **kwargs):
            return await fn(*args, **kwargs)

        mock_breaker_call.side_effect = side_effect

        # 1. Test transient error (504 DEADLINE_EXCEEDED) logs as WARNING
        async def raise_504():
            raise ValueError("504 DEADLINE_EXCEEDED")

        caplog.clear()
        with pytest.raises(ValueError, match="504"):
            await _call_with_breaker(_TEXT_BREAKER, raise_504)

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
