"""Utilities for preparing Q&A Markdown answers for Gemini TTS synthesis."""

from __future__ import annotations

import re

# Matches Kitabim citation links such as [«كىتاب نامى»، 42-بەت](ref:book-id:42)
_REF_LINK_RE = re.compile(r"\[([^\]]+)\]\(ref:[^)]+\)")
_REF_PAREN_RE = re.compile(r"\(ref:[^)]+\)")
_BOOK_ID_RE = re.compile(r"\s*\(?BookID:\s*[a-zA-Z0-9_-]+\)?", re.IGNORECASE)
_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]+\)")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_CODE_FENCE_RE = re.compile(r"^```[^\n]*$", re.MULTILINE)
_TABLE_SEP_RE = re.compile(
    r"^\s*\|?(?:\s*:?-{2,}:?\s*\|)+\s*:?-{2,}:?\s*\|?\s*$", re.MULTILINE
)
_HEADING_RE = re.compile(r"^\s*#{1,6}\s+", re.MULTILINE)
_BLOCKQUOTE_RE = re.compile(r"^\s*>+\s?", re.MULTILINE)
_BULLET_RE = re.compile(r"^\s*[-*+•]\s+", re.MULTILINE)
_HR_RE = re.compile(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$", re.MULTILINE)
_INLINE_CODE_RE = re.compile(r"(`+)([^`]+)\1")
_BOLD_RE = re.compile(r"(\*\*|__)(.+?)\1", re.DOTALL)
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_STRIKE_RE = re.compile(r"~~(.+?)~~", re.DOTALL)
# Strip common emoji / pictograph ranges while preserving Arabic/Uyghur/Latin/digits/punctuation
_EMOJI_RE = re.compile(
    "["
    "\U0001f300-\U0001f9ff"
    "\U0001fa00-\U0001faff"
    "\U00002600-\U000027bf"
    "\U0000fe0f"
    "\U0000200d"
    "]+",
    flags=re.UNICODE,
)
_SENTENCE_BOUNDARY_RE = re.compile(r"[.؟!؛\n]")


def prepare_answer_for_tts(
    raw_markdown: str, max_chars: int = 5000
) -> tuple[str, bool]:
    """Convert a Markdown Q&A answer into clean spoken text for Gemini TTS.

    Preserves Uyghur numbers, dates, and natural paragraph breaks (gemini-3.8-flash-tts
    pronounces raw Uyghur numerals natively). Strips Markdown syntax, internal `ref:`
    citation URLs, raw web URLs, and non-speech symbols.

    Returns:
        (cleaned_text, was_truncated)
    """
    if not raw_markdown:
        return "", False

    text = raw_markdown.replace("\r\n", "\n").replace("\r", "\n")

    # 1. Clean Kitabim citation links and BookID tags first
    text = _REF_LINK_RE.sub(r"\1", text)
    text = _REF_PAREN_RE.sub("", text)
    text = _BOOK_ID_RE.sub("", text)

    # 2. Strip markdown structure & formatting
    text = _CODE_FENCE_RE.sub("", text)
    text = _TABLE_SEP_RE.sub("", text)
    text = _MD_IMAGE_RE.sub(r"\1", text)
    text = _MD_LINK_RE.sub(r"\1", text)
    text = _URL_RE.sub("", text)
    text = _HR_RE.sub("", text)
    text = _HEADING_RE.sub("", text)
    text = _BLOCKQUOTE_RE.sub("", text)
    text = _BULLET_RE.sub("", text)
    text = _INLINE_CODE_RE.sub(r"\2", text)
    text = _BOLD_RE.sub(r"\2", text)
    text = _ITALIC_RE.sub(r"\1", text)
    text = _STRIKE_RE.sub(r"\1", text)

    # Convert table cell pipes into natural comma pauses
    cleaned_lines: list[str] = []
    for line in text.split("\n"):
        if "|" in line:
            cells = [c.strip() for c in line.strip().strip("|").split("|") if c.strip()]
            line = "، ".join(cells)
        cleaned_lines.append(line.strip())
    text = "\n".join(cleaned_lines)

    # 3. Strip emojis and control characters (keep \n)
    text = _EMOJI_RE.sub("", text)
    text = "".join(ch for ch in text if ch == "\n" or ord(ch) >= 32)

    # 4. Normalize whitespace while preserving paragraph breaks
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()

    if not text:
        return "", False

    # 5. Enforce max character cap cleanly at sentence boundary when possible
    if max_chars > 0 and len(text) > max_chars:
        slice_text = text[:max_chars]
        # Prefer cutting at the last sentence-ending punctuation past 60% of max_chars
        min_cut = int(max_chars * 0.6)
        last_boundary = -1
        for m in _SENTENCE_BOUNDARY_RE.finditer(slice_text):
            if m.end() >= min_cut:
                last_boundary = m.end()
        if last_boundary > 0:
            text = slice_text[:last_boundary].strip()
        else:
            # Fall back to last whitespace
            ws_cut = slice_text.rfind(" ")
            text = (slice_text[:ws_cut] if ws_cut > min_cut else slice_text).strip()
        return text, True

    return text, False


def split_tts_chunks(text: str, max_chunk_chars: int = 2500) -> list[str]:
    """Split long cleaned text into paragraph-aligned chunks for stable TTS synthesis."""
    if not text:
        return []
    if len(text) <= max_chunk_chars:
        return [text]

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buf = ""

    for para in paragraphs:
        if len(para) > max_chunk_chars:
            if buf:
                chunks.append(buf)
                buf = ""
            # Split oversized paragraph on sentence boundaries
            sentences = [
                s.strip() for s in re.split(r"(?<=[.؟!؛])\s+", para) if s.strip()
            ]
            s_buf = ""
            for sent in sentences:
                cand = f"{s_buf} {sent}".strip() if s_buf else sent
                if len(cand) <= max_chunk_chars:
                    s_buf = cand
                else:
                    if s_buf:
                        chunks.append(s_buf)
                    # Hard-split only if a single sentence itself exceeds max_chunk_chars
                    if len(sent) > max_chunk_chars:
                        for i in range(0, len(sent), max_chunk_chars):
                            chunks.append(sent[i : i + max_chunk_chars].strip())
                        s_buf = ""
                    else:
                        s_buf = sent
            if s_buf:
                chunks.append(s_buf)
            continue

        cand = f"{buf}\n\n{para}" if buf else para
        if len(cand) <= max_chunk_chars:
            buf = cand
        else:
            if buf:
                chunks.append(buf)
            buf = para

    if buf:
        chunks.append(buf)

    return chunks
