"""Lazy-loaded LLM chains and embeddings — module-level singleton."""
from __future__ import annotations

from app.langchain import GeminiEmbeddings, build_text_chain
from app.core.prompts import QUERY_REWRITE_PROMPT, RAG_PROMPT_TEMPLATE


class LLMResources:
    """Lazy-load and cache Gemini chains and embeddings by model name.

    Constructed once at module level and reused across all requests.
    """

    def __init__(self) -> None:
        self._rag_chains: dict = {}
        self._rewrite_chains: dict = {}
        self._embeddings_cache: dict = {}

    def get_embeddings(self, model_name: str) -> GeminiEmbeddings:
        if model_name not in self._embeddings_cache:
            self._embeddings_cache[model_name] = GeminiEmbeddings(model_name)
        return self._embeddings_cache[model_name]

    def get_rag_chain(self, model_name: str):
        if model_name not in self._rag_chains:
            self._rag_chains[model_name] = build_text_chain(
                RAG_PROMPT_TEMPLATE, model_name, run_name="rag_chain"
            )
        return self._rag_chains[model_name]

    def get_rewrite_chain(self, model_name: str):
        if model_name not in self._rewrite_chains:
            self._rewrite_chains[model_name] = build_text_chain(
                QUERY_REWRITE_PROMPT, model_name, run_name="rewrite_chain"
            )
        return self._rewrite_chains[model_name]


# Module-level singleton — shared across all RAGService instances and workers.
llm_resources = LLMResources()
