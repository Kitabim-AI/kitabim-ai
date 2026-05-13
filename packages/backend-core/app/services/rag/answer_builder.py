"""Answer generation helpers — LLM call wrappers for all handlers."""
from __future__ import annotations

import logging
from typing import AsyncIterator, List, Optional

from langchain_core.documents import Document

from app.core.i18n import t
from app.utils.observability import log_json
from app.services.rag.utils import build_empty_response_message

logger = logging.getLogger("app.rag.answer_builder")


def build_instructions(
    strict_no_answer: bool,
    suppress_page_notice: bool,
    persona_prompt: Optional[str] = None,
    is_global: bool = False,
    has_categories: bool = False,
) -> str:
    prefix = ""
    if persona_prompt:
        prefix = f"Persona: {persona_prompt}\n\n"

    if strict_no_answer:
        return (
            prefix
            + "Instructions:\n"
            "1. Primary Goal: Answer the user's question ONLY based on the provided context.\n"
            "2. Chat History: Review the chat history to understand follow-up questions, references to previous topics, and conversational context. If the user asks 'what about...', 'tell me more', or uses pronouns like 'it', 'that', or 'this', refer to the chat history to understand what they're asking about.\n"
            "3. If the answer is NOT in the context, respond with exactly: " + t("errors.chat_no_answer") + "\n"
            "4. Format your response in markdown:\n"
            "   - Use double newlines (\\n\\n) to separate paragraphs for better readability\n"
            "   - Use **bold** for emphasis on key terms\n"
            "   - Use bullet points (- ) for lists when appropriate\n"
            "5. Respond ONLY in professional Uyghur (Arabic script).\n"
            "6. STRICT RULE: Output ONLY Uyghur text. Do not include English words, translations, or explanations in other languages."
        )

    extra_rules = ""
    if suppress_page_notice:
        extra_rules = "\n9. If you can answer, do NOT mention whether the current page contained the answer."
    if is_global:
        extra_rules += (
            "\n10. Skip any greetings, introductions, or pleasantries (e.g., 'Hello', "
            "'As-salamu alaykum', 'How can I help you?'). Start your response directly "
            "with the answer or the most relevant information."
        )

    librarian_fallback = ""
    if is_global and has_categories:
        librarian_fallback = (
            "   - Suggest that the user ask the Librarian (زېرەكچاق) for assistance "
            "with books or authors outside your specific expertise.\n"
        )

    return (
        prefix
        + "Instructions:\n"
        "1. Primary Goal: Answer the user's question based on the provided context.\n"
        "2. Chat History: Review the chat history to understand follow-up questions, references to previous topics, and conversational context. If the user asks 'what about...', 'tell me more', or uses pronouns like 'it', 'that', or 'this', refer to the chat history to understand what they're asking about.\n"
        "3. Format your response in markdown:\n"
        "   - Use double newlines (\\n\\n) to separate paragraphs for better readability\n"
        "   - Use **bold** for emphasis on key terms or important information\n"
        "   - Use bullet points (- ) for lists when presenting multiple items\n"
        "   - Use > for direct quotations from the source text\n"
        "4. If the context contains the information, ALWAYS cite the source clearly.\n"
        "   Each document in the context starts with a header like: [BookID: abc123, Book: title, Author: name, Volume: N, Page: N]\n"
        "   Book summaries use the marker SUMMARY instead of Page: [BookID: abc123, Book: title, Author: name, SUMMARY]\n"
        "   You MUST use the EXACT author name from the 'Author:' field in that header. If there is no 'Author:' field in the header, omit the author from the citation entirely — do NOT write any 'unknown' or placeholder text for the author.\n"
        "5. Format citations in Uyghur as a markdown link.\n"
        "   For page-based sources, the link URL MUST be in the format 'ref:book_id:page_number'.\n"
        "   If multiple pages are referenced, separate the page numbers with commas in the URL (e.g. 'ref:book_id:9,10').\n"
        "   For SUMMARY-marked sources (no Page field), use 'ref:book_id:summary' as the URL.\n"
        "   STRICT RULE: Do NOT include the 'BookID: abc123' part in the visible text label of the link! Keep the book ID ONLY in the URL parenthesis.\n"
        "   Example (page): **مەنبە:** [ئانا يۇرت (زوردۇن سابىر)، 1-توم، 25-بەت](ref:abc123:25)\n"
        "   Example (summary): **مەنبە:** [ئانا يۇرت (زوردۇن سابىر) — قىسقىچە مەزمۇنى](ref:abc123:summary)\n"
        "6. Replace 'abc123' with the actual BookID in the URL, and use the exact values from the context header for the author/title. **Citations must be placed immediately after the relevant sentence or paragraph they support. NEVER group all citations at the end of your response.**\n"
        "7. If the context is marked as 'NO RELEVANT DOCUMENTS FOUND' or does not contain the answer:\n"
        "   - Politely explain that you couldn't find a specific match in the indexed books.\n"
        "   - Skip any greeting and directly state that no match was found.\n"
        + librarian_fallback
        + "   - If it's a general question or greeting, respond naturally but maintain your persona as a librarian advisor.\n"
        "8. Respond ONLY in professional Uyghur (Arabic script).\n"
        "9. STRICT RULE: Output ONLY Uyghur text. Do not include English words, translations, or mixed-language sentences. Maintain purely Uyghur syntax and vocabulary."
        + extra_rules
    )


def format_document(doc: Document) -> str:
    title = doc.metadata.get("title") or "Unknown"
    author = doc.metadata.get("author") or None
    volume = doc.metadata.get("volume")
    page = doc.metadata.get("page")
    book_id = doc.metadata.get("book_id") or "unknown"

    source_parts = [f"BookID: {book_id}", f"Book: {title}"]
    if author:
        source_parts.append(f"Author: {author}")
    if volume is not None:
        source_parts.append(f"Volume: {volume}")
    if page is not None:
        source_parts.append(f"Page: {page}")

    header = ", ".join(source_parts)
    return f"[{header}]\n{doc.page_content}"


async def generate_answer(
    context: str,
    question: str,
    chain,
    *,
    chat_history: str = "",
    strict_no_answer: bool = False,
    suppress_page_notice: bool = False,
    persona_prompt: Optional[str] = None,
    is_global: bool = False,
    has_categories: bool = False,
) -> str:
    instructions = build_instructions(
        strict_no_answer, suppress_page_notice, persona_prompt, is_global, has_categories
    )
    response_text = await chain.ainvoke(
        {
            "context": context,
            "instructions": instructions,
            "chat_history": chat_history,
            "question": question,
        }
    )
    return response_text.strip() or build_empty_response_message()


async def generate_answer_stream(
    context: str,
    question: str,
    chain,
    *,
    chat_history: str = "",
    strict_no_answer: bool = False,
    suppress_page_notice: bool = False,
    persona_prompt: Optional[str] = None,
    is_global: bool = False,
    has_categories: bool = False,
) -> AsyncIterator[str]:
    """Stream answer chunks as they are generated by the LLM."""
    instructions = build_instructions(
        strict_no_answer, suppress_page_notice, persona_prompt, is_global, has_categories
    )
    has_content = False
    chunk_count = 0

    async for chunk in chain.astream(
        {
            "context": context,
            "instructions": instructions,
            "chat_history": chat_history,
            "question": question,
        }
    ):
        if chunk:
            has_content = True
            chunk_count += 1
            chunk_size = len(chunk) if isinstance(chunk, str) else 0
            log_json(
                logger,
                logging.INFO,
                "Streaming chunk",
                chunk_num=chunk_count,
                chunk_size=chunk_size,
                chunk_type=type(chunk).__name__,
            )
            yield chunk

    log_json(logger, logging.INFO, "Stream generation complete", total_chunks=chunk_count)

    if not has_content:
        yield build_empty_response_message()


async def categorize_question(question: str, categories: List[str], chain) -> List[str]:
    """Use LLM chain to match a question to a list of known categories."""
    if not categories:
        return []
    response = await chain.ainvoke(
        {
            "categories": categories,
            "question": question,
        }
    )
    if not response:
        return []
    return [str(x) for x in (response.categories or [])]
