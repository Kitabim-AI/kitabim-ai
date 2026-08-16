"""Retrieval Agent builder using Google ADK"""

from __future__ import annotations

from typing import Optional
from google.adk import Agent

from app.services.rag.agent.prompts import AGENT_SYSTEM_PROMPT
from app.services.rag.agent.tools import (
    search_chunks,
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
) -> Agent:
    """Build the Retrieval Agent focused exclusively on tool execution and context gathering.

    The Retrieval Agent uses AGENT_SYSTEM_PROMPT and tools, stopping once evidence is gathered.
    """
    instructions = AGENT_SYSTEM_PROMPT
    if intent_signals:
        hints = []
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
        if intent_signals.get("quran_surah") or intent_signals.get("quran_ayah"):
            hints.append(
                f"- Query hint: Quran surah {intent_signals.get('quran_surah')}, ayah {intent_signals.get('quran_ayah')}"
            )
        if intent_signals.get("catalog_subtype"):
            hints.append(
                f"- Query hint: Catalog query subtype identified as '{intent_signals['catalog_subtype']}'"
            )
        if hints:
            instructions += (
                "\n\nStructured Intent Hints from Query Analysis:\n" + "\n".join(hints)
            )

    agent = Agent(
        model=model,
        name="KitabimRetrievalAgent",
        description="Retrieves evidence from books, Quran, catalog, and dictionaries.",
        instruction=instructions,
        tools=ALL_TOOLS,
    )
    return agent
