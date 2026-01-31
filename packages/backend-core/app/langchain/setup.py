from __future__ import annotations

import logging
import os

from app.core.config import settings
from app.utils.observability import log_json


def _set_langsmith_env() -> None:
    if settings.langchain_tracing_enabled:
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
        if settings.langchain_project:
            os.environ.setdefault("LANGCHAIN_PROJECT", settings.langchain_project)


def configure_langchain() -> None:
    logger = logging.getLogger("app.langchain")
    _set_langsmith_env()

    if settings.langchain_tracing_enabled:
        log_json(
            logger,
            logging.INFO,
            "LangChain tracing enabled",
            project=settings.langchain_project or "default",
        )

    if settings.langchain_cache_enabled:
        try:
            try:
                from langchain_core.caches import InMemoryCache
                from langchain_core.globals import set_llm_cache
            except Exception:
                from langchain.cache import InMemoryCache
                from langchain.globals import set_llm_cache

            set_llm_cache(InMemoryCache())
            log_json(logger, logging.INFO, "LangChain in-memory cache enabled")
            return
        except Exception as exc:
            log_json(logger, logging.WARNING, "LangChain cache setup failed", error=str(exc))
        log_json(logger, logging.INFO, "LangChain cache disabled")
