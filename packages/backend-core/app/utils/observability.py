from __future__ import annotations

import contextvars
import functools
import inspect
import json
import logging
from datetime import datetime, UTC
from typing import Any, Dict

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)


def track_request_id(func):
    """Decorator to wrap a worker job or function, extracting the request_id from keyword arguments
    and setting the request_id_var context variable during its execution.
    """

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        request_id = kwargs.pop("request_id", None)
        token = None
        if request_id:
            token = request_id_var.set(request_id)
        try:
            sig = inspect.signature(func)
            if "request_id" in sig.parameters:
                kwargs["request_id"] = request_id
            return await func(*args, **kwargs)
        finally:
            if token:
                request_id_var.reset(token)

    return wrapper


def patch_arq_enqueue_job() -> None:
    """Monkey-patch arq.connections.ArqRedis.enqueue_job to inject request_id_var into kwargs."""
    try:
        from arq.connections import ArqRedis
    except ImportError:
        return

    if getattr(ArqRedis, "_is_patched_for_request_id", False):
        return

    original_enqueue_job = ArqRedis.enqueue_job

    async def custom_enqueue_job(
        self,
        function: str,
        *args,
        _job_id=None,
        _queue_name=None,
        _defer_until=None,
        _defer_by=None,
        _expires=None,
        _job_try=None,
        **kwargs,
    ):
        req_id = request_id_var.get()
        if req_id and "request_id" not in kwargs:
            kwargs["request_id"] = req_id
        return await original_enqueue_job(
            self,
            function,
            *args,
            _job_id=_job_id,
            _queue_name=_queue_name,
            _defer_until=_defer_until,
            _defer_by=_defer_by,
            _expires=_expires,
            _job_try=_job_try,
            **kwargs,
        )

    ArqRedis.enqueue_job = custom_enqueue_job
    ArqRedis._is_patched_for_request_id = True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
        }

        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update(fields)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]

    # Silence noisy loggers - keep only warnings and errors
    for name in (
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "google_genai",
        "arq.worker",
        "arq.jobs",
    ):
        logging.getLogger(name).handlers = [handler]
        logging.getLogger(name).propagate = False
        logging.getLogger(name).setLevel(logging.WARNING)

    # Apply request ID queue patching
    patch_arq_enqueue_job()


def log_json(logger: logging.Logger, level: int, message: str, **fields: Any) -> None:
    logger.log(level, message, extra={"fields": fields})


def make_pipeline_event_payload(
    duration_ms: int | None = None, extra_fields: Dict[str, Any] | None = None
) -> str:
    """Helper to construct a standardized JSON string payload for PipelineEvents,
    injecting request_id and duration_ms when available.
    """
    payload: Dict[str, Any] = {}
    req_id = request_id_var.get()
    if req_id is not None:
        payload["request_id"] = req_id
    if duration_ms is not None:
        payload["duration_ms"] = duration_ms
    if extra_fields:
        payload.update(extra_fields)
    return json.dumps(payload, ensure_ascii=False)
