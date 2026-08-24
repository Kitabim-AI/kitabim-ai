"""LLM-based reranker replacing _grade_context's relative-score selection with
real semantic reranking. _grade_context itself is untouched and remains the
fallback path when the reranker call fails, times out, or returns malformed
output — see the retrieval design spec for the error-handling rationale."""

from __future__ import annotations

import json
import logging

from google.genai import types

from app.core.prompts import RAG_RERANK_PROMPT
from app.llm.models import build_text_llm
from app.services.rag.agent.config import (
    AGENT_MAX_CONTEXT_CHUNKS,
    CHUNK_RESULT_TOOLS,
    MIN_CHUNKS_AFTER_GRADING,
    RERANK_MAX_INPUT_CHUNKS,
)
from app.services.rag.answer_builder import Document, format_document
from app.utils.observability import log_json

logger = logging.getLogger("app.services.rag.agent.reranker")

_NO_DOCS_MESSAGE = "NO RELEVANT DOCUMENTS FOUND IN THE LIBRARY."


def _pool_and_dedup(observations: list[dict]) -> tuple[list[Document], int]:
    """Pool chunks from every search_chunks/search_keyword_phrase observation,
    deduped by (book_id, page). No relevance filtering here — that's the reranker's
    job, not this pooling step (data hygiene only, same dedup _grade_context always did)."""
    docs: list[Document] = []
    total_raw_chunks = 0
    seen: set[tuple] = set()

    for obs in observations:
        if obs.get("tool") not in CHUNK_RESULT_TOOLS:
            continue

        res = obs.get("result", {})
        if not res.get("ok", False):
            continue
        data = res.get("data") or res
        if not isinstance(data, dict):
            continue
        chunks = data.get("chunks", [])
        if not chunks:
            continue
        total_raw_chunks += len(chunks)
        for c in chunks:
            page_val = (
                c.get("page") if c.get("page") is not None else c.get("page_number")
            )
            key = (c.get("book_id"), page_val)
            if key in seen:
                continue
            seen.add(key)
            docs.append(
                Document(
                    page_content=c.get("text", ""),
                    metadata={
                        "title": c.get("title") or "Unknown",
                        "author": c.get("author") or None,
                        "volume": c.get("volume"),
                        "page": page_val,
                        "page_number": page_val,
                        "book_id": c.get("book_id"),
                        "score": c.get("score", 0.0),
                        "rrf_score": c.get("rrf_score", 0.0),
                        "rank": c.get("rank"),
                        "surah_name_en": c.get("surah_name_en"),
                        "surah": c.get("surah"),
                        "ayah": c.get("ayah"),
                    },
                )
            )
    return docs, total_raw_chunks


def _metadata_parts(observations: list[dict]) -> list[str]:
    parts = []
    for obs in observations:
        res = obs.get("result", {})
        if not res.get("ok", False):
            continue
        data = res.get("data") or res
        if isinstance(data, dict) and data.get("context"):
            parts.append(data["context"])
    return parts


def _join_context(metadata_parts: list[str], chunk_parts: list[str]) -> str:
    all_parts = metadata_parts + chunk_parts
    return "\n\n---\n\n".join(all_parts) if all_parts else _NO_DOCS_MESSAGE


async def rerank_context(
    question: str,
    observations: list[dict],
    model: str,
    max_chunks: int | None = None,
) -> tuple[str, int, int]:
    """Drop-in replacement for _grade_context(observations) — same
    (graded_context, before_count, after_count) return shape. Raises on any
    judge failure (call error, timeout, malformed/out-of-range response);
    callers must catch and fall back to _grade_context."""
    docs, total_raw_chunks = _pool_and_dedup(observations)
    metadata_parts = _metadata_parts(observations)

    if not docs:
        return _join_context(metadata_parts, []), total_raw_chunks, 0

    candidates = docs
    if len(candidates) > RERANK_MAX_INPUT_CHUNKS:
        candidates = sorted(
            candidates,
            key=lambda d: (
                d.metadata.get("rrf_score", 0.0),
                d.metadata.get("score", 0.0),
            ),
            reverse=True,
        )[:RERANK_MAX_INPUT_CHUNKS]

    numbered = "\n\n".join(
        f"[{i}] {format_document(d)}" for i, d in enumerate(candidates, start=1)
    )
    prompt = RAG_RERANK_PROMPT.format(question=question, candidates=numbered)

    llm = build_text_llm(model)
    res_text = await llm.ainvoke(
        prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=list[int],
        ),
    )

    start = res_text.find("[")
    if start == -1:
        raise ValueError(f"Reranker response contained no JSON array: {res_text!r}")

    # raw_decode parses just the first complete JSON value starting at `start`
    # and ignores anything after it — unlike a greedy bracket regex, this
    # can't be tricked into over-capturing when the model appends trailing
    # commentary (violating the "JSON only" instruction) that happens to
    # contain another '[' or ']' further along in the text.
    try:
        indices, _ = json.JSONDecoder().raw_decode(res_text, start)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Reranker response was not valid JSON: {res_text!r}") from exc

    if not isinstance(indices, list):
        raise ValueError(f"Reranker response was not a JSON list: {indices!r}")

    ordered_docs: list[Document] = []
    seen_idx: set[int] = set()
    for idx in indices:
        # response_schema constrains the model to a JSON integer array, but
        # numeric strings (e.g. "26") have been observed in production
        # despite that — coerce unambiguous numeric strings before validating range.
        if isinstance(idx, str) and idx.strip().lstrip("-").isdigit():
            idx = int(idx)
        if not isinstance(idx, int) or not (1 <= idx <= len(candidates)):
            raise ValueError(f"Reranker returned an out-of-range index: {idx!r}")
        if idx in seen_idx:
            continue
        seen_idx.add(idx)
        ordered_docs.append(candidates[idx - 1])

    if not ordered_docs and candidates:
        # Mirrors _grade_context's existing floor (llm_routed_handler.py), but
        # only triggers on a total rejection (0 of N judged relevant) — a
        # partial, reasoned selection (e.g. 2 of 3) is exactly the filtering
        # the reranker exists to do and must not be padded back out. Library
        # content often requires synthesis rather than a verbatim answer, and
        # a strict "none relevant" LLM verdict shouldn't unilaterally veto
        # everything the answer-generation LLM could still use — fill up to
        # the floor with the next-best original-score candidates instead.
        for d in sorted(
            candidates,
            key=lambda d: (
                d.metadata.get("rrf_score", 0.0),
                d.metadata.get("score", 0.0),
            ),
            reverse=True,
        )[:MIN_CHUNKS_AFTER_GRADING]:
            ordered_docs.append(d)

    limit = max_chunks if max_chunks is not None else AGENT_MAX_CONTEXT_CHUNKS
    graded = ordered_docs[:limit]

    log_json(
        logger,
        logging.INFO,
        "Context reranked",
        before=total_raw_chunks,
        after=len(graded),
    )
    chunk_parts = [format_document(d) for d in graded]
    return _join_context(metadata_parts, chunk_parts), total_raw_chunks, len(graded)
