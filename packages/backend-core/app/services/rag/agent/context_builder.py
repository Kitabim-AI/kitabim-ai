"""Format agent observations into a context string for the answer LLM."""
from __future__ import annotations

from typing import List, Tuple

from langchain_core.documents import Document

from app.services.rag.agent.config import AGENT_MAX_CONTEXT_CHUNKS
from app.services.rag.answer_builder import format_document


def format_observations_as_context(observations: list[dict]) -> Tuple[str, List[str], int]:
    """Convert accumulated tool observations into (context_str, used_book_ids, chunk_count).

    Tools that return a "context" key (get_book_author, get_books_by_author, search_catalog)
    are prepended as metadata context. search_chunks results are deduplicated, capped at
    MAX_CONTEXT_CHUNKS, and sorted by similarity score DESC.
    """
    # Metadata context from catalog/author/lookup tools (any tool returning a "context" key)
    metadata_parts = [
        obs["result"]["context"]
        for obs in observations
        if obs.get("result", {}).get("context")
    ]

    # Chunk context from search_chunks
    seen: set[tuple] = set()
    documents: List[Document] = []

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

    if not documents and not metadata_parts:
        return "NO RELEVANT DOCUMENTS FOUND IN THE LIBRARY.", [], 0

    documents.sort(key=lambda d: d.metadata["score"], reverse=True)
    documents = documents[:AGENT_MAX_CONTEXT_CHUNKS]

    parts = list(metadata_parts) + [format_document(doc) for doc in documents]

    # Collect book IDs from both chunk results and get_book_summary results so the next
    # turn's context_book_ids is populated even when retrieval relied on summaries only.
    chunk_book_ids = {str(doc.metadata["book_id"]) for doc in documents if doc.metadata.get("book_id")}
    summary_book_ids = {
        str(summary["book_id"])
        for obs in observations
        if obs.get("tool") == "get_book_summary"
        for summary in obs.get("result", {}).get("summaries", [])
        if summary.get("book_id")
    }
    used_book_ids = list(chunk_book_ids | summary_book_ids)

    return "\n\n---\n\n".join(parts), used_book_ids, len(documents)
