"""Retrieval Agent builder using Google ADK"""

from __future__ import annotations

from typing import Optional
from google.adk import Agent

from app.services.rag.agent.prompts import build_agent_system_prompt
from app.services.rag.agent.tools import (
    search_chunks,
    search_keyword_phrase,
    search_books_by_summary,
    find_books_by_title,
    rewrite_query,
    get_book_author,
    get_books_by_author,
    search_catalog,
    get_book_summary,
    get_sister_volumes,
    get_current_page,
    lookup_uyghur_word,
    lookup_history_term,
    translate_english_to_uyghur,
    check_word_spelling,
    lookup_uyghur_name,
    search_language_sources,
    lookup_proverbs,
    lookup_synonyms,
    search_quran,
)

ALL_TOOLS = [
    search_chunks,
    search_keyword_phrase,
    search_books_by_summary,
    find_books_by_title,
    rewrite_query,
    get_book_author,
    get_books_by_author,
    search_catalog,
    get_book_summary,
    get_sister_volumes,
    get_current_page,
    lookup_uyghur_word,
    lookup_history_term,
    translate_english_to_uyghur,
    check_word_spelling,
    lookup_uyghur_name,
    search_language_sources,
    lookup_proverbs,
    lookup_synonyms,
    search_quran,
]


def build_retrieval_agent(
    model: str,
    intent_signals: Optional[dict] = None,
    summary_narrowing_enabled: bool = True,
) -> Agent:
    """Build the Retrieval Agent focused exclusively on tool execution and context gathering.

    The Retrieval Agent uses the retrieval system prompt and tools, stopping once
    evidence is gathered. summary_narrowing_enabled=False (the
    rag_summary_narrowing_enabled system_config) drops the search_books_by_summary
    tool and uses the direct-chunk prompt variant.
    """
    instructions = build_agent_system_prompt(
        summary_narrowing=summary_narrowing_enabled
    )
    if intent_signals:
        hints = []
        if intent_signals.get("intent") and intent_signals["intent"] != "open":
            hints.append(
                f"- Query hint: Primary intent classified as '{intent_signals['intent']}'"
            )
        if intent_signals.get("is_current_page_query"):
            hints.append(
                "- Query hint: User is explicitly asking about the current page — call get_current_page() and STOP."
            )
        if intent_signals.get("is_volume_shift"):
            tv = intent_signals.get("target_volume")
            vol_note = f" (target_volume={tv})" if tv is not None else ""
            hints.append(
                f"- Query hint: User is asking about another volume of the book{vol_note} — call get_sister_volumes first."
            )
        if intent_signals.get("needs_rewrite") and intent_signals.get(
            "rewritten_question"
        ):
            hints.append(
                f"- Query hint: Standalone rewritten question already resolved as '{intent_signals['rewritten_question']}' — do NOT call rewrite_query again; use this standalone phrasing for search tools."
            )
        if intent_signals.get("dictionary_subtype"):
            hints.append(
                f"- Query hint: Dictionary subtype identified as '{intent_signals['dictionary_subtype']}'"
            )
        if intent_signals.get("dictionary_term"):
            hints.append(
                f"- Query hint: Dictionary term already extracted as '{intent_signals['dictionary_term']}' "
                "— pass this exact string as the term argument to whichever dictionary tool you call; "
                "do not re-extract or re-spell it from the raw question."
            )
        if (
            intent_signals.get("quran_surah")
            or intent_signals.get("quran_ayah")
            or intent_signals.get("quran_query")
        ):
            hints.append(
                f"- Query hint: Quran lookup parameters — surah={intent_signals.get('quran_surah')}, "
                f"ayah={intent_signals.get('quran_ayah')}, q={intent_signals.get('quran_query')!r}"
            )
        if intent_signals.get("catalog_subtype"):
            hints.append(
                f"- Query hint: Catalog query subtype identified as '{intent_signals['catalog_subtype']}'"
            )
        pre_matched_ids = list(
            dict.fromkeys(
                str(b["id"])
                for b in [
                    *(intent_signals.get("matched_books") or []),
                    *(intent_signals.get("matched_author_books") or []),
                ]
                if isinstance(b, dict) and b.get("id")
            )
        )
        if pre_matched_ids:
            hints.append(
                f"- Query hint: Book IDs already resolved from the question: {pre_matched_ids[:30]} "
                "— pass these book_ids directly to search_chunks / get_book_summary without re-running find_books_by_title or get_books_by_author."
            )
        if intent_signals.get("is_composite") and isinstance(
            intent_signals.get("sub_questions"), list
        ):
            sub_qs = [
                sq.get("question", "").strip()
                for sq in intent_signals["sub_questions"]
                if isinstance(sq, dict) and sq.get("question")
            ]
            if len(sub_qs) > 1:
                hints.append(
                    "- Query hint: Composite multi-part question — gather evidence covering every sub-question before stopping: "
                    + " ; ".join(f"({i + 1}) {sq}" for i, sq in enumerate(sub_qs))
                )
        if hints:
            instructions += (
                "\n\nStructured Intent Hints from Query Analysis:\n" + "\n".join(hints)
            )

    tools = (
        ALL_TOOLS
        if summary_narrowing_enabled
        else [t for t in ALL_TOOLS if t is not search_books_by_summary]
    )

    agent = Agent(
        model=model,
        name="KitabimRetrievalAgent",
        description="Retrieves evidence from books, Quran, catalog, and dictionaries.",
        instruction=instructions,
        tools=tools,
    )
    return agent
