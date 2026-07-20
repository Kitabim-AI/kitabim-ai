"""Verify that _execute_and_record_tool only catches recoverable tool errors.

ADK 2.x uses framework signals (e.g. NodeInterruptedError) that must propagate
freely. The old broad `except Exception` would trap those. These tests ensure
only known DB/network errors are caught and recorded as ok=False, while all
other exceptions propagate.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


class _FakeToolContext:
    """Minimal stand-in for ADK ToolContext."""

    def __init__(self):
        self.state = {"query_context": MagicMock(), "observations": []}


@pytest.mark.asyncio
async def test_execute_and_record_tool_reraises_keyboard_interrupt():
    """KeyboardInterrupt must not be swallowed — it's a BaseException."""
    from app.services.rag.agent.tools import _execute_and_record_tool

    async def _raise_ki(*args, **kwargs):
        raise KeyboardInterrupt("stop")

    with patch(
        "app.services.rag.agent.tools._dispatch_tool_with_retry",
        new=_raise_ki,
    ):
        ctx = _FakeToolContext()
        with pytest.raises(KeyboardInterrupt):
            await _execute_and_record_tool(ctx, "search_chunks", {"query": "test"})


@pytest.mark.asyncio
async def test_execute_and_record_tool_reraises_system_exit():
    """SystemExit must propagate — it's a BaseException."""
    from app.services.rag.agent.tools import _execute_and_record_tool

    async def _raise_se(*args, **kwargs):
        raise SystemExit(1)

    with patch(
        "app.services.rag.agent.tools._dispatch_tool_with_retry",
        new=_raise_se,
    ):
        ctx = _FakeToolContext()
        with pytest.raises(SystemExit):
            await _execute_and_record_tool(ctx, "search_chunks", {"query": "test"})


@pytest.mark.asyncio
async def test_execute_and_record_tool_records_db_error():
    """SQLAlchemy DBAPIError is a recoverable tool error — catch and record as ok=False."""
    from sqlalchemy.exc import DBAPIError
    from app.services.rag.agent.tools import _execute_and_record_tool

    async def _raise_db(*args, **kwargs):
        raise DBAPIError("stmt", "params", Exception("conn refused"))

    with patch(
        "app.services.rag.agent.tools._dispatch_tool_with_retry",
        new=_raise_db,
    ):
        ctx = _FakeToolContext()
        result = await _execute_and_record_tool(ctx, "search_chunks", {"query": "test"})
        assert result["ok"] is False
        assert "error" in result
        # The failed obs should be recorded in state
        assert len(ctx.state["observations"]) == 1
        assert ctx.state["observations"][0]["result"]["ok"] is False


@pytest.mark.asyncio
async def test_execute_and_record_tool_records_httpx_error():
    """httpx.HTTPError is recoverable — catch and record as ok=False."""
    import httpx
    from app.services.rag.agent.tools import _execute_and_record_tool

    async def _raise_http(*args, **kwargs):
        raise httpx.ReadTimeout("timeout", request=MagicMock())

    with patch(
        "app.services.rag.agent.tools._dispatch_tool_with_retry",
        new=_raise_http,
    ):
        ctx = _FakeToolContext()
        result = await _execute_and_record_tool(ctx, "search_chunks", {"query": "test"})
        assert result["ok"] is False


@pytest.mark.asyncio
async def test_execute_and_record_tool_records_success():
    """Successful tool calls are appended to observations with the result."""
    from app.services.rag.agent.tools import _execute_and_record_tool

    async def _success(*args, **kwargs):
        return {"ok": True, "data": {"chunks": []}}

    with patch(
        "app.services.rag.agent.tools._dispatch_tool_with_retry",
        new=_success,
    ):
        ctx = _FakeToolContext()
        result = await _execute_and_record_tool(
            ctx, "search_chunks", {"query": "hello"}
        )
        assert result["ok"] is True
        assert len(ctx.state["observations"]) == 1
        assert ctx.state["observations"][0]["tool"] == "search_chunks"
        assert ctx.state["observations"][0]["result"]["ok"] is True
