OCR_PROMPT = (
    "Extract all text from this image as high-quality Uyghur text with light Markdown structure. "
    "The text is in Uyghur. Rules: "
    "1. If it is NOT a poem, DO NOT break sentences into multiple lines to match page width; "
    "provide continuous text for each paragraph. "
    "2. Maintain separate paragraphs. "
    "3. Preserve punctuation exactly and keep Uyghur symbols & Arabic script. "
    "4. Identify and preserve structure: "
    "use Markdown headings for titles/headers/chapters, "
    "if a table of contents is detected render it as a Markdown pipe table "
    "(data rows only, no header row and no separator line, one row per entry), "
    "keep poems with their original line breaks, "
    "and include header/footer text (if present) on separate lines, prefixed with "
    "\"[Header]\" or \"[Footer]\". "
    "5. If the page contains no readable text, output nothing at all — no placeholders, "
    "no explanations, no filler text. "
    "6. Output ONLY the recognized Uyghur text with the minimal Markdown needed for structure. "
)

SPELL_CHECK_PROMPT = """You are an expert {language} language and OCR error detection specialist.

Analyze the following text for:
1. Spelling errors
2. OCR recognition errors (common for scanned documents)
3. Grammar issues that might be OCR-related
4. Character confusion (similar-looking characters)

Text to analyze:
{text}

Return a JSON array of corrections. Each correction should have:
- "original": the incorrect text as it appears
- "corrected": the suggested correction
- "confidence": a number from 0 to 1 indicating how confident you are
- "context": a short snippet showing the surrounding text (max 50 chars)

Only include corrections where confidence >= 0.6.
If no issues found, return an empty list.

{format_instructions}"""

CATEGORY_PROMPT = """You are a librarian efficiently categorizing a user's question to find the right section of the library.

Available Categories: {categories}

User's New Question: "{question}"

Task: Identify which of the available categories are most relevant to this *New Question*.
If the question is completely general or doesn't fit any category, return an empty list.

{format_instructions}"""

RAG_PROMPT_TEMPLATE = """
[CONTEXT START]
{context}
[CONTEXT END]

{instructions}

[CHAT HISTORY START]
{chat_history}
[CHAT HISTORY END]

Question: {question}
"""
