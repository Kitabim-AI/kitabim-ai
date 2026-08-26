from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, AsyncIterator, List, Optional

from google import genai
from google.genai import types

from app.core.config import settings
from app.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpen,
)
from app.utils.observability import log_json
from app.utils.rate_limiter import RedisRateLimiter

_logger = logging.getLogger("app.llm")

# Dedicated rate limiters for different purposes to prevent OCR from starving Chat/Text requests
_TEXT_LIMITER = RedisRateLimiter(
    "gemini_text", limit=settings.gemini_text_rpm, window=60
)
_OCR_LIMITER = RedisRateLimiter("gemini_ocr", limit=settings.gemini_ocr_rpm, window=60)
_EMBED_LIMITER = RedisRateLimiter(
    "gemini_embed", limit=settings.gemini_embed_rpm, window=60
)

_TEXT_BREAKER = CircuitBreaker(
    "llm_generate",
    CircuitBreakerConfig(
        failure_threshold=settings.llm_cb_failure_threshold,
        recovery_timeout=float(settings.llm_cb_recovery_seconds),
        half_open_max_calls=settings.llm_cb_half_open_max_calls,
        cooling_period=float(settings.llm_cb_cooling_period),
    ),
)


_OCR_BREAKER = CircuitBreaker(
    "llm_ocr",
    CircuitBreakerConfig(
        failure_threshold=settings.llm_cb_failure_threshold,
        recovery_timeout=float(settings.llm_cb_recovery_seconds),
        half_open_max_calls=settings.llm_cb_half_open_max_calls,
        cooling_period=float(settings.llm_cb_cooling_period),
    ),
)


_EMBED_BREAKER = CircuitBreaker(
    "llm_embed",
    CircuitBreakerConfig(
        failure_threshold=settings.llm_cb_failure_threshold,
        recovery_timeout=float(settings.llm_cb_recovery_seconds),
        half_open_max_calls=settings.llm_cb_half_open_max_calls,
        cooling_period=float(settings.llm_cb_cooling_period),
    ),
)


async def is_llm_available() -> bool:
    """Check if the LLM circuit breakers are fully available (closed)."""
    text_st = (await _TEXT_BREAKER._get_state()).get("state")
    ocr_st = (await _OCR_BREAKER._get_state()).get("state")
    embed_st = (await _EMBED_BREAKER._get_state()).get("state")
    return text_st == "closed" and ocr_st == "closed" and embed_st == "closed"


def update_breaker_config(
    failure_threshold: int | None = None, recovery_timeout: float | None = None
) -> None:
    """Update defaults for all circuit breakers."""
    for breaker in [_TEXT_BREAKER, _OCR_BREAKER, _EMBED_BREAKER]:
        if failure_threshold is not None:
            breaker.config.failure_threshold = failure_threshold
        if recovery_timeout is not None:
            breaker.config.recovery_timeout = recovery_timeout


async def reset_circuit_breakers(name: Optional[str] = None) -> dict:
    """Manually reset (close) circuit breakers. Admin control."""
    breakers = [_TEXT_BREAKER, _OCR_BREAKER, _EMBED_BREAKER]
    if name:
        breakers = [b for b in breakers if b.name == name]

    for breaker in breakers:
        await breaker.reset()

    return await get_circuit_breaker_status()


async def force_open_circuit_breakers(name: Optional[str] = None) -> dict:
    """Manually open circuit breakers. Admin control."""
    breakers = [_TEXT_BREAKER, _OCR_BREAKER, _EMBED_BREAKER]
    if name:
        breakers = [b for b in breakers if b.name == name]

    for breaker in breakers:
        await breaker.force_open()

    return await get_circuit_breaker_status()


async def get_circuit_breaker_status() -> dict:
    """Get current status of circuit breakers."""
    text_info = await _TEXT_BREAKER.get_info()
    ocr_info = await _OCR_BREAKER.get_info()
    embed_info = await _EMBED_BREAKER.get_info()

    # Determine overall state
    states = [text_info["state"], ocr_info["state"], embed_info["state"]]
    if "open" in states:
        overall_state = "open"
    elif "half_open" in states:
        overall_state = "half_open"
    else:
        overall_state = "closed"

    return {
        "text_breaker": text_info,
        "ocr_breaker": ocr_info,
        "embed_breaker": embed_info,
        "overall_available": overall_state == "closed",
        "overall_state": overall_state,
    }


_text_client: genai.Client | None = None
_ocr_client: genai.Client | None = None


def _get_text_client() -> genai.Client:
    global _text_client
    if _text_client is None:
        _text_client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(timeout=int(_INVOKE_TIMEOUT * 1000)),
        )
    return _text_client


def _get_ocr_client() -> genai.Client:
    global _ocr_client
    if _ocr_client is None:
        _ocr_client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(timeout=int(_OCR_INVOKE_TIMEOUT * 1000)),
        )
    return _ocr_client


def _normalize_prompt_value(value: Any) -> str:
    if hasattr(value, "to_string"):
        try:
            return value.to_string()
        except Exception:
            pass
    return str(value)


_STREAM_FIRST_CHUNK_TIMEOUT = (
    60.0  # seconds to wait for the first chunk before treating as failure
)
_INVOKE_TIMEOUT = 60.0  # seconds to wait for a non-streaming ainvoke to complete
_OCR_INVOKE_TIMEOUT = (
    300.0  # seconds for OCR vision calls (image + prompt, much slower)
)


class DegenerateOcrOutputError(Exception):
    """Raised when an OCR call returns output that looks like a runaway
    repetition/reasoning-leak loop rather than a real page. Treated as
    retryable, same as a transient API error.
    """


def is_transient_error(exc: Exception) -> bool:
    """Check if the exception represents a transient API error (429, 503, overloaded)."""
    err_msg = str(exc)
    return any(
        x in err_msg or x in err_msg.lower()
        for x in [
            "429",
            "503",
            "overloaded",
            "resource_exhausted",
        ]
    )


async def _call_with_breaker(
    breaker: CircuitBreaker, fn, *args, timeout: float | None = None, **kwargs
):
    # Apply rate limiting based on the breaker before attempting the call
    if breaker.name == "llm_ocr":
        await _OCR_LIMITER.wait()
    elif breaker.name == "llm_embed":
        await _EMBED_LIMITER.wait()
    else:
        await _TEXT_LIMITER.wait()
    effective_timeout = timeout or _INVOKE_TIMEOUT

    async def _fn_with_timeout():
        try:
            return await asyncio.wait_for(
                fn(*args, **kwargs), timeout=effective_timeout
            )
        except asyncio.TimeoutError:
            log_json(
                _logger,
                logging.WARNING,
                "LLM invoke timed out",
                timeout=effective_timeout,
                breaker=breaker.name,
            )
            raise TimeoutError(f"LLM did not respond within {effective_timeout}s")

    try:
        return await breaker.call(
            _fn_with_timeout, ignore_on_failure=is_transient_error
        )
    except CircuitBreakerOpen as exc:
        log_json(_logger, logging.ERROR, "LLM circuit open", error=str(exc))
        raise
    except Exception as exc:
        log_level = logging.WARNING if is_transient_error(exc) else logging.ERROR
        log_json(
            _logger,
            log_level,
            "LLM call failed",
            error=str(exc),
            breaker=breaker.name,
        )
        raise


async def _stream_with_breaker(breaker: CircuitBreaker, fn, *args, **kwargs):
    allowed, state = await breaker._allow_call()
    if not allowed:
        if state == "half_open":
            raise CircuitBreakerOpen(
                f"Circuit breaker '{breaker.name}' is half-open (recovering but at capacity)"
            )
        raise CircuitBreakerOpen(f"Circuit breaker '{breaker.name}' is open")

    try:
        if asyncio.iscoroutinefunction(fn):
            it = await fn(*args, **kwargs)
        else:
            it = fn(*args, **kwargs)
            if asyncio.iscoroutine(it):
                it = await it
        aiter = it.__aiter__()
        first = True
        while True:
            try:
                if first:
                    # Timeout only on the first chunk — if the model connects but never responds
                    chunk = await asyncio.wait_for(
                        aiter.__anext__(), timeout=_STREAM_FIRST_CHUNK_TIMEOUT
                    )
                    await breaker._on_success()
                    first = False
                else:
                    chunk = await aiter.__anext__()
            except asyncio.TimeoutError:
                await breaker._on_failure()
                log_json(
                    _logger,
                    logging.ERROR,
                    "LLM stream timed out waiting for first chunk",
                    timeout=_STREAM_FIRST_CHUNK_TIMEOUT,
                    breaker=breaker.name,
                )
                raise TimeoutError(
                    f"LLM did not respond within {_STREAM_FIRST_CHUNK_TIMEOUT}s"
                )
            except StopAsyncIteration:
                break
            yield chunk
    except (TimeoutError, asyncio.TimeoutError):
        raise
    except Exception as exc:
        if not is_transient_error(exc):
            await breaker._on_failure()
        log_level = logging.WARNING if is_transient_error(exc) else logging.ERROR
        log_json(
            _logger,
            log_level,
            "LLM stream failed",
            error=str(exc),
            breaker=breaker.name,
        )
        raise


async def generate_text(prompt: str, model_name: str) -> str:
    client = _get_text_client()
    model = (
        model_name.replace("models/", "", 1)
        if model_name.startswith("models/")
        else model_name
    )

    async def _call():
        response = await client.aio.models.generate_content(
            model=model,
            contents=prompt,
        )
        return response.text or ""

    text = await _call_with_breaker(_TEXT_BREAKER, _call)
    log_json(
        _logger,
        logging.INFO,
        "LLM response received",
        text_length=len(text) if text else 0,
    )
    return text


_BREAKER_TIMEOUT_CONFIGS = {
    "llm_ocr": ("ocr_gemini_timeout", 300.0),
    "llm_generate": ("rag_gemini_chat_timeout", 60.0),
    "llm_embed": ("embed_gemini_timeout", 15.0),
}


async def get_system_config_timeout(key: str, default_val: float) -> float:
    try:
        from app.db import session as db_session
        from app.db.repositories.system_configs_repository import (
            SystemConfigsRepository,
        )

        async with db_session.async_session_factory() as session:
            repo = SystemConfigsRepository(session)
            val_str = await repo.get_value(key)
            if val_str:
                return float(val_str)
    except Exception as e:
        _logger.warning("Failed to fetch system config for %s: %s", key, e)
    return default_val


_MODEL_MAJOR_VERSION_RE = re.compile(r"gemini-(\d+)")


def disabled_thinking_config(model_name: str) -> dict:
    """
    OCR is pure transcription, not a reasoning task — without disabling
    "thinking", the model can burn its entire output budget on hidden
    thinking and return finishReason=STOP with zero actual output tokens
    (silent, no error surfaced).
    Most models (including gemini-3.7-flash, gemini-3.5-flash, gemini-2.5-flash)
    disable thinking via thinking_budget=0. Thinking-only models (like
    gemini-3.1-pro or gemini-3.6-flash) require thinking_level='LOW'.
    Note: 'MINIMAL' is not supported by Google Gemini API and causes INVALID_ARGUMENT.
    """
    if "3.1" in model_name or "3.6" in model_name:
        return {"thinking_level": "LOW"}
    return {"thinking_budget": 0}


async def generate_text_with_image(
    prompt: str, image_bytes: bytes, model_name: str, timeout: float | None = None
) -> str:
    client = _get_ocr_client()
    model = (
        model_name.replace("models/", "", 1)
        if model_name.startswith("models/")
        else model_name
    )
    image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
    config = types.GenerateContentConfig(
        temperature=0.0,
        system_instruction=prompt,
        thinking_config=types.ThinkingConfig(**disabled_thinking_config(model)),
        max_output_tokens=settings.ocr_max_output_tokens,
    )
    effective_timeout = timeout or await get_system_config_timeout(
        "ocr_gemini_timeout", _OCR_INVOKE_TIMEOUT
    )
    if effective_timeout is not None:
        config.http_options = types.HttpOptions(timeout=int(effective_timeout * 1000))

    async def _call():
        response = await client.aio.models.generate_content(
            model=model,
            contents=[image_part],
            config=config,
        )
        return response.text or ""

    text = await _call_with_breaker(_OCR_BREAKER, _call, timeout=effective_timeout)
    log_json(
        _logger,
        logging.INFO,
        "LLM response received",
        text_length=len(text) if text else 0,
    )
    return text


class ProtectedLLM:
    """
    A protected LLM wrapper that adds circuit breaker protection
    for both non-streaming (ainvoke) and streaming (astream) calls.
    """

    def __init__(self, model_name: str, breaker: CircuitBreaker):
        self.model_name = model_name
        self.breaker = breaker

    async def ainvoke(
        self, input: Any, config: Any | None = None, **kwargs: Any
    ) -> str:
        client = _get_text_client()
        prompt = _normalize_prompt_value(input)
        model = (
            self.model_name.replace("models/", "", 1)
            if self.model_name.startswith("models/")
            else self.model_name
        )

        timeout = kwargs.pop("timeout", None)
        timeout_config_key = kwargs.pop("timeout_config_key", None)
        if timeout is None:
            if timeout_config_key:
                default_val = (
                    300.0
                    if "summary" in timeout_config_key or "ocr" in timeout_config_key
                    else 30.0
                )
                timeout = await get_system_config_timeout(
                    timeout_config_key, default_val
                )
            else:
                config_key, default_val = _BREAKER_TIMEOUT_CONFIGS.get(
                    self.breaker.name, (None, _INVOKE_TIMEOUT)
                )
                if config_key:
                    timeout = await get_system_config_timeout(config_key, default_val)
                else:
                    timeout = default_val

        if timeout is not None:
            if config is None:
                config = types.GenerateContentConfig(
                    http_options=types.HttpOptions(timeout=int(timeout * 1000))
                )
            elif isinstance(config, dict):
                config = config.copy()
                config["http_options"] = types.HttpOptions(timeout=int(timeout * 1000))
            elif isinstance(config, types.GenerateContentConfig):
                config.http_options = types.HttpOptions(timeout=int(timeout * 1000))

        async def _call():
            response = await client.aio.models.generate_content(
                model=model, contents=prompt, config=config, **kwargs
            )
            return response.text or ""

        text = await _call_with_breaker(self.breaker, _call, timeout=timeout)
        log_json(
            _logger,
            logging.INFO,
            "ProtectedLLM response received",
            text_length=len(text) if text else 0,
        )
        return text

    async def astream(
        self, input: Any, config: Any | None = None, **kwargs: Any
    ) -> AsyncIterator[str]:
        client = _get_text_client()
        prompt = _normalize_prompt_value(input)
        model = (
            self.model_name.replace("models/", "", 1)
            if self.model_name.startswith("models/")
            else self.model_name
        )
        log_json(_logger, logging.INFO, "ProtectedLLM stream started", model=model)

        timeout = kwargs.pop("timeout", None)
        timeout_config_key = kwargs.pop("timeout_config_key", None)
        if timeout is None:
            if timeout_config_key:
                default_val = (
                    300.0
                    if "summary" in timeout_config_key or "ocr" in timeout_config_key
                    else 30.0
                )
                timeout = await get_system_config_timeout(
                    timeout_config_key, default_val
                )
            else:
                config_key, default_val = _BREAKER_TIMEOUT_CONFIGS.get(
                    self.breaker.name, (None, _INVOKE_TIMEOUT)
                )
                if config_key:
                    timeout = await get_system_config_timeout(config_key, default_val)
                else:
                    timeout = default_val

        if timeout is not None:
            if config is None:
                config = types.GenerateContentConfig(
                    http_options=types.HttpOptions(timeout=int(timeout * 1000))
                )
            elif isinstance(config, dict):
                config = config.copy()
                config["http_options"] = types.HttpOptions(timeout=int(timeout * 1000))
            elif isinstance(config, types.GenerateContentConfig):
                config.http_options = types.HttpOptions(timeout=int(timeout * 1000))

        async def _get_stream():
            return await client.aio.models.generate_content_stream(
                model=model, contents=prompt, config=config, **kwargs
            )

        chunk_count = 0
        async for chunk in _stream_with_breaker(self.breaker, _get_stream):
            text_chunk = chunk.text
            if text_chunk:
                chunk_count += 1
                yield text_chunk
        log_json(
            _logger, logging.INFO, "ProtectedLLM stream completed", chunks=chunk_count
        )

    def invoke(self, input: Any, config: Any | None = None, **kwargs: Any) -> str:
        return _run_sync(self.ainvoke(input, config, **kwargs))


def build_text_llm(model_name: str) -> ProtectedLLM:
    """Build a protected LLM instance."""
    return ProtectedLLM(model_name, _TEXT_BREAKER)


class GeminiEmbeddings:
    def __init__(self, model_name: str | None = None) -> None:
        if not model_name:
            raise ValueError("model_name is required for GeminiEmbeddings")
        self.model_name = (
            model_name.replace("models/", "", 1)
            if model_name.startswith("models/")
            else model_name
        )

    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        import aiohttp
        from app.core.config import settings

        model_name = self.model_name
        dimensions = 3072 if "gemini-embedding-2" in model_name else 768

        async def _call():
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:batchEmbedContents?key={settings.gemini_api_key}"
            requests = []
            for t in texts:
                req = {
                    "model": f"models/{model_name}",
                    "content": {"parts": [{"text": t}]},
                }
                if dimensions:
                    req["outputDimensionality"] = dimensions
                requests.append(req)

            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15.0)
            ) as session:
                async with session.post(url, json={"requests": requests}) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    if "embeddings" not in data:
                        raise ValueError(f"No embeddings returned from API: {data}")
                    return [e["values"] for e in data["embeddings"]]

        return await _call_with_breaker(_EMBED_BREAKER, _call)

    async def aembed_query(self, text: str) -> List[float]:
        if not text:
            return []

        import aiohttp
        from app.core.config import settings

        model_name = self.model_name
        dimensions = 3072 if "gemini-embedding-2" in model_name else 768

        async def _call():
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:embedContent?key={settings.gemini_api_key}"
            req = {
                "model": f"models/{model_name}",
                "content": {"parts": [{"text": text}]},
            }
            if dimensions:
                req["outputDimensionality"] = dimensions

            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15.0)
            ) as session:
                async with session.post(url, json=req) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    if "embedding" not in data:
                        raise ValueError(f"No embedding returned from API: {data}")
                    return data["embedding"]["values"]

        return await _call_with_breaker(_EMBED_BREAKER, _call)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return _run_sync(self.aembed_documents(texts))

    def embed_query(self, text: str) -> List[float]:
        return _run_sync(self.aembed_query(text))


def _run_sync(awaitable):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        return asyncio.run_coroutine_threadsafe(awaitable, loop).result()
    return asyncio.run(awaitable)
