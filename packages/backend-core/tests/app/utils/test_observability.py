import pytest
import logging
import json
from unittest.mock import MagicMock, patch
from app.utils.observability import JsonFormatter, log_json, configure_logging, request_id_var

def test_json_formatter():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="test message",
        args=(),
        exc_info=None
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
        exc_info=None
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
            exc_info=sys.exc_info()
        )
        formatted = formatter.format(record)
        data = json.loads(formatted)
        assert "exception" in data
        assert "ValueError: error" in data["exception"]

def test_log_json():
    mock_logger = MagicMock()
    log_json(mock_logger, logging.INFO, "msg", key="value")
    mock_logger.log.assert_called_with(logging.INFO, "msg", extra={"fields": {"key": "value"}})

def test_configure_logging():
    with patch("logging.StreamHandler") as mock_handler:
        with patch("logging.getLogger") as mock_get_logger:
            configure_logging(logging.DEBUG)
            assert mock_get_logger.called
