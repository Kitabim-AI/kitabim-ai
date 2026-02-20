from __future__ import annotations

import asyncio
import base64
import inspect
import logging
from typing import Any, AsyncIterator, List

from langchain_core.embeddings import Embeddings
from langchain_core.messages import HumanMessage
from langchain_core.runnables import Runnable, RunnableConfig, RunnableLambda
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

from app.core.config import settings
from app.utils.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitBreakerOpen
from app.utils.observability import log_json

_logger = logging.getLogger("app.llm")

_TEXT_BREAKER = CircuitBreaker(
    "llm_generate",
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


def is_llm_available() -> bool:
    """Check if the LLM circuit breakers are available."""
    return _TEXT_BREAKER._state != "open" and _EMBED_BREAKER._state != "open"

def update_breaker_config(failure_threshold: int | None = None, recovery_timeout: float | None = None) -> None:
    """Update defaults for both circuit breakers."""
    for breaker in [_TEXT_BREAKER, _EMBED_BREAKER]:
        if failure_threshold is not None:
            breaker.config.failure_threshold = failure_threshold
        if recovery_timeout is not None:
            breaker.config.recovery_timeout = recovery_timeout


def reset_circuit_breakers() -> dict:
    """Manually reset (close) both circuit breakers. Admin control."""
    import time
    for breaker in [_TEXT_BREAKER, _EMBED_BREAKER]:
        breaker._state = "closed"
        breaker._failure_count = 0
        breaker._opened_at = 0.0
        breaker._half_open_in_flight = 0

    return get_circuit_breaker_status()


def force_open_circuit_breakers() -> dict:
    """Manually open both circuit breakers. Admin control."""
    import time
    for breaker in [_TEXT_BREAKER, _EMBED_BREAKER]:
        breaker._state = "open"
        breaker._opened_at = time.monotonic()
        breaker._half_open_in_flight = 0

    return get_circuit_breaker_status()


def get_circuit_breaker_status() -> dict:
    """Get current status of circuit breakers."""
    import time
    now = time.monotonic()

    def breaker_info(breaker):
        time_since_opened = int(now - breaker._opened_at) if breaker._opened_at > 0 else 0
        return {
            "state": breaker._state,
            "failure_count": breaker._failure_count,
            "time_since_opened_seconds": time_since_opened if breaker._state == "open" else 0,
            "recovery_timeout": breaker.config.recovery_timeout,
            "failure_threshold": breaker.config.failure_threshold,
        }

    return {
        "text_breaker": breaker_info(_TEXT_BREAKER),
        "embed_breaker": breaker_info(_EMBED_BREAKER),
        "overall_available": is_llm_available(),
    }


_CHAT_MODEL_CACHE: dict[str, ChatGoogleGenerativeAI] = {}


def _build_kwargs(cls, model_name: str, task_type: str | None = None) -> dict:
    sig = inspect.signature(cls)
    kwargs: dict = {}

    if "model" in sig.parameters:
        kwargs["model"] = model_name
    elif "model_name" in sig.parameters:
        kwargs["model_name"] = model_name

    if task_type and "task_type" in sig.parameters:
        kwargs["task_type"] = task_type

    if "dimensions" in sig.parameters:
        kwargs["dimensions"] = 768
    elif "output_dimensionality" in sig.parameters:
        kwargs["output_dimensionality"] = 768

    if settings.gemini_api_key:
        if "google_api_key" in sig.parameters:
            kwargs["google_api_key"] = settings.gemini_api_key
        elif "api_key" in sig.parameters:
            kwargs["api_key"] = settings.gemini_api_key

    return kwargs


def _build_chat_model(model_name: str) -> ChatGoogleGenerativeAI:
    cached = _CHAT_MODEL_CACHE.get(model_name)
    if cached is not None:
        return cached
    kwargs = _build_kwargs(ChatGoogleGenerativeAI, model_name)
    # Enable streaming for better UX
    kwargs["streaming"] = True
    # Add retries to handle transient 503 errors
    kwargs["max_retries"] = 3
    model = ChatGoogleGenerativeAI(**kwargs)
    _CHAT_MODEL_CACHE[model_name] = model
    return model


def _build_embeddings(model_name: str, task_type: str | None) -> GoogleGenerativeAIEmbeddings:
    kwargs = _build_kwargs(GoogleGenerativeAIEmbeddings, model_name, task_type=task_type)
    return GoogleGenerativeAIEmbeddings(**kwargs)


def _extract_message_text(response) -> str:
    if response is None:
        return ""
    if isinstance(response, str):
        return response
    content = getattr(response, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and "text" in part:
                parts.append(str(part["text"]))
        return "".join(parts)
    return str(response)


async def _call_with_breaker(breaker: CircuitBreaker, fn, *args, **kwargs):
    try:
        return await breaker.call(fn, *args, **kwargs)
    except CircuitBreakerOpen as exc:
        log_json(_logger, logging.ERROR, "LLM circuit open", error=str(exc))
        raise
    except Exception as exc:
        log_json(_logger, logging.ERROR, "LLM call failed", error=str(exc), breaker=breaker.name)
        raise


async def generate_text(prompt: str, model_name: str) -> str:
    llm = _build_chat_model(model_name)

    async def _call():
        return await llm.ainvoke(prompt)

    response = await _call_with_breaker(_TEXT_BREAKER, _call)
    text = _extract_message_text(response)
    log_json(_logger, logging.INFO, "LLM response received", text_length=len(text) if text else 0)
    return text


async def generate_text_with_image(prompt: str, image_bytes: bytes, model_name: str) -> str:
    llm = _build_chat_model(model_name)
    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    content = [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
    ]
    message = HumanMessage(content=content)

    async def _call():
        return await llm.ainvoke([message])

    response = await _call_with_breaker(_TEXT_BREAKER, _call)
    text = _extract_message_text(response)
    log_json(_logger, logging.INFO, "LLM response received", text_length=len(text) if text else 0)
    return text


def _normalize_prompt_value(value) -> str:
    if hasattr(value, "to_string"):
        try:
            return value.to_string()
        except Exception:
            pass
    return str(value)


async def _stream_with_breaker(breaker: CircuitBreaker, fn, *args, **kwargs):
    allowed = await breaker._allow_call()
    if not allowed:
        raise CircuitBreakerOpen(f"Circuit breaker '{breaker.name}' is open")

    try:
        # Get the async iterator (ensure we don't double-await if it's already an iterator)
        it = fn(*args, **kwargs)
        started = False
        async for chunk in it:
            if not started:
                await breaker._on_success()
                started = True
            yield chunk
    except Exception as exc:
        await breaker._on_failure()
        log_json(_logger, logging.ERROR, "LLM stream failed", error=str(exc), breaker=breaker.name)
        raise


class ProtectedLLM(Runnable[Any, str]):
    """
    A protected LLM wrapper that adds circuit breaker protection
    for both non-streaming (ainvoke) and streaming (astream) calls.
    """
    def __init__(self, model: ChatGoogleGenerativeAI, breaker: CircuitBreaker):
        self.model = model
        self.breaker = breaker

    async def ainvoke(
        self, input: Any, config: RunnableConfig | None = None, **kwargs: Any
    ) -> str:
        prompt = _normalize_prompt_value(input)
        async def _call():
            return await self.model.ainvoke(prompt, config=config, **kwargs)
        response = await _call_with_breaker(self.breaker, _call)
        text = _extract_message_text(response)
        log_json(_logger, logging.INFO, "LLM response received", text_length=len(text) if text else 0)
        return text

    async def astream(
        self, input: Any, config: RunnableConfig | None = None, **kwargs: Any
    ) -> AsyncIterator[str]:
        prompt = _normalize_prompt_value(input)
        log_json(_logger, logging.INFO, "LLM stream started", model=self.model.model)
        
        def _get_stream():
            return self.model.astream(prompt, config=config, **kwargs)
            
        chunk_count = 0
        async for chunk in _stream_with_breaker(self.breaker, _get_stream):
            text_chunk = _extract_message_text(chunk)
            if text_chunk:
                chunk_count += 1
                yield text_chunk
        log_json(_logger, logging.INFO, "LLM stream completed", chunks=chunk_count)

    def invoke(self, input: Any, config: RunnableConfig | None = None, **kwargs: Any) -> str:
        return _run_sync(self.ainvoke(input, config, **kwargs))


def build_text_llm(model_name: str) -> ProtectedLLM:
    """Build a protected LLM instance."""
    llm = _build_chat_model(model_name)
    return ProtectedLLM(llm, _TEXT_BREAKER)


class GeminiEmbeddings(Embeddings):
    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or settings.gemini_embedding_model
        self._doc_embeddings = _build_embeddings(self.model_name, task_type="RETRIEVAL_DOCUMENT")
        self._query_embeddings = _build_embeddings(self.model_name, task_type="RETRIEVAL_QUERY")

    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        return await _call_with_breaker(_EMBED_BREAKER, self._doc_embeddings.aembed_documents, texts)

    async def aembed_query(self, text: str) -> List[float]:
        if not text:
            return []
        return await _call_with_breaker(_EMBED_BREAKER, self._query_embeddings.aembed_query, text)

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
