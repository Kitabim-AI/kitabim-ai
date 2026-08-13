"""Query signal & intent extraction — single-shot structured LLM call used
by the chat orchestrator's pre-processing stage."""

from __future__ import annotations

import json
import logging
import re

from google.genai import types

from app.services.rag.agent.tools import _dispatch_tool_with_retry
from app.services.rag.context import QueryContext
from app.utils.observability import log_json

logger = logging.getLogger("app.services.chat.query_signals")


def repair_json_unescaped_quotes(json_str: str) -> str:
    """Repair JSON string values with unescaped internal double quotes."""
    pattern = (
        r'"(rewritten_question|question|intent|catalog_subtype)":\s*"(.*)"\s*(,?)\s*$'
    )

    def escape_internal_quotes(match):
        key = match.group(1)
        val = match.group(2)
        suffix = match.group(3)
        normalized = val.replace('\\"', '"')
        escaped = normalized.replace('"', '\\"')
        return f'"{key}": "{escaped}"{suffix}'

    return re.sub(pattern, escape_internal_quotes, json_str, flags=re.MULTILINE)


async def analyze_query_signals(question: str, ctx: QueryContext) -> dict:
    """Stage 1.5: Query Signal & Intent Extractor LLM Call.

    Uses a single structured JSON response to classify query properties,
    using tool calls to resolve book titles/authors dynamically.
    """
    in_reader = (ctx.current_page is not None) or (
        not ctx.is_global and bool(ctx.book_id)
    )
    current_page = ctx.current_page
    has_history = len(ctx.history) > 0
    history_str = ctx.chat_history_str if has_history else "None"

    async def find_books_by_title(question: str) -> dict:
        """Find books matching a title mentioned in the question.

        Args:
            question: The user's query containing the book title.
        """
        return await _dispatch_tool_with_retry(
            "find_books_by_title", {"question": question}, ctx
        )

    async def get_books_by_author(question: str) -> dict:
        """Find books written by an author mentioned in the question.

        Args:
            question: The user's query containing the author's name.
        """
        return await _dispatch_tool_with_retry(
            "get_books_by_author", {"question": question}, ctx
        )

    prompt = f"""Analyze this query in the context of an Uyghur book reading assistant.

Context:
- In Reader (Active Book Context): {in_reader} (Page: {current_page})
- Has Chat History: {has_history}

Chat History:
{history_str}

Query: {question}

Database Tools:
You have access to tools to query the book database:
- `find_books_by_title(question)`: Call this if the query mentions a specific book title or title keyword to check if the book exists in the library.
- `get_books_by_author(question)`: Call this if the query mentions a specific author to check what books by this author exist in the library.

Before returning the final JSON, call these tools if the user is asking about specific books or authors, so you can determine the catalog signals accurately.

Important Guidelines for Tool Use:
- If a tool call (e.g., `find_books_by_title` or `get_books_by_author`) returns no books or empty results (e.g., `books: []` or `found_count: 0`), do NOT call the tools again with the same or similar arguments.
- Once you have called a tool and successfully found one or more matching books or authors (i.e., `books` is not empty, `found_count > 0`), do NOT keep calling tools to search for other variations of the same name or title. Stop calling tools immediately and output the final JSON response.
- If you cannot find any matching books/authors via tools, stop calling tools and immediately return the final JSON classification with the best available signals. Do not get stuck in an execution loop.

Return ONLY valid JSON matching this schema:
{{
  "is_current_page_query": boolean, // True ONLY if the user explicitly asks about the current page/text they are looking at (e.g. "what is on this page", "read this page", "بۇ بەتتە نېمە بار"). MUST be false if asking about the book as a whole (e.g. "مەن ھازىر ئوقۇۋاتقان كىتابنىڭ ئاساسىي مەزمۇنى نېمە؟", "this book", "currently reading book").
  "is_volume_shift": boolean,       // True if the user wants to go to another volume (e.g. "next volume", "previous volume", "ئالدىنقى توم", "2-توم")
  "target_volume": integer | null,  // The volume number to shift to if specified (e.g. 2, 3), else null
  "needs_rewrite": boolean,         // True ONLY if the query has unresolved pronouns/coreferences or implicit references (ellipsis) referring to prior chat history. MUST be false if the query is fully self-contained, or if there is no chat history.
  "rewritten_question": string | null, // If needs_rewrite is true, rewrite the question to resolve all pronouns/references using chat history to make it self-contained in standard Uyghur (strictly maintaining Uyghur SOV word order and suffix grammar). If needs_rewrite is false, return null.
  "catalog_subtype": "author_of" | "books_by" | "general" | null, // Use "author_of" if asking who wrote a book, "books_by" if asking what books an author wrote, "general" for other catalog/library-wide queries (like "what books do you have"), or null if this is NOT a catalog query.
  "dictionary_subtype": "uyghur_definition" | "history_term" | "english_uyghur" | "spelling" | "names" | "proverbs" | "synonyms" | "general" | null, // Use only when intent is "dictionary".
  "dictionary_term": string | null, // The exact word/term/name/English phrase to look up when intent is "dictionary".
  "quran_surah": integer | null,    // The surah number (1-114) if specified (e.g. 1 for Fatihah, 2 for Baqarah), or null.
  "quran_ayah": integer | null,     // The ayah/verse number if specified, or null.
  "quran_query": string | null,     // The text query or keyword to search inside Quranic verses, or null.
  "intent": "catalog" | "dictionary" | "identity" | "summary" | "relationship" | "passage" | "quran",
  "is_composite": boolean,          // True if the query contains multiple distinct questions or requests that should be handled separately (e.g. "Who wrote X and what is it about?").
  "sub_questions": Array<{{         // If is_composite is true, return each sub-question with its own signals. If is_composite is false, return null.
    "question": string,             // Self-contained sub-question text (pronouns resolved using history, in standard Uyghur SOV grammar)
    "intent": "catalog" | "dictionary" | "identity" | "summary" | "relationship" | "passage" | "quran",
    "is_current_page_query": boolean,
    "is_volume_shift": boolean,
    "target_volume": integer | null,
    "catalog_subtype": "author_of" | "books_by" | "general" | null,
    "dictionary_subtype": "uyghur_definition" | "history_term" | "english_uyghur" | "spelling" | "names" | "proverbs" | "synonyms" | "general" | null,
    "dictionary_term": string | null,
    "quran_surah": integer | null,
    "quran_ayah": integer | null,
    "quran_query": string | null
  }}> | null
}}

Intents:
- catalog     : asking about book metadata, authors of books, book listings, or what books exist in the library
- dictionary  : asking for word meanings, dictionary definitions, spelling validity, names, synonyms, historical vocabulary headword explanations, or English-to-Uyghur translation
- identity    : asking who/what a person or character IS (biography, role, background)
- summary     : asking about the plot, themes, or main characters of a book
- relationship: asking about connections, lineages, family trees, or how X and Y relate
- passage     : asking for specific events, facts, quotes, details, timelines, dates, or historical events/origins (e.g., "when and how was X founded?", "why did X happen?", "tell me about X's history")
- quran       : asking about Quran surahs, verses (ayahs), translations, or searching for specific verses/phrases in the Quran (e.g., "what is surah 1?", "read ayah 1:2", "فاتىھە سۈرىسى", "ئاللاھنىڭ ئىسمى بىلەن باشلايمەن قايسى سۈرىدە بار؟")

Dictionary subtype rules:
- "uyghur_definition": Uyghur word meaning or definition ("X دېگەن نېمە؟", "X مەنىسى نېمە؟")
- "history_term": historical entity/person/place lookup for direct headword definition (e.g. "X كىم؟", "X نېمە؟"). Do NOT use "dictionary" for complex historical questions asking about events, origins, timelines, dates, or causes (e.g. "when/how was X founded?", "why did X happen?") — classify those as "passage".
- "english_uyghur": user asks for the Uyghur translation/equivalent of an English word or phrase
- "spelling": user asks whether a Uyghur spelling is correct or valid
- "names": Uyghur person name lookup, or listing/asking about names starting with a specific letter/alphabet (e.g. "ب ھەرىپىدىن باشلانغان كىشى ئىسىملىرى", "ئالىم دېگەن ئىسىم"). For requests listing names starting with a letter, extract the target letter (e.g., "ب") as the dictionary_term.
- "proverbs": user asks for proverbs, Uyghur proverbs/sayings, or searches for proverbs containing a word (e.g. "ماقال-تەمسىللەر", "بىلىم ھەققىدە ماقال-تەمسىل", "proverb about knowledge")
- "synonyms": user asks for synonyms of a Uyghur word, words with the same or similar meaning, or a list of synonym-dictionary headwords starting with a letter (e.g. "مەنىداش سۆز", "X نىڭ مەنىداش سۆزى نېمە؟", "ئوخشاش مەنىلىك سۆزلەر", "synonym for X")
- "general": dictionary-style query where the exact source is unclear
"""
    from app.llm.models import _get_text_client

    client = _get_text_client()
    model = (
        ctx.agent_model.replace("models/", "", 1)
        if ctx.agent_model.startswith("models/")
        else ctx.agent_model
    )

    contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]

    matched_books = []
    matched_author_books = []
    has_title = False
    has_author = False

    config = types.GenerateContentConfig(
        temperature=0.0,
        tools=[find_books_by_title, get_books_by_author],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    tools_invoked = False

    for _ in range(3):
        # One round of tool calls is all we allow: after the model has had a
        # chance to resolve titles/authors, force the final JSON on the next
        # turn instead of trusting prompt-level "stop calling tools" guidance.
        if tools_invoked and config.tools is not None:
            config.tools = None
            config.response_mime_type = "application/json"

        res_obj = await client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )

        # Add model response to history
        if res_obj.candidates and res_obj.candidates[0].content:
            contents.append(res_obj.candidates[0].content)

        # Check for function calls
        if res_obj.function_calls:
            tools_invoked = True
            parts = []
            for call in res_obj.function_calls:
                name = call.name
                args = call.args or {}
                # Execute tool
                if name == "find_books_by_title":
                    tool_res = await find_books_by_title(**args)
                    if tool_res.get("ok"):
                        books = tool_res.get("books", [])
                        matched_books.extend(books)
                        if books:
                            has_title = True
                elif name == "get_books_by_author":
                    tool_res = await get_books_by_author(**args)
                    if tool_res.get("ok"):
                        books = tool_res.get("books", [])
                        matched_author_books.extend(books)
                        if books:
                            has_author = True
                else:
                    tool_res = {"ok": False, "error": f"Unknown tool: {name}"}

                parts.append(
                    types.Part.from_function_response(name=name, response=tool_res)
                )
            contents.append(types.Content(role="user", parts=parts))
        else:
            # No more function calls, parse final text response
            res_text = res_obj.text or ""
            break
    else:
        raise ValueError("Too many tool call iterations in query analysis")

    m = re.search(r"\{.*\}", res_text, re.DOTALL)
    if m:
        repaired_json = repair_json_unescaped_quotes(m.group())
        result = json.loads(repaired_json)

        # Deduplicate books by ID
        seen_books = set()
        deduped_books = []
        for b in matched_books:
            bid = b.get("id")
            if bid not in seen_books:
                seen_books.add(bid)
                deduped_books.append(b)

        seen_author_books = set()
        deduped_author_books = []
        for b in matched_author_books:
            bid = b.get("id")
            if bid not in seen_author_books:
                seen_author_books.add(bid)
                deduped_author_books.append(b)

        result["has_title"] = has_title
        result["has_author"] = has_author
        result["matched_books"] = deduped_books
        result["matched_author_books"] = deduped_author_books

        log_json(
            logger,
            logging.INFO,
            "Query analyzer result received",
            result=result,
        )
        return result
    raise ValueError("LLM response did not contain a JSON block")
