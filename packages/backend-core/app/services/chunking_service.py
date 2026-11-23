import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Sequence

from app.core.config import settings
from app.services.book_structure_service import (
    _detect_repeated_running_headers,
    close_span_before_next,
    format_section_hierarchy_title,
    is_structural_chapter_title,
    parse_page_blocks,
)
from app.utils.text import normalize_section_title, parse_footnote_line


_BLOCK_SEPARATOR = "\n\n"
# Hard character ceiling for a single chunk, sized to stay under gemini-embedding-2's
# 8192-token input limit even for Uyghur Arabic script (~1.3 chars/token conservative).
# Only atomic units larger than this are force-split.
_EMBED_SAFE_CHARS = 4000
_SENTENCE_REGEX_SEP = r"(?<=[.۔؟!؛;»”])\s+"
_SENTENCE_SPLIT_RE = re.compile(_SENTENCE_REGEX_SEP)
_MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+\S")
_FOOTNOTE_MARKERS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
_SUPERSCRIPT_MARKERS = "¹²³⁴⁵⁶⁷⁸⁹"
_NUM_TO_CIRCLED = {str(i + 1): chr(0x2460 + i) for i in range(20)}
_NUM_TO_SUPERSCRIPT = {str(i + 1): ch for i, ch in enumerate(_SUPERSCRIPT_MARKERS)}
_TERMINAL_SENTENCE_PUNCT_RE = re.compile(r"(?:[\.۔!؟?:؛;»\"”…)】\]]|\.\.\.|['’])\s*$")
_TRAILING_HYPHEN_RE = re.compile(r"[-‐‑‒]\s*$")

# (char_start, char_end, page_number) within a unit or buffer string
PageCharSpan = tuple[int, int, int]


def compute_chunk_text_hash(
    text: str,
    *,
    book_title: Optional[str] = None,
    section_title: Optional[str] = None,
) -> str:
    """Compute deterministic SHA-256 hash of the contextual v2 embedding input.

    Incorporating `format_chunk_embedding_text(text, book_title=..., section_title=...)`
    plus the `emb:v2` version tag ensures:
    - Chunks embedded before contextual prefixes were introduced are never reused.
    - Renaming a book or a parent/child section invalidates outdated vectors.
    """
    formatted = format_chunk_embedding_text(
        text,
        book_title=book_title,
        section_title=section_title,
    )
    normalized = " ".join((formatted or "").split())
    return hashlib.sha256(f"emb:v2\0{normalized}".encode("utf-8")).hexdigest()


def extract_chunk_embedding_prefix(
    text: str,
    *,
    book_title: Optional[str] = None,
    section_title: Optional[str] = None,
) -> Optional[str]:
    """Return the contextual header prepended at embedding time (or `None` when unprefixed)."""
    body = (text or "").strip()
    if not body:
        return None

    b_clean = (book_title or "").strip()
    s_clean = (section_title or "").strip()
    if not b_clean and not s_clean:
        return None

    b_norm = normalize_section_title(b_clean) if b_clean else ""
    s_norm = normalize_section_title(s_clean) if s_clean else ""
    head_sample_norm = normalize_section_title(body[:140])

    parts: List[str] = []
    if b_clean and b_norm and b_norm not in head_sample_norm:
        parts.append(b_clean)
    if s_clean and s_norm and s_norm != b_norm and s_norm not in head_sample_norm:
        parts.append(s_clean)

    return " — ".join(parts) if parts else None


def format_chunk_embedding_text(
    text: str,
    *,
    book_title: Optional[str] = None,
    section_title: Optional[str] = None,
) -> str:
    """Build contextual input text for embedding calls while keeping `Chunk.text` unprefixed.

    Prepends `book_title` and `section_title` (when non-redundant) so mid-section
    passages using pronouns or implicit topic references retain strong topical affinity.
    """
    body = (text or "").strip()
    if not body:
        return ""

    header = extract_chunk_embedding_prefix(
        body, book_title=book_title, section_title=section_title
    )
    if not header:
        return body

    combined = f"{header}\n\n{body}"
    if len(combined) <= _EMBED_SAFE_CHARS:
        return combined
    max_body = max(1, _EMBED_SAFE_CHARS - len(header) - 2)
    return f"{header}\n\n{body[:max_body]}"


def extract_leading_overlap(
    prev_text: Optional[str], cur_text: str, max_window: int = 450
) -> Optional[str]:
    """Return the leading prefix of `cur_text` repeated verbatim from the tail of `prev_text`."""
    if not prev_text or not cur_text:
        return None
    p = prev_text.strip()
    c = cur_text.strip()
    if not p or not c or p == c:
        return None
    limit = min(len(p), len(c), max_window)
    for length in range(limit, 19, -1):
        candidate = c[:length]
        if p.endswith(candidate) and (
            length == len(c) or c[length : length + 2] == "\n\n" or c[length].isspace()
        ):
            return candidate
    return None


async def load_book_embedding_context(
    session: Any, book_id: str
) -> tuple[Optional[str], dict[int, str]]:
    """Fetch `(book_title, {section_id: formatted_section_title})` for contextual chunk embedding."""
    if session is None or not book_id:
        return None, {}

    from sqlalchemy import select
    from sqlalchemy.orm import aliased
    from app.db.models import Book, BookSection

    b_res = await session.execute(select(Book.title).where(Book.id == book_id))
    raw_b_title = b_res.scalar_one_or_none()
    book_title = (
        raw_b_title.strip()
        if isinstance(raw_b_title, str) and raw_b_title.strip()
        else None
    )

    parent_bs = aliased(BookSection)
    s_res = await session.execute(
        select(
            BookSection.id,
            BookSection.title,
            BookSection.section_type,
            parent_bs.title,
            parent_bs.section_type,
        )
        .outerjoin(parent_bs, BookSection.parent_id == parent_bs.id)
        .where(BookSection.book_id == book_id)
    )
    section_titles: dict[int, str] = {}
    for sid, stitle, stype, ptitle, pstype in s_res.fetchall():
        formatted_sec = format_section_hierarchy_title(stitle, stype, ptitle, pstype)
        if sid is not None and formatted_sec:
            section_titles[int(sid)] = formatted_sec
    return book_title, section_titles


@dataclass(frozen=True)
class Block:
    """A single logical unit of a document -- a heading, prose/verse paragraph,
    footnote, table, meta_noise, or table-of-contents entry (see ``kind``).
    """

    text: str
    kind: str


@dataclass(frozen=True)
class SectionChunk:
    """Book-scoped chunk with physical page span, enclosing section ID, and SHA-256 text hash."""

    page_number: int
    end_page_number: int
    chunk_index: int
    section_id: Optional[int]
    text: str
    text_hash: str


def _is_heading_line(line: str) -> bool:
    stripped = (line or "").strip()
    return bool(
        _MARKDOWN_HEADING_RE.match(stripped)
        or (len(stripped) <= 90 and is_structural_chapter_title(stripped))
    )


def _should_stitch_cross_page_prose(prev_text: str, next_text: str) -> bool:
    """Return True if a trailing prose block on page p should stitch with
    a leading prose block on page p + 1 within the same leaf section."""
    p_strip = (prev_text or "").strip()
    n_strip = (next_text or "").strip()
    if not p_strip or not n_strip:
        return False
    if n_strip.startswith(("#", "|", "—", "-", "–", "*")):
        return False
    if _TRAILING_HYPHEN_RE.search(p_strip):
        return True
    if not _TERMINAL_SENTENCE_PUNCT_RE.search(p_strip):
        return True
    return False


def _split_prose_on_internal_paragraphs(text: str) -> List[str]:
    """Split a multi-line prose block at clear internal paragraph/dialogue boundaries
    (terminal sentence punctuation followed by a new line starting a dialogue turn or paragraph)
    so cross-page stitching only absorbs the wrapped sentence/paragraph rather than an entire page.
    """
    raw_lines = [ln for ln in (text or "").split("\n") if ln.strip()]
    if len(raw_lines) <= 1:
        return [text.strip()] if (text or "").strip() else []

    segments: List[str] = []
    current: List[str] = [raw_lines[0]]
    for ln in raw_lines[1:]:
        prev = current[-1].rstrip()
        cur_s = ln.lstrip()
        starts_new_turn = cur_s.startswith(("—", "-", "–")) or (
            len(ln) > len(cur_s) and _TERMINAL_SENTENCE_PUNCT_RE.search(prev)
        )
        if _TERMINAL_SENTENCE_PUNCT_RE.search(prev) and (
            starts_new_turn or len("\n".join(current)) >= 250
        ):
            segments.append("\n".join(current).strip())
            current = [ln]
        else:
            current.append(ln)
    if current:
        segments.append("\n".join(current).strip())
    return [seg for seg in segments if seg]


def _clamp_spans(spans: Sequence[PageCharSpan], max_len: int) -> List[PageCharSpan]:
    clamped: List[PageCharSpan] = []
    for cs, ce, pg in spans:
        if cs >= max_len:
            break
        clamped.append((cs, min(ce, max_len), pg))
    return clamped


def _slice_spans(
    spans: Sequence[PageCharSpan], start_idx: int, end_idx: int
) -> List[PageCharSpan]:
    """Slice character-to-page spans to `[start_idx, end_idx)` and rebase to `0`."""
    sliced: List[PageCharSpan] = []
    for cs, ce, pg in spans:
        ov_s = max(cs, start_idx)
        ov_e = min(ce, end_idx)
        if ov_e > ov_s:
            sliced.append((ov_s - start_idx, ov_e - start_idx, pg))
    if not sliced and spans:
        fallback_pg = spans[-1][2] if start_idx >= spans[-1][0] else spans[0][2]
        return [(0, max(0, end_idx - start_idx), fallback_pg)]
    return sliced


def _span_page_bounds(
    spans: Sequence[PageCharSpan], fallback_page: int = 1
) -> tuple[int, int]:
    if not spans:
        return fallback_page, fallback_page
    pages = [pg for cs, ce, pg in spans if ce > cs] or [pg for _, _, pg in spans]
    return min(pages), max(pages)


def _stitch_cross_page_prose_with_spans(
    prev_text: str,
    prev_spans: Sequence[PageCharSpan],
    next_text: str,
    next_page: int,
) -> tuple[str, List[PageCharSpan]]:
    """Join two cross-page prose blocks while tracking exact character-to-page spans."""
    p_strip = prev_text.rstrip()
    n_strip = next_text.lstrip()
    if _TRAILING_HYPHEN_RE.search(p_strip):
        stem = _TRAILING_HYPHEN_RE.sub("", p_strip)
        joined = f"{stem}{n_strip}"
        base_spans = _clamp_spans(prev_spans, len(stem))
        base_spans.append((len(stem), len(joined), int(next_page)))
        return joined, base_spans

    joined = f"{p_strip} {n_strip}"
    base_spans = _clamp_spans(prev_spans, len(p_strip))
    base_spans.append((len(p_strip) + 1, len(joined), int(next_page)))
    return joined, base_spans


def _extract_sentence_tail(text: str, max_overlap: int) -> Optional[tuple[str, int]]:
    """Extract trailing 1-2 complete sentences up to `max_overlap` chars (with soft 1.4x cap
    for a single final sentence) and return `(tail_text, start_char_offset)`."""
    if max_overlap <= 0 or not text:
        return None
    parts = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text.strip()) if s.strip()]
    if len(parts) < 2:
        return None

    chosen: List[str] = []
    total = 0
    hard_cap = max(max_overlap, int(max_overlap * 1.4))
    for sent in reversed(parts):
        sep = 1 if chosen else 0
        cand_len = len(sent) + sep
        if chosen and total + cand_len > max_overlap:
            break
        if not chosen and cand_len > hard_cap:
            return None
        chosen.insert(0, sent)
        total += cand_len
        if len(chosen) >= 2:
            break

    if not chosen:
        return None
    tail = " ".join(chosen)
    pos = text.rfind(chosen[0])
    if pos < 0:
        pos = max(0, len(text) - len(tail))
    return tail, pos


class RecursiveCharacterTextSplitter:
    def __init__(
        self,
        chunk_size: int = 4000,
        chunk_overlap: int = 200,
        length_function: Callable[[str], int] = len,
        separators: Optional[List[str]] = None,
    ):
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._length_function = length_function
        self._separators = separators or ["\n\n", "\n", _SENTENCE_REGEX_SEP, " ", ""]

    def split_text(self, text: str) -> List[str]:
        final_chunks: List[str] = []

        separator = self._separators[-1]
        is_regex_sep = False
        for _s in self._separators:
            if _s == "":
                separator = _s
                break
            if _s == _SENTENCE_REGEX_SEP:
                if _SENTENCE_SPLIT_RE.search(text):
                    separator = _s
                    is_regex_sep = True
                    break
            elif _s in text:
                separator = _s
                break

        if is_regex_sep:
            splits = [s for s in _SENTENCE_SPLIT_RE.split(text) if s]
            join_sep = " "
        elif separator:
            splits = text.split(separator)
            join_sep = separator
        else:
            splits = list(text)
            join_sep = ""

        _good_splits: List[str] = []

        for s in splits:
            if self._length_function(s) < self._chunk_size:
                _good_splits.append(s)
            else:
                if _good_splits:
                    final_chunks.extend(self._merge_splits(_good_splits, join_sep))
                    _good_splits = []
                if not self._separators:
                    final_chunks.append(s[: self._chunk_size])
                else:
                    try:
                        idx = self._separators.index(separator)
                        next_separators = self._separators[idx + 1 :]
                    except ValueError:
                        next_separators = []

                    if next_separators:
                        sub_splitter = RecursiveCharacterTextSplitter(
                            chunk_size=self._chunk_size,
                            chunk_overlap=self._chunk_overlap,
                            length_function=self._length_function,
                            separators=next_separators,
                        )
                        final_chunks.extend(sub_splitter.split_text(s))
                    else:
                        final_chunks.append(s[: self._chunk_size])

        if _good_splits:
            final_chunks.extend(self._merge_splits(_good_splits, join_sep))

        return final_chunks

    def _merge_splits(self, splits: List[str], separator: str) -> List[str]:
        separator_len = self._length_function(separator)
        docs: List[str] = []
        current_doc: List[str] = []
        total = 0
        for d in splits:
            _len = self._length_function(d)
            if total + _len + (separator_len if current_doc else 0) > self._chunk_size:
                if current_doc:
                    doc = separator.join(current_doc)
                    if doc:
                        docs.append(doc)

                    while total > self._chunk_overlap or (
                        total + _len + (separator_len if current_doc else 0)
                        > self._chunk_size
                        and total > 0
                    ):
                        total -= self._length_function(current_doc[0]) + (
                            separator_len if len(current_doc) > 1 else 0
                        )
                        current_doc.pop(0)

            current_doc.append(d)
            total += _len + (separator_len if len(current_doc) > 1 else 0)

        doc = separator.join(current_doc)
        if doc:
            docs.append(doc)
        return docs


class ChunkingService:
    def __init__(
        self,
        chunk_size: int = 1500,
        chunk_overlap: int = 200,
        min_chunk_size: Optional[int] = None,
        max_chunk_size: Optional[int] = None,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        if min_chunk_size is not None:
            self.min_chunk_size = min_chunk_size
        elif chunk_size == 1500:
            self.min_chunk_size = 350
        else:
            self.min_chunk_size = max(1, chunk_size // 3)
        self.max_chunk_size = (
            max_chunk_size if max_chunk_size is not None else _EMBED_SAFE_CHARS
        )
        self.target_size = min(chunk_size, self.max_chunk_size)
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.target_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", _SENTENCE_REGEX_SEP, " ", ""],
            length_function=len,
        )

    def split_text(self, text: Optional[str]) -> List[str]:
        if not text:
            return []
        page_blocks = parse_page_blocks(text, is_toc=False)
        blocks = [Block(pb.raw_text, pb.kind) for pb in page_blocks]
        if not self._has_document_structure(blocks):
            cleaned_text = _BLOCK_SEPARATOR.join(
                block.text
                for block in blocks
                if block.kind not in {"meta_noise", "toc"}
            )
            return self._merge_undersized(
                [c for c in self.text_splitter.split_text(cleaned_text) if c.strip()]
            )
        return self.chunk(blocks)

    def chunk(self, blocks: List[Block]) -> List[str]:
        """Pack a parsed block stream into embedding-sized chunks."""
        content: List[list] = []
        footnotes: List[tuple[int, str, str, str]] = []
        for index, block in enumerate(blocks):
            if block.kind in {"meta_noise", "toc"}:
                continue
            if block.kind == "footnote":
                for raw_m, norm_m, note in self._split_footnote_entries(block.text):
                    footnotes.append((index, raw_m, norm_m, note))
            else:
                content.append([index, block.kind, block.text])

        if footnotes:
            self._attach_footnotes_to_blocks(content, footnotes)
        return self._pack_adaptive(content)

    def chunk_book_sections(
        self,
        pages: Sequence[Any],
        leaf_sections: Optional[Sequence[Any]] = None,
        *,
        book_title: Optional[str] = None,
        section_titles: Optional[dict[int, str]] = None,
    ) -> List[SectionChunk]:
        """Pack each leaf `BookSection` independently into `SectionChunk` rows.

        1. Page-local footnote binding (`① ② ③`, `¹ ² ³`, `[1]:`) before cross-page joining.
        2. Cross-page `'prose'` stitching with exact character-to-page span provenance.
        3. Page-provenance adaptive packing (`1500` / `200` / `350` / `4000`) with
           sentence-level overlap, unprefixed `Chunk.text`, inherited `section_id`, and `text_hash`.
        """

        def _p_num(pg: Any) -> int:
            return int(pg["page_number"] if isinstance(pg, dict) else pg.page_number)

        def _p_is_toc(pg: Any) -> bool:
            return bool(
                pg.get("is_toc", False)
                if isinstance(pg, dict)
                else getattr(pg, "is_toc", False)
            )

        def _p_text(pg: Any) -> str:
            return (
                pg.get("text") if isinstance(pg, dict) else getattr(pg, "text", None)
            ) or ""

        ordered_pages = [
            p
            for p in sorted(pages, key=_p_num)
            if not _p_is_toc(p) and _p_text(p).strip()
        ]
        if not ordered_pages:
            return []

        pages_by_num = {_p_num(p): p for p in ordered_pages}
        running_headers = _detect_repeated_running_headers(ordered_pages)
        parsed_by_page = {
            _p_num(p): parse_page_blocks(
                _p_text(p),
                is_toc=False,
                repeated_running_headers=running_headers,
            )
            for p in ordered_pages
        }

        def _slice_has_body_blocks(sp: int, sb: int, ep: int, eb: int) -> bool:
            for pg_n in range(sp, ep + 1):
                for b in parsed_by_page.get(pg_n, []):
                    if (pg_n > sp or b.block_index >= sb) and (
                        pg_n < ep or b.block_index <= eb
                    ):
                        if b.kind in {"prose", "verse", "table", "footnote"}:
                            return True
            return False

        raw_input_sections: List[Any] = list(leaf_sections or [])
        resolved_section_titles: dict[int, str] = dict(section_titles or {})
        if raw_input_sections:
            by_id_meta: dict[int, tuple[Optional[str], Optional[str]]] = {}
            by_idx_meta: dict[int, tuple[Optional[str], Optional[str]]] = {}
            for s in raw_input_sections:
                s_id = s.get("id") if isinstance(s, dict) else getattr(s, "id", None)
                s_idx = (
                    s.get("section_index")
                    if isinstance(s, dict)
                    else getattr(s, "section_index", None)
                )
                s_title = (
                    s.get("title") if isinstance(s, dict) else getattr(s, "title", None)
                )
                s_type = (
                    s.get("section_type")
                    if isinstance(s, dict)
                    else getattr(s, "section_type", None)
                )
                if s_id is not None:
                    by_id_meta[int(s_id)] = (s_title, s_type)
                if s_idx is not None:
                    by_idx_meta[int(s_idx)] = (s_title, s_type)

            for s in raw_input_sections:
                s_id = s.get("id") if isinstance(s, dict) else getattr(s, "id", None)
                if s_id is None or int(s_id) in resolved_section_titles:
                    continue
                s_title = (
                    s.get("title") if isinstance(s, dict) else getattr(s, "title", None)
                )
                s_type = (
                    s.get("section_type")
                    if isinstance(s, dict)
                    else getattr(s, "section_type", None)
                )
                p_id = (
                    s.get("parent_id")
                    if isinstance(s, dict)
                    else getattr(s, "parent_id", None)
                )
                p_idx = (
                    s.get("parent_section_index")
                    if isinstance(s, dict)
                    else getattr(s, "parent_section_index", None)
                )
                p_title, p_type = (None, None)
                if p_id is not None and int(p_id) in by_id_meta:
                    p_title, p_type = by_id_meta[int(p_id)]
                elif p_idx is not None and int(p_idx) in by_idx_meta:
                    p_title, p_type = by_idx_meta[int(p_idx)]
                fmt_t = format_section_hierarchy_title(s_title, s_type, p_title, p_type)
                if fmt_t:
                    resolved_section_titles[int(s_id)] = fmt_t

        if not raw_input_sections:
            # Fallback if no sections were passed: treat entire book as one synthetic section
            @dataclass
            class _FallbackSection:
                id: Optional[int] = None
                start_page: int = _p_num(ordered_pages[0])
                start_block_index: int = 0
                end_page: int = _p_num(ordered_pages[-1])
                end_block_index: int = 999999

            sections_to_chunk: List[Any] = [_FallbackSection()]
        else:
            # Slice any parent chapter/part down to its own substantive preamble before its
            # first child; skip body-less Part divider preambles (e.g. standalone "ئىككىنچى قىسىم" pages).
            children_by_parent_key: dict[tuple[str, int], List[Any]] = defaultdict(list)
            for s in raw_input_sections:
                p_id = (
                    s.get("parent_id")
                    if isinstance(s, dict)
                    else getattr(s, "parent_id", None)
                )
                p_idx = (
                    s.get("parent_section_index")
                    if isinstance(s, dict)
                    else getattr(s, "parent_section_index", None)
                )
                if p_id is not None:
                    children_by_parent_key[("id", int(p_id))].append(s)
                if p_idx is not None:
                    children_by_parent_key[("idx", int(p_idx))].append(s)

            sections_to_chunk = []
            for s in raw_input_sections:
                s_id = s.get("id") if isinstance(s, dict) else getattr(s, "id", None)
                s_idx = (
                    s.get("section_index")
                    if isinstance(s, dict)
                    else getattr(s, "section_index", None)
                )
                children = []
                if s_id is not None and ("id", int(s_id)) in children_by_parent_key:
                    children = children_by_parent_key[("id", int(s_id))]
                elif (
                    s_idx is not None and ("idx", int(s_idx)) in children_by_parent_key
                ):
                    children = children_by_parent_key[("idx", int(s_idx))].copy()

                if not children:
                    sections_to_chunk.append(s)
                    continue

                def _sec_start(item: Any) -> tuple[int, int]:
                    if isinstance(item, dict):
                        return (
                            int(item["start_page"]),
                            int(item.get("start_block_index", 0)),
                        )
                    return (
                        int(item.start_page),
                        int(getattr(item, "start_block_index", 0)),
                    )

                first_child = min(children, key=_sec_start)
                s_start_p, s_start_b = _sec_start(s)
                fc_start_p, fc_start_b = _sec_start(first_child)
                if (s_start_p, s_start_b) >= (fc_start_p, fc_start_b):
                    continue

                intro_end_p, intro_end_b = close_span_before_next(
                    s_start_p,
                    s_start_b,
                    fc_start_p,
                    fc_start_b,
                    parsed_by_page,
                )
                if not _slice_has_body_blocks(
                    s_start_p, s_start_b, intro_end_p, intro_end_b
                ):
                    continue

                sections_to_chunk.append(
                    {
                        "id": s_id,
                        "start_page": s_start_p,
                        "start_block_index": s_start_b,
                        "end_page": intro_end_p,
                        "end_block_index": intro_end_b,
                    }
                )

        raw_emitted: List[tuple[int, int, Optional[int], str]] = []

        for sec in sections_to_chunk:
            sec_id = getattr(sec, "id", None)
            if isinstance(sec, dict):
                sec_id = sec.get("id")
                s_page = int(sec["start_page"])
                s_blk = int(sec.get("start_block_index", 0))
                e_page = int(sec["end_page"])
                e_blk = int(sec.get("end_block_index", 999999))
            else:
                s_page = int(sec.start_page)
                s_blk = int(getattr(sec, "start_block_index", 0))
                e_page = int(sec.end_page)
                e_blk = int(getattr(sec, "end_block_index", 999999))

            # Step 1: Slice blocks per page and bind page-local footnotes
            # Each unit in `section_units` is `[kind, text, spans]`
            section_units: List[list] = []

            for pnum in range(s_page, e_page + 1):
                if pnum not in pages_by_num:
                    continue
                p_blocks = parsed_by_page.get(pnum, [])
                sliced = [
                    b
                    for b in p_blocks
                    if (pnum > s_page or b.block_index >= s_blk)
                    and (pnum < e_page or b.block_index <= e_blk)
                    and b.kind not in {"toc", "meta_noise"}
                ]
                if not sliced:
                    continue

                page_content: List[list] = []
                page_footnotes: List[tuple[int, str, str, str]] = []
                for local_idx, blk in enumerate(sliced):
                    if blk.kind == "footnote":
                        for raw_m, norm_m, note in self._split_footnote_entries(
                            blk.raw_text
                        ):
                            page_footnotes.append((local_idx, raw_m, norm_m, note))
                    else:
                        page_content.append([local_idx, blk.kind, blk.raw_text])

                if page_footnotes:
                    self._attach_footnotes_to_blocks(page_content, page_footnotes)

                # Step 2: Cross-page prose stitching with character-level span tracking.
                # Only split internal single-\n paragraphs on the leading block of `pnum`
                # when it actually glues onto an unfinished prose block from `pnum - 1`.
                for idx_in_page, (_, kind, text_val) in enumerate(page_content):
                    last_unit_end_page = (
                        section_units[-1][2][-1][2]
                        if (section_units and section_units[-1][2])
                        else -999
                    )
                    if (
                        idx_in_page == 0
                        and section_units
                        and section_units[-1][0] == "prose"
                        and kind == "prose"
                        and int(last_unit_end_page) == pnum - 1
                        and _should_stitch_cross_page_prose(
                            section_units[-1][1], text_val
                        )
                    ):
                        stitch_head = text_val
                        remainder_tail: Optional[str] = None
                        if "\n" in text_val:
                            sub_parts = _split_prose_on_internal_paragraphs(text_val)
                            if len(sub_parts) > 1:
                                stitch_head = sub_parts[0]
                                remainder_tail = "\n".join(sub_parts[1:])

                        joined_txt, joined_spans = _stitch_cross_page_prose_with_spans(
                            section_units[-1][1],
                            section_units[-1][2],
                            stitch_head,
                            pnum,
                        )
                        section_units[-1][1] = joined_txt
                        section_units[-1][2] = joined_spans
                        if remainder_tail:
                            section_units.append(
                                [
                                    kind,
                                    remainder_tail,
                                    [(0, len(remainder_tail), pnum)],
                                ]
                            )
                    else:
                        section_units.append(
                            [kind, text_val, [(0, len(text_val), pnum)]]
                        )

            if not section_units:
                continue

            # Step 3: Adaptive packing with exact per-piece `(start_page, end_page)` provenance
            packed_section = self._pack_adaptive_with_pages(section_units)
            for chunk_text, c_start, c_end in packed_section:
                if chunk_text.strip():
                    raw_emitted.append((c_start, c_end, sec_id, chunk_text.strip()))

        # Assign sequential chunk_index per start_page across the book
        per_page_counter: dict[int, int] = defaultdict(int)
        final_chunks: List[SectionChunk] = []
        for c_start, c_end, sec_id, chunk_text in raw_emitted:
            c_idx = per_page_counter[c_start]
            per_page_counter[c_start] += 1
            sec_title = (
                resolved_section_titles.get(int(sec_id)) if sec_id is not None else None
            )
            final_chunks.append(
                SectionChunk(
                    page_number=c_start,
                    end_page_number=max(c_start, c_end),
                    chunk_index=c_idx,
                    section_id=sec_id,
                    text=chunk_text,
                    text_hash=compute_chunk_text_hash(
                        chunk_text,
                        book_title=book_title,
                        section_title=sec_title,
                    ),
                )
            )
        return final_chunks

    def _pack_adaptive_with_pages(
        self, units: List[list]
    ) -> List[tuple[str, int, int]]:
        """Pack `[kind, text, spans]` units into `(text, start_page, end_page)` chunks."""
        chunks: List[tuple[str, List[PageCharSpan]]] = []
        buffer: List[tuple[str, str, List[PageCharSpan]]] = []

        def build_combined_buffer() -> tuple[str, List[PageCharSpan]]:
            parts: List[str] = []
            combined_spans: List[PageCharSpan] = []
            offset = 0
            sep_len = len(_BLOCK_SEPARATOR)
            for idx, (_, txt, u_spans) in enumerate(buffer):
                if idx > 0:
                    offset += sep_len
                parts.append(txt)
                for cs, ce, pg in u_spans:
                    combined_spans.append((offset + cs, offset + ce, pg))
                offset += len(txt)
            return _BLOCK_SEPARATOR.join(parts), combined_spans

        def buffer_len() -> int:
            if not buffer:
                return 0
            return sum(len(item[1]) for item in buffer) + len(_BLOCK_SEPARATOR) * (
                len(buffer) - 1
            )

        def flush(carry_overlap: bool) -> None:
            nonlocal buffer
            if not buffer:
                return
            combined_text, combined_spans = build_combined_buffer()
            for piece, piece_spans in self._safety_split_with_spans(
                combined_text, combined_spans
            ):
                if piece.strip():
                    chunks.append((piece, piece_spans))
            buffer = self._tail_overlap_units(buffer) if carry_overlap else []

        for kind, text, u_spans in units:
            if (
                kind == "heading"
                and buffer
                and not all(item[0] == "heading" for item in buffer)
            ):
                flush(carry_overlap=False)

            current_len = buffer_len()
            addition = len(text) + (len(_BLOCK_SEPARATOR) if buffer else 0)
            if (
                buffer
                and current_len + addition > self.target_size
                and current_len >= self.min_chunk_size
            ):
                flush(carry_overlap=True)

            buffer.append((kind, text, list(u_spans)))

        flush(carry_overlap=False)

        # Merge undersized chunks backward within the same section while propagating char spans
        merged: List[tuple[str, List[PageCharSpan]]] = []
        sep_len = len(_BLOCK_SEPARATOR)
        for text, c_spans in chunks:
            if (
                merged
                and len(text) < self.min_chunk_size
                and not self._starts_with_heading(text)
                and len(merged[-1][0]) + sep_len + len(text) <= self.max_chunk_size
            ):
                prev_text, prev_spans = merged[-1]
                shift = len(prev_text) + sep_len
                merged_spans = list(prev_spans) + [
                    (cs + shift, ce + shift, pg) for cs, ce, pg in c_spans
                ]
                merged[-1] = (prev_text + _BLOCK_SEPARATOR + text, merged_spans)
            else:
                merged.append((text, c_spans))

        resolved: List[tuple[str, int, int]] = []
        for text, c_spans in merged:
            s_p, e_p = _span_page_bounds(c_spans)
            resolved.append((text, s_p, e_p))
        return resolved

    def _safety_split_with_spans(
        self, text: str, spans: Sequence[PageCharSpan]
    ) -> List[tuple[str, List[PageCharSpan]]]:
        """Split oversized text while mapping each piece to its exact character-range page spans."""
        if len(text) <= self.max_chunk_size:
            return [(text, list(spans))]

        pieces = self.text_splitter.split_text(text)
        result: List[tuple[str, List[PageCharSpan]]] = []
        cursor = 0
        for piece in pieces:
            if not piece:
                continue
            search_from = max(0, cursor - self.chunk_overlap - 64)
            pos = text.find(piece, search_from)
            if pos < 0:
                probe = piece[: min(80, len(piece))]
                pos = text.find(probe, search_from)
            if pos < 0:
                pos = min(cursor, max(0, len(text) - len(piece)))
            end_pos = min(len(text), pos + len(piece))
            piece_spans = _slice_spans(spans, pos, end_pos)
            result.append((piece, piece_spans))
            cursor = max(cursor, end_pos)
        return result

    def _tail_overlap_units(
        self, buffer: List[tuple[str, str, List[PageCharSpan]]]
    ) -> List[tuple[str, str, List[PageCharSpan]]]:
        if self.chunk_overlap <= 0 or not buffer:
            return []
        overlap: List[tuple[str, str, List[PageCharSpan]]] = []
        total = 0
        for kind, text, u_spans in reversed(buffer):
            if kind == "heading" or self._starts_with_heading(text):
                break
            separator_len = len(_BLOCK_SEPARATOR) if overlap else 0
            block_len = len(text) + separator_len
            if total + block_len > self.chunk_overlap:
                break
            overlap.insert(0, (kind, text, list(u_spans)))
            total += block_len

        if overlap:
            return overlap

        # Sentence-level fallback when the trailing prose paragraph exceeds `chunk_overlap`
        last_kind, last_text, last_spans = buffer[-1]
        if last_kind == "prose" and not self._starts_with_heading(last_text):
            extracted = _extract_sentence_tail(last_text, self.chunk_overlap)
            if extracted is not None:
                tail_text, start_off = extracted
                tail_spans = _slice_spans(last_spans, start_off, len(last_text))
                return [("prose", tail_text, tail_spans)]
        return []

    def _attach_footnotes_to_blocks(
        self, content: List[list], footnotes: List[tuple[int, str, str, str]]
    ) -> None:
        """Merge each footnote into the paragraph that references it on the same page."""
        for position, raw_marker, norm_marker, note in footnotes:
            candidate_tokens = [f"[{norm_marker}]", f"({norm_marker})"]
            if raw_marker in _FOOTNOTE_MARKERS or raw_marker in _SUPERSCRIPT_MARKERS:
                candidate_tokens.insert(0, raw_marker)
            else:
                if norm_marker in _NUM_TO_SUPERSCRIPT:
                    candidate_tokens.append(_NUM_TO_SUPERSCRIPT[norm_marker])
                if norm_marker in _NUM_TO_CIRCLED:
                    candidate_tokens.append(_NUM_TO_CIRCLED[norm_marker])

            target: Optional[list] = None
            for item in content:
                if item[0] >= position:
                    break
                if any(tok in item[2] for tok in candidate_tokens):
                    target = item
            if target is None:
                preceding = [item for item in content if item[0] < position]
                target = (
                    preceding[-1] if preceding else (content[-1] if content else None)
                )
            if target is not None:
                target[2] = f"{target[2]}{_BLOCK_SEPARATOR}{note}"

    def _pack_adaptive(self, content: List[list]) -> List[str]:
        """Pack atomic paragraphs into chunks with structure-driven sizing."""
        chunks: List[str] = []
        buffer: List[tuple[int, str, str]] = []

        def buffer_text() -> str:
            return _BLOCK_SEPARATOR.join(text for _, _, text in buffer)

        def flush(carry_overlap: bool) -> None:
            nonlocal buffer
            if not buffer:
                return
            chunks.extend(self._safety_split(buffer_text()))
            buffer = self._tail_overlap_pairs(buffer) if carry_overlap else []

        for index, kind, text in content:
            if (
                kind == "heading"
                and buffer
                and not all(item[1] == "heading" for item in buffer)
            ):
                flush(carry_overlap=False)

            current_len = len(buffer_text())
            addition = len(text) + (len(_BLOCK_SEPARATOR) if buffer else 0)
            if (
                buffer
                and current_len + addition > self.target_size
                and current_len >= self.min_chunk_size
            ):
                flush(carry_overlap=True)

            buffer.append((index, kind, text))

        flush(carry_overlap=False)
        return self._merge_undersized([chunk for chunk in chunks if chunk.strip()])

    def _merge_undersized(self, chunks: List[str]) -> List[str]:
        """Fold a below-minimum chunk into the previous one."""
        merged: List[str] = []
        for chunk in chunks:
            if (
                merged
                and len(chunk) < self.min_chunk_size
                and not self._starts_with_heading(chunk)
                and len(merged[-1]) + len(_BLOCK_SEPARATOR) + len(chunk)
                <= self.max_chunk_size
            ):
                merged[-1] = merged[-1] + _BLOCK_SEPARATOR + chunk
            else:
                merged.append(chunk)
        return merged

    def _starts_with_heading(self, chunk: str) -> bool:
        for line in chunk.splitlines():
            if line.strip():
                return _is_heading_line(line.strip())
        return False

    def _split_footnote_entries(self, block: str) -> List[tuple[str, str, str]]:
        """Split a footnote block into `(raw_marker, normalized_marker, footnote_text)` tuples."""
        entries: List[tuple[str, str, str]] = []
        raw_marker: Optional[str] = None
        norm_marker: Optional[str] = None
        lines: List[str] = []
        for raw_line in block.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            parsed_fn = parse_footnote_line(line)
            if parsed_fn is not None:
                if raw_marker is not None and norm_marker is not None:
                    entries.append((raw_marker, norm_marker, "\n".join(lines).strip()))
                norm_marker = parsed_fn[0]
                raw_marker = (
                    line[0]
                    if (line[0] in _FOOTNOTE_MARKERS or line[0] in _SUPERSCRIPT_MARKERS)
                    else f"[{norm_marker}]"
                )
                lines = [line]
            elif raw_marker is not None:
                lines.append(line)
        if raw_marker is not None and norm_marker is not None:
            entries.append((raw_marker, norm_marker, "\n".join(lines).strip()))
        return entries

    def _has_document_structure(self, blocks: List[Block]) -> bool:
        return any(
            block.kind in {"heading", "toc", "table", "footnote", "verse"}
            for block in blocks
        )

    def _tail_overlap_pairs(
        self, buffer: List[tuple[int, str, str]]
    ) -> List[tuple[int, str, str]]:
        if self.chunk_overlap <= 0 or not buffer:
            return []

        overlap: List[tuple[int, str, str]] = []
        total = 0
        for index, kind, block in reversed(buffer):
            if kind == "heading" or self._starts_with_heading(block):
                break
            separator_len = len(_BLOCK_SEPARATOR) if overlap else 0
            block_len = len(block) + separator_len
            if total + block_len > self.chunk_overlap:
                break
            overlap.insert(0, (index, kind, block))
            total += block_len

        if overlap:
            return overlap

        last_idx, last_kind, last_text = buffer[-1]
        if last_kind == "prose" and not self._starts_with_heading(last_text):
            extracted = _extract_sentence_tail(last_text, self.chunk_overlap)
            if extracted is not None:
                tail_text, _ = extracted
                return [(last_idx, "prose", tail_text)]
        return []

    def _safety_split(self, text: str) -> List[str]:
        """Return the text as a single chunk, splitting only if it exceeds the
        hard ceiling (embedding token safety). Normal paragraphs are never split."""
        if len(text) <= self.max_chunk_size:
            return [text]
        return self.text_splitter.split_text(text)


chunking_service = ChunkingService(
    chunk_size=settings.chunk_size,
    chunk_overlap=settings.chunk_overlap,
    min_chunk_size=settings.chunk_min_size,
)
