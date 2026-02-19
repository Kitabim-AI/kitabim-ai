from __future__ import annotations

import asyncio
import base64
import inspect
import logging
from typing import List

from langchain_core.embeddings import Embeddings
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableLambda
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
    ),
)




_EMBED_BREAKER = CircuitBreaker(
    "llm_embed",
    CircuitBreakerConfig(
        failure_threshold=settings.llm_cb_failure_threshold,
        recovery_timeout=float(settings.llm_cb_recovery_seconds),
        half_open_max_calls=settings.llm_cb_half_open_max_calls,
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


def build_text_llm(model_name: str) -> RunnableLambda:
    async def _call_llm(prompt_value) -> str:
        prompt = _normalize_prompt_value(prompt_value)
        return await generate_text(prompt, model_name)

    return RunnableLambda(_call_llm)


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
