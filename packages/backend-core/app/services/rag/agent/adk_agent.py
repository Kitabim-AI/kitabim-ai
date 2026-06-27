from __future__ import annotations

from google.adk.agents import Agent
from google.genai import types
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
    query_knowledge_graph,
    lookup_uyghur_word,
    lookup_history_term,
    translate_english_to_uyghur,
    check_word_spelling,
    search_language_sources,
)
from app.services.rag.agent.prompts import AGENT_SYSTEM_PROMPT


def build_rag_agent(model_name: str) -> Agent:
    """Build the Google ADK Agent with standard tools and system instructions."""
    # Strip 'models/' prefix from model name if present
    model = (
        model_name.replace("models/", "", 1)
        if model_name.startswith("models/")
        else model_name
    )

    return Agent(
        name="kitabim_retrieval_agent",
        model=model,
        instruction=AGENT_SYSTEM_PROMPT,
        generate_content_config=types.GenerateContentConfig(temperature=0.0),
        tools=[
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
            query_knowledge_graph,
            lookup_uyghur_word,
            lookup_history_term,
            translate_english_to_uyghur,
            check_word_spelling,
            search_language_sources,
        ],
    )
