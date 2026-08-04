"""Exact-phrase chat turn support — keyword-search-rework-plan.md Phase 1.

Quoted / explicit-exact-phrase questions are answered by the keyword-only
leg, with no vector or graph fusion. Page-finding phrasing ("find pages
with...") is formatted as raw page hits instead of an LLM-synthesized
answer; other exact-phrase questions still get an LLM-synthesized answer,
but built only from the exact-phrase matches.
"""

from __future__ import annotations

from typing import List, Optional

from app.core.i18n import t
from app.core.providers import get_vector_store
from app.services.rag.phrase_intent import PhraseIntent
from app.services.rag.retrieval import exact_phrase_chunk_search


async def run_exact_phrase_retrieval(
    session,
    phrase_intent: PhraseIntent,
    book_ids: Optional[List[str]],
    categories: Optional[List[str]],
    limit: int,
    is_global: bool = True,
) -> tuple[List[dict], dict]:
    """Run the keyword-only exact-phrase leg and package the hits as a
    `search_chunks`-shaped observation, so the existing grading/rerank/
    answer-agent pipeline can consume it unchanged for non-page-finding
    exact-phrase questions.

    Returns (raw_hits, observation).
    """
    chunks_repo = get_vector_store(session)
    hits = await exact_phrase_chunk_search(
        chunks_repo,
        phrase_intent.phrases,
        book_ids=book_ids,
        categories=categories,
        limit=limit,
    )
    if not hits and book_ids is not None and is_global:
        hits = await exact_phrase_chunk_search(
            chunks_repo,
            phrase_intent.phrases,
            book_ids=None,
            categories=categories,
            limit=limit,
        )
    chunks = [
        {
            "book_id": h.get("book_id"),
            "page_number": h.get("page_number")
            if h.get("page_number") is not None
            else h.get("page"),
            "page": h.get("page")
            if h.get("page") is not None
            else h.get("page_number"),
            "text": h.get("text", ""),
            "title": h.get("title") or "Unknown",
            "volume": h.get("volume"),
            "author": h.get("author"),
            "score": h.get("rank", 0.0),
        }
        for h in hits
    ]
    observation = {
        "tool": "search_chunks",
        "result": {
            "ok": True,
            "data": {"chunks": chunks},
            "found_count": len(chunks),
        },
    }
    return hits, observation


def format_page_hits(hits: List[dict]) -> List[dict]:
    """Structured page-hit payload for the `page_hits` SSE event."""
    return [
        {
            "bookId": h.get("book_id"),
            "title": h.get("title") or "Unknown",
            "volume": h.get("volume"),
            "author": h.get("author"),
            "page": h.get("page_number"),
            "snippet": (h.get("text") or "")[:280],
        }
        for h in hits
    ]


def summarize_page_hits_as_text(hits: List[dict], phrase: str) -> str:
    """Plain-text fallback used for conversation persistence — the SSE
    `page_hits` event carries the structured version for live rendering."""
    if not hits:
        return t("rag.exact_phrase_no_matches", phrase=phrase)

    lines = [t("rag.exact_phrase_page_hits_header", count=len(hits))]
    for h in hits:
        title = h.get("title") or "Unknown"
        page = h.get("page_number")
        if page is not None:
            lines.append(
                f"- {t('rag.exact_phrase_page_hit_line', title=title, page=page)}"
            )
        else:
            lines.append(
                f"- {t('rag.exact_phrase_page_hit_line_no_page', title=title)}"
            )
    return "\n".join(lines)
