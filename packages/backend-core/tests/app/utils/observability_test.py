import logging
import json
from unittest.mock import MagicMock, patch
from app.utils.observability import (
    JsonFormatter,
    log_json,
    configure_logging,
    request_id_var,
)


def test_json_formatter():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="test message",
        args=(),
        exc_info=None,
    )
    request_id_var.set("req-123")

    formatted = formatter.format(record)
    data = json.loads(formatted)

    assert data["message"] == "test message"
    assert data["logger"] == "test_logger"
    assert data["request_id"] == "req-123"
    assert "ts" in data


def test_json_formatter_with_fields():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="test message",
        args=(),
        exc_info=None,
    )
    record.fields = {"key": "value"}

    formatted = formatter.format(record)
    data = json.loads(formatted)
    assert data["key"] == "value"


def test_json_formatter_with_exception():
    formatter = JsonFormatter()
    try:
        raise ValueError("error")
    except ValueError:
        import sys

        record = logging.LogRecord(
            name="test_logger",
            level=logging.ERROR,
            pathname="test.py",
            lineno=10,
            msg="test error",
            args=(),
            exc_info=sys.exc_info(),
        )
        formatted = formatter.format(record)
        data = json.loads(formatted)
        assert "exception" in data
        assert "ValueError: error" in data["exception"]


def test_log_json():
    mock_logger = MagicMock()
    log_json(mock_logger, logging.INFO, "msg", key="value")
    mock_logger.log.assert_called_with(
        logging.INFO, "msg", extra={"fields": {"key": "value"}}
    )


def test_configure_logging():
    with patch("logging.StreamHandler"):
        with patch("logging.getLogger") as mock_get_logger:
            configure_logging(logging.DEBUG)
            assert mock_get_logger.called


import pytest


@pytest.mark.asyncio
async def test_track_request_id():
    from app.utils.observability import track_request_id

    # Reset any request ID from previous tests
    request_id_var.set(None)

    @track_request_id
    async def sample_job(ctx, some_val, **kwargs):
        assert request_id_var.get() == "job-req-id"
        return some_val

    # Test that setting request_id inside kwargs populates request_id_var
    res = await sample_job(None, 42, request_id="job-req-id")
    assert res == 42
    # Verify request_id_var is reset afterward
    assert request_id_var.get() is None


@pytest.mark.asyncio
async def test_patch_arq_enqueue_job():
    from arq.connections import ArqRedis
    from app.utils.observability import patch_arq_enqueue_job
    from unittest.mock import AsyncMock

    # Reset any request ID from previous tests
    request_id_var.set("client-req-id")

    patch_arq_enqueue_job()
    assert getattr(ArqRedis, "_is_patched_for_request_id", False)

    # Setup mocked Redis client that enqueue_job expects
    mock_redis = MagicMock()
    mock_redis.default_queue_name = "arq:queue"
    mock_redis.expires_extra_ms = 86400000
    mock_redis.job_serializer = None
    mock_redis.job_deserializer = None

    mock_pipeline = AsyncMock()
    mock_pipeline.exists.return_value = False

    mock_context_manager = MagicMock()
    mock_context_manager.__aenter__ = AsyncMock(return_value=mock_pipeline)
    mock_context_manager.__aexit__ = AsyncMock(return_value=False)

    mock_redis.pipeline.return_value = mock_context_manager

    try:
        with patch("arq.connections.serialize_job") as mock_serialize:
            mock_serialize.return_value = b"serialized-job"
            # Call enqueue_job as a class method passing mock_redis as self
            await ArqRedis.enqueue_job(mock_redis, "test_job", 1, val="abc")

            # Verify serialize_job was called with injected request_id in kwargs
            mock_serialize.assert_called_once()
            args_passed = mock_serialize.call_args[0]
            # serialize_job signature: serialize_job(function, args, kwargs, ...)
            kwargs_passed = args_passed[2]
            assert kwargs_passed["request_id"] == "client-req-id"
            assert kwargs_passed["val"] == "abc"
    finally:
        request_id_var.set(None)
