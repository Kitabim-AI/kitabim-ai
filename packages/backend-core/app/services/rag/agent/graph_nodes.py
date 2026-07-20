"""Pure-Python graph node functions for the deterministic RAG workflow.

All functions here are side-effect free (no LLM calls, no DB access) unless
explicitly noted. They can be unit-tested without mocking external services.

These were previously private helpers in handler.py. They are extracted here
so they can be:
  1. Unit-tested independently (no ADK runner, no DB, no LLM)
  2. Reused by both graph_agent.py and deterministic_handler.py

Exports:
    detect_intent              — Node 1: classify question intent
    decompose_question         — Node 2: heuristic multi-question detection
    is_graph_enabled           — helper: whether KG tool should be offered
    build_human_message        — helper: build human-turn text with context
    grade_context              — Node 5: grade and dedup retrieved chunks
    extract_used_book_ids      — helper: extract book IDs from observations
    populate_ctx_from_observations — helper: write eval metrics back onto ctx
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from app.services.rag.keywords import PAGE_QUERY_PATTERNS
from app.utils.observability import log_json

if TYPE_CHECKING:
    from app.services.rag.context import QueryContext

logger = logging.getLogger("app.rag.agent.graph_nodes")

# ---------------------------------------------------------------------------
# Regex helpers (shared with handler.py / graph_agent.py)
# ---------------------------------------------------------------------------

_COMPARISON_PATTERNS = re.compile(
    r"\b(commonalit|similar|differ|compar|contrast|vs\.?|versus|both|between)\b"
    r"|ئوخشاشلىق|پەرق|سېلىشتۇر|ئىككىسى",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Node 1: Intent Detection
# ---------------------------------------------------------------------------


def detect_intent(question: str, ctx: "QueryContext") -> str:
    """Classify question intent without any LLM call.

    Returns:
        "current_page" — user is asking about the page they are reading
        "content_search" — all other intents; trigger retrieval loop
    """
    q = question.lower()
    if ctx.current_page is not None and any(p in q for p in PAGE_QUERY_PATTERNS):
        return "current_page"
    return "content_search"


# ---------------------------------------------------------------------------
# Node 2: Question Decomposition (heuristic only — no LLM)
# ---------------------------------------------------------------------------


def _question_mark_count(text: str) -> int:
    return text.count("؟") + text.count("?")


def _is_multi_entity_question(text: str) -> bool:
    """Return True when the question compares/contrasts multiple entities."""
    return bool(_COMPARISON_PATTERNS.search(text))


def decompose_question(question: str) -> tuple[list[str], bool]:
    """Heuristic multi-question detection — does NOT call any LLM.

    Returns:
        (sub_questions, was_split) — sub_questions is always a list with at
        least the original question. was_split=True means a follow-up LLM
        split call is warranted (done by graph_agent._llm_split_question).
        When was_split=False the list contains the original question unchanged.
    """
    if _question_mark_count(question) > 1 or _is_multi_entity_question(question):
        return [question], True
    return [question], False


# ---------------------------------------------------------------------------
# Helper: Is KG tool enabled?
# ---------------------------------------------------------------------------


def is_graph_enabled(ctx: "QueryContext") -> bool:
    """Whether query_knowledge_graph should be offered to the retrieval agent."""
    if not ctx.use_knowledge_graph_in_chat:
        return False
    if not ctx.is_global and ctx.book:
        return getattr(ctx.book, "graph_milestone", None) == "complete"
    return True


# ---------------------------------------------------------------------------
# Helper: Build human-turn message with context metadata
# ---------------------------------------------------------------------------


def build_human_message(ctx: "QueryContext", question: str) -> str:
    """Build the human-turn message with contextual metadata injected.

    This is the same logic as _build_human_message in handler.py.
    """
    lines = []
    if not ctx.is_global and ctx.book:
        book = ctx.book
        book_info = f'"{book.title}"' if book.title else "unknown title"
        if book.author:
            book_info += f" by {book.author}"
        if book.volume is not None:
            book_info += f", volume {book.volume}"
        lines.append(f"Current book: {book_info} (book_id: {ctx.book_id})")
        if ctx.current_page is not None:
            lines.append(f"Current page: {ctx.current_page}")
        graph_available = is_graph_enabled(ctx)
        lines.append(f"Graph available: {'yes' if graph_available else 'no'}")
    elif ctx.is_global:
        if not ctx.use_knowledge_graph_in_chat:
            lines.append("Graph available: no")
        if ctx.context_book_ids:
            lines.append(
                f"Previous response book IDs: {', '.join(ctx.context_book_ids[:10])}"
            )
        if ctx.character_categories:
            lines.append(f"Category filter: {', '.join(ctx.character_categories)}")
    if ctx.history:
        lines.append("Chat history: Available (contains prior conversation context)")
    if not lines:
        return question
    return "[Context]\n" + "\n".join(lines) + "\n\n[Question]\n" + question


# ---------------------------------------------------------------------------
# Node 5: Context Grading
# ---------------------------------------------------------------------------


def grade_context(observations: list[dict]) -> tuple[str, int, int]:
    """Grade and deduplicate retrieved chunks from tool observations.

    This is the same logic as _grade_context in handler.py, extracted here
    for independent testability and reuse by deterministic_handler.py.

    Returns:
        (graded_text, raw_chunk_count, graded_chunk_count)
    """
    from app.services.rag.agent.config import (
        AGENT_MAX_CONTEXT_CHUNKS,
        GRADE_RELATIVE_THRESHOLD,
        MIN_CHUNKS_AFTER_GRADING,
    )
    from app.services.rag.answer_builder import Document, format_document

    # Build metadata context from any tool returning a "context" key
    metadata_parts: list[str] = []
    for obs in observations:
        res = obs.get("result", {})
        if not res.get("ok", False):
            continue
        data = res.get("data") or res
        if isinstance(data, dict) and data.get("context"):
            metadata_parts.append(data["context"])

    all_graded_documents: list[Document] = []
    total_raw_chunks = 0
    seen: set[tuple] = set()

    for obs in observations:
        if obs.get("tool") != "search_chunks":
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

        # Convert to Document list for this search tool call
        search_docs = [
            Document(
                page_content=c.get("text", ""),
                metadata={
                    "title": c.get("title") or "Unknown",
                    "author": c.get("author") or None,
                    "volume": c.get("volume"),
                    "page": c.get("page"),
                    "book_id": c.get("book_id"),
                    "score": c.get("score", 0.0),
                    "surah_name_en": c.get("surah_name_en"),
                    "surah": c.get("surah"),
                    "ayah": c.get("ayah"),
                },
            )
            for c in chunks
        ]

        # Grade this specific search call's results
        search_docs.sort(key=lambda d: d.metadata["score"], reverse=True)
        top_score = search_docs[0].metadata["score"]
        score_floor = top_score * GRADE_RELATIVE_THRESHOLD

        graded_search_docs = [
            d for d in search_docs if d.metadata["score"] >= score_floor
        ]

        # Fallback to keep minimum chunks for this specific search if drop is steep
        if len(graded_search_docs) < MIN_CHUNKS_AFTER_GRADING:
            graded_search_docs = search_docs[:MIN_CHUNKS_AFTER_GRADING]

        # Append to global pool, deduplicating along the way
        for doc in graded_search_docs:
            key = (doc.metadata["book_id"], doc.metadata["page"])
            if key in seen:
                continue
            seen.add(key)
            all_graded_documents.append(doc)

    # Final global sort and cap
    if all_graded_documents:
        all_graded_documents.sort(key=lambda d: d.metadata["score"], reverse=True)
        graded = all_graded_documents[:AGENT_MAX_CONTEXT_CHUNKS]
        log_json(
            logger,
            logging.INFO,
            "Context graded (per-search)",
            before=total_raw_chunks,
            after=len(graded),
        )
        chunk_parts = [format_document(d) for d in graded]
        after_count = len(graded)
    else:
        chunk_parts = []
        after_count = 0

    all_parts = metadata_parts + chunk_parts
    graded_context = (
        "\n\n---\n\n".join(all_parts)
        if all_parts
        else "NO RELEVANT DOCUMENTS FOUND IN THE LIBRARY."
    )
    return graded_context, total_raw_chunks, after_count


# ---------------------------------------------------------------------------
# Helper: Extract book IDs from observations
# ---------------------------------------------------------------------------


def extract_used_book_ids(observations: list[dict]) -> list[str]:
    """Extract book IDs from search_chunks and get_book_summary results.

    This is the same logic as _extract_used_book_ids in handler.py.
    """
    chunk_book_ids: set[str] = set()
    for obs in observations:
        if obs.get("tool") == "search_chunks":
            res = obs.get("result", {})
            if res.get("ok", False):
                data = res.get("data") or res
                if isinstance(data, dict):
                    for chunk in data.get("chunks", []):
                        if chunk.get("book_id"):
                            chunk_book_ids.add(str(chunk["book_id"]))

    summary_book_ids: set[str] = set()
    for obs in observations:
        if obs.get("tool") == "get_book_summary":
            res = obs.get("result", {})
            if res.get("ok", False):
                data = res.get("data") or res
                if isinstance(data, dict):
                    for summary in data.get("summaries", []):
                        if summary.get("book_id"):
                            summary_book_ids.add(str(summary["book_id"]))

    return list(chunk_book_ids | summary_book_ids)


# ---------------------------------------------------------------------------
# Helper: Populate ctx eval fields from observations
# ---------------------------------------------------------------------------


def populate_ctx_from_observations(
    ctx: "QueryContext",
    observations: list[dict],
    graded_context: str,
    llm_calls: int,
) -> None:
    """Write retrieval metrics back onto ctx for eval recording.

    This is the same logic as _populate_ctx_from_observations in handler.py,
    extracted here so it can be reused by both graph_agent.py and
    deterministic_handler.py without importing from handler.py.
    """
    all_chunks = [
        chunk
        for obs in observations
        if obs.get("tool") == "search_chunks"
        for chunk in (obs.get("result", {}).get("data") or obs.get("result", {})).get(
            "chunks", []
        )
    ]

    ctx.retrieved_count = len(all_chunks)
    ctx.scores = [c.get("score", 0.0) for c in all_chunks]
    ctx.agent_steps = llm_calls
    ctx.agent_tools_called = [
        obs.get("tool", "") for obs in observations if obs.get("tool")
    ]
    ctx.agent_retry_count = sum(
        1 for obs in observations if obs.get("tool") == "search_chunks"
    )
    ctx.agent_final_chunk_count = graded_context.count("[BookID:")
    ctx.graded_context = graded_context
