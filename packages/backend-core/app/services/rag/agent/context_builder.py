"""Format agent observations into a context string for the answer LLM."""
from __future__ import annotations

from typing import List, Tuple

from langchain_core.documents import Document

from app.services.rag.answer_builder import format_document

def format_observations_as_context(observations: list[dict]) -> Tuple[str, List[str], int]:
    """Convert accumulated tool observations into (context_str, used_book_ids, chunk_count).

    Only `search_chunks` observations contribute to the context.
    Duplicate (book_id, page) pairs are deduplicated, then sorted by similarity
    score DESC so the answer LLM sees the most relevant passages first.
    """
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

    if not documents:
        return "NO RELEVANT DOCUMENTS FOUND IN THE LIBRARY.", [], 0

    documents.sort(key=lambda d: d.metadata["score"], reverse=True)

    parts = [format_document(doc) for doc in documents]
    used_book_ids = list({str(doc.metadata["book_id"]) for doc in documents if doc.metadata.get("book_id")})
    return "\n\n---\n\n".join(parts), used_book_ids, len(documents)
