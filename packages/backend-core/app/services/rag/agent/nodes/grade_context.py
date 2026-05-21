"""grade_context node — filters retrieved chunks by relative score before answer generation.

Uses a relative score threshold: keeps chunks scoring at least GRADE_RELATIVE_THRESHOLD
of the best chunk's score. Falls back to the full context if fewer than
MIN_CHUNKS_AFTER_GRADING survive, preventing over-filtering on sparse results.
"""
from __future__ import annotations

import logging

from langchain_core.documents import Document
from langgraph.config import get_stream_writer

from app.services.rag.agent.config import AGENT_MAX_CONTEXT_CHUNKS, GRADE_RELATIVE_THRESHOLD, MIN_CHUNKS_AFTER_GRADING
from app.services.rag.agent.state import AgentState
from app.services.rag.answer_builder import format_document
from app.utils.observability import log_json

logger = logging.getLogger("app.rag.agent.nodes.grade_context")


async def grade_context_node(state: AgentState) -> dict:
    writer = get_stream_writer()
    observations = state["observations"]

    # Collect all unique chunks from search_chunks observations
    seen: set[tuple] = set()
    documents: list[Document] = []
    for obs in observations:
        if obs.get("tool") != "search_chunks":
            continue
        for chunk in obs.get("result", {}).get("chunks", []):
            key = (chunk.get("book_id"), chunk.get("page"))
            if key in seen:
                continue
            seen.add(key)
            documents.append(
                Document(
                    page_content=chunk.get("text", ""),
                    metadata={
                        "title": chunk.get("title") or "Unknown",
                        "author": chunk.get("author") or None,
                        "volume": chunk.get("volume"),
                        "page": chunk.get("page"),
                        "book_id": chunk.get("book_id"),
                        "score": chunk.get("score", 0.0),
                    },
                )
            )

    # If no chunk documents (pure catalog/metadata answer), pass retrieved_context through unchanged
    if not documents:
        return {"graded_context": state.get("retrieved_context", "")}

    documents.sort(key=lambda d: d.metadata["score"], reverse=True)
    before_count = len(documents)

    # Apply relative threshold: keep chunks within GRADE_RELATIVE_THRESHOLD of the top score
    top_score = documents[0].metadata["score"] if documents else 0.0
    score_floor = top_score * GRADE_RELATIVE_THRESHOLD
    graded = [d for d in documents if d.metadata["score"] >= score_floor]

    # Safety fallback: don't over-filter
    if len(graded) < MIN_CHUNKS_AFTER_GRADING:
        graded = documents[:MIN_CHUNKS_AFTER_GRADING]

    graded = graded[:AGENT_MAX_CONTEXT_CHUNKS]

    log_json(
        logger, logging.INFO, "Context graded",
        before=before_count, after=len(graded),
        top_score=round(top_score, 3), score_floor=round(score_floor, 3),
    )
    writer({"type": "grading", "before": before_count, "after": len(graded)})

    # Extract metadata context directly from observations to prevent parsing issues
    metadata_parts = [
        obs["result"]["context"]
        for obs in observations
        if obs.get("result", {}).get("context")
    ]

    chunk_parts = [format_document(d) for d in graded]
    all_parts = metadata_parts + chunk_parts
    graded_context = "\n\n---\n\n".join(all_parts) if all_parts else "NO RELEVANT DOCUMENTS FOUND IN THE LIBRARY."

    return {"graded_context": graded_context}
