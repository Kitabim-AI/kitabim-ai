from __future__ import annotations

import asyncio
from typing import Iterable, List, Optional

from langchain_core.embeddings import Embeddings
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda

from google.genai import types
from app.core.config import settings
from app.services import genai_client


def _extract_model_text(response) -> Optional[str]:
    try:
        text = response.text
        if text:
            return text
    except Exception:
        pass

    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        if not content:
            continue
        parts = getattr(content, "parts", None) or []
        for part in parts:
            part_text = getattr(part, "text", None)
            if part_text:
                return part_text
    return None


async def generate_text(prompt: str, model_name: str) -> str:
    client = genai_client.get_genai_client()
    response = await client.aio.models.generate_content(
        model=model_name,
        contents=prompt,
    )
    return _extract_model_text(response) or ""


class GeminiEmbeddings(Embeddings):
    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or settings.gemini_embedding_model

    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        client = genai_client.get_genai_client()
        result = await client.aio.models.embed_content(
            model=self.model_name,
            contents=texts,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=768,
            ),
        )
        return genai_client.extract_embeddings_list(result)

    async def aembed_query(self, text: str) -> List[float]:
        if not text:
            return []
        client = genai_client.get_genai_client()
        result = await client.aio.models.embed_content(
            model=self.model_name,
            contents=text,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_QUERY",
                output_dimensionality=768,
            ),
        )
        vector = genai_client.extract_embedding_vector(result)
        return vector or []

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return _run_sync(self.aembed_documents(texts))

    def embed_query(self, text: str) -> List[float]:
        return _run_sync(self.aembed_query(text))


class PromptChainFactory:
    @staticmethod
    def build_text_chain(template: str, model_name: str) -> RunnableLambda:
        prompt = PromptTemplate.from_template(template)

        async def _call_llm(rendered: str) -> str:
            return await generate_text(rendered, model_name)

        llm = RunnableLambda(_call_llm)
        return prompt | llm | StrOutputParser()


def _run_sync(awaitable):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        return asyncio.run_coroutine_threadsafe(awaitable, loop).result()
    return asyncio.run(awaitable)
