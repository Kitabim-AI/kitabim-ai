from __future__ import annotations

import asyncio
import base64
import inspect
import logging
from typing import Any, AsyncIterator, List

from langchain_core.embeddings import Embeddings
from langchain_core.messages import HumanMessage
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

from app.core.config import settings
from app.utils.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitBreakerOpen
from app.utils.observability import log_json
from app.utils.rate_limiter import RedisRateLimiter

_logger = logging.getLogger("app.llm")

# Rate limit for Gemini API (Total across all workers)
# The user's quota is 25 RPM; we use 20 to be safe.
_GEMINI_LIMITER = RedisRateLimiter("gemini_api", limit=20, window=60)

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

def update_breaker_config(failure_threshold: int | None = None, recovery_timeout: float | None = None) -> None:
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


def _build_chat_model(model_name: str, temperature: float | None = None) -> ChatGoogleGenerativeAI:
    cache_key = (model_name, temperature)
    cached = _CHAT_MODEL_CACHE.get(cache_key)
    if cached is not None:
        return cached
    kwargs = _build_kwargs(ChatGoogleGenerativeAI, model_name)
    # Enable streaming for better UX
    kwargs["streaming"] = True
    # Add retries to handle transient 503 errors
    kwargs["max_retries"] = 3
    # Suppress thinking output — model still thinks internally but thoughts
    # are not included in the streamed response shown to users.
    kwargs["include_thoughts"] = False
    if temperature is not None:
        kwargs["temperature"] = temperature
    model = ChatGoogleGenerativeAI(**kwargs)
    _CHAT_MODEL_CACHE[cache_key] = model
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
            elif isinstance(part, dict):
                # Skip thought/thinking parts from Gemini thinking models
                if part.get("thought") or part.get("type") in ("thinking", "thought"):
                    continue
                if "text" in part:
                    parts.append(str(part["text"]))
        return "".join(parts)
    return str(response)


async def _call_with_breaker(breaker: CircuitBreaker, fn, *args, **kwargs):
    # Apply global rate limiting before attempting the call
    await _GEMINI_LIMITER.wait()
    
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
    llm = _build_chat_model(model_name, temperature=0)
    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    content = [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
    ]
    message = HumanMessage(content=content)

    async def _call():
        return await llm.ainvoke([message])

    response = await _call_with_breaker(_OCR_BREAKER, _call)
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


_STREAM_FIRST_CHUNK_TIMEOUT = 60.0  # seconds to wait for the first chunk before treating as failure


async def _stream_with_breaker(breaker: CircuitBreaker, fn, *args, **kwargs):
    allowed, state = await breaker._allow_call()
    if not allowed:
        if state == "half_open":
            raise CircuitBreakerOpen(f"Circuit breaker '{breaker.name}' is half-open (recovering but at capacity)")
        raise CircuitBreakerOpen(f"Circuit breaker '{breaker.name}' is open")

    try:
        it = fn(*args, **kwargs)
        aiter = it.__aiter__()
        first = True
        while True:
            try:
                if first:
                    # Timeout only on the first chunk — if the model connects but never responds
                    chunk = await asyncio.wait_for(aiter.__anext__(), timeout=_STREAM_FIRST_CHUNK_TIMEOUT)
                    await breaker._on_success()
                    first = False
                else:
                    chunk = await aiter.__anext__()
            except asyncio.TimeoutError:
                await breaker._on_failure()
                log_json(_logger, logging.ERROR, "LLM stream timed out waiting for first chunk", timeout=_STREAM_FIRST_CHUNK_TIMEOUT, breaker=breaker.name)
                raise TimeoutError(f"LLM did not respond within {_STREAM_FIRST_CHUNK_TIMEOUT}s")
            except StopAsyncIteration:
                break
            yield chunk
    except (TimeoutError, asyncio.TimeoutError):
        raise
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
