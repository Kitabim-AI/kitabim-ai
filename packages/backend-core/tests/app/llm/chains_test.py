import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pydantic import BaseModel


class DummySchema(BaseModel):
    name: str


@pytest.mark.asyncio
@patch("app.llm.chains._get_text_client")
@patch("app.llm.models._TEXT_BREAKER.call")
@patch("app.llm.models._TEXT_LIMITER.wait", new_callable=AsyncMock)
async def test_structured_chain_timeout_propagation(
    mock_limiter_wait, mock_breaker_call, mock_get_client
):
    async def side_effect(fn, *args, ignore_on_failure=None, **kwargs):
        return await fn(*args, **kwargs)

    mock_breaker_call.side_effect = side_effect

    mock_client = MagicMock()
    mock_generate_content = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.text = '{"name": "test"}'
    mock_generate_content.return_value = mock_resp
    mock_client.aio.models.generate_content = mock_generate_content
    mock_get_client.return_value = mock_client

    from app.llm.chains import StructuredChain

    chain = StructuredChain(
        template="Tell me about {topic}",
        model_name="gemini-2.0-flash",
        response_schema=DummySchema,
    )

    result = await chain.ainvoke({"topic": "AI"}, timeout=75.0)

    assert isinstance(result, DummySchema)
    assert result.name == "test"
    mock_generate_content.assert_called_once()
    kwargs = mock_generate_content.call_args.kwargs
    assert "config" in kwargs
    config = kwargs["config"]
    assert config.http_options.timeout == 75000
