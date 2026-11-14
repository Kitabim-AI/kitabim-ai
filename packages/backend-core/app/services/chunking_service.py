import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Sequence

from app.core.config import settings
from app.services.book_structure_service import parse_page_blocks
from app.utils.text import is_poem_block, parse_footnote_line


_BLOCK_SEPARATOR = "\n\n"
# Hard character ceiling for a single chunk, sized to stay under gemini-embedding-2's
# 8192-token input limit even for Uyghur Arabic script (~1.3 chars/token conservative).
# Only atomic units larger than this are force-split.
_EMBED_SAFE_CHARS = 4000
_MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+\S")
# Structural noise that must never become its own chunk: HTML page comments
# (e.g. "<!-- page 3 -->") and horizontal rules ("---", "***", "___").
_NOISE_LINE_RE = re.compile(r"^(?:<!--.*-->|-{3,}|\*{3,}|_{3,}|(?:\*\s*){3,})$")
# OCR page header/footer markers (from the OCR prompt), either on their own line
# ("[Footer] 1") or glued to the end of a content line ("...خانىسى.[Footer] 3").
_OCR_HEADER_FOOTER_RE = re.compile(r"\s*\[(?:Header|Footer)\].*", re.IGNORECASE)
_UYGHUR_HEADING_RE = re.compile(
    r"^(?:.+\s+(?:باب|قىسىم|بۆلۈم|پەسىل)|(?:.+\s+.)?(?:مۇقەددىمە|خاتىمە|كىرىش\s+سۆز|سۆز\s+بېشى|ئاخىرقى\s+سۆز))\s*$"
)
_FOOTNOTE_MARKERS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
_FOOTNOTE_RE = re.compile(rf"^[{_FOOTNOTE_MARKERS}]\s+")
_TOC_ENTRY_RE = re.compile(
    r"^(?:[-*•]|\d+[.)])\s*\d{1,4}\b|.*[.·•∙⋅]{3,}\s*\d{1,4}\s*$"
)
_TERMINAL_SENTENCE_PUNCT_RE = re.compile(r"(?:[\.۔!؟?:؛;»\"”…)】\]]|\.\.\.|['’])\s*$")
_TRAILING_HYPHEN_RE = re.compile(r"[-‐‑‒]\s*$")


def compute_chunk_text_hash(text: str) -> str:
    """Compute deterministic SHA-256 hash of whitespace-normalized unprefixed chunk text."""
    normalized = " ".join((text or "").split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


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
    return bool(_MARKDOWN_HEADING_RE.match(line) or _UYGHUR_HEADING_RE.match(line))


def _looks_like_toc_entries(block: str) -> bool:
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    if not lines:
        return False
    matches = sum(1 for line in lines if _TOC_ENTRY_RE.match(line))
    return matches / len(lines) >= 0.5


def _is_table_block(lines: List[str]) -> bool:
    table_lines = sum(
        1 for line in lines if line.startswith("|") and line.endswith("|")
    )
    return table_lines >= 2 and table_lines / len(lines) >= 0.5


def _classify_block(block: str) -> str:
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    if not lines:
        return "prose"
    if all(_NOISE_LINE_RE.match(ln) for ln in lines):
        return "meta_noise"
    if any("مۇندەرىجە" in line for line in lines):
        return "toc"
    if _is_table_block(lines):
        return "table"
    if len(lines) <= 2 and any(_is_heading_line(line) for line in lines):
        return "heading"
    if _FOOTNOTE_RE.match(lines[0]):
        return "footnote"
    if is_poem_block(lines):
        return "verse"
    return "prose"


def _split_block_on_headings(block: str) -> List[str]:
    """Split a raw block so each markdown heading line stands alone."""
    segments: List[str] = []
    current: List[str] = []
    for line in block.splitlines():
        if _MARKDOWN_HEADING_RE.match(line):
            if current:
                segments.append("\n".join(current))
                current = []
            segments.append(line)
        else:
            current.append(line)
    if current:
        segments.append("\n".join(current))
    return segments


def _strip_noise_lines(segment: str) -> str:
    lines = []
    for line in segment.splitlines():
        line = _OCR_HEADER_FOOTER_RE.sub("", line)
        stripped = line.strip()
        if stripped and not _NOISE_LINE_RE.match(stripped):
            lines.append(line)
    return "\n".join(lines).strip()


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


def _stitch_cross_page_prose_text(prev_text: str, next_text: str) -> str:
    """Join two cross-page prose blocks, stripping any trailing line-break hyphen on page p."""
    p_strip = prev_text.rstrip()
    n_strip = next_text.lstrip()
    if _TRAILING_HYPHEN_RE.search(p_strip):
        stem = _TRAILING_HYPHEN_RE.sub("", p_strip)
        return f"{stem}{n_strip}"
    return f"{p_strip} {n_strip}"


class OcrMarkdownParser:
    """Parser for OCR-pipeline markdown (headings, paragraphs, pipe tables)."""

    def parse(self, text: str) -> List[Block]:
        blocks: List[Block] = []
        for raw in re.split(r"\n\s*\n", text):
            for segment in _split_block_on_headings(raw):
                cleaned = _strip_noise_lines(segment)
                if cleaned:
                    blocks.append(Block(cleaned, _classify_block(cleaned)))
        return blocks


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
        self._separators = separators or ["\n\n", "\n", " ", ""]

    def split_text(self, text: str) -> List[str]:
        final_chunks = []

        separator = self._separators[-1]
        for _s in self._separators:
            if _s == "":
                separator = _s
                break
            if _s in text:
                separator = _s
                break

        if separator:
            splits = text.split(separator)
        else:
            splits = list(text)

        _good_splits = []
        _separator = separator if separator else ""

        for s in splits:
            if self._length_function(s) < self._chunk_size:
                _good_splits.append(s)
            else:
                if _good_splits:
                    final_chunks.extend(self._merge_splits(_good_splits, _separator))
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
            final_chunks.extend(self._merge_splits(_good_splits, _separator))

        return final_chunks

    def _merge_splits(self, splits: List[str], separator: str) -> List[str]:
        separator_len = self._length_function(separator)
        docs = []
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
            separators=["\n\n", "\n", ". ", " ", ""],
            length_function=len,
        )

    def split_text(self, text: Optional[str]) -> List[str]:
        if not text:
            return []
        blocks = OcrMarkdownParser().parse(text)
        if not self._has_document_structure(blocks):
            cleaned_text = _BLOCK_SEPARATOR.join(
                block.text for block in blocks if block.kind != "meta_noise"
            )
            return self._merge_undersized(
                [c for c in self.text_splitter.split_text(cleaned_text) if c.strip()]
            )
        return self.chunk(blocks)

    def chunk(self, blocks: List[Block]) -> List[str]:
        """Pack a parsed block stream into embedding-sized chunks."""
        content: List[list] = []
        footnotes: List[tuple[int, str, str]] = []
        for index, block in enumerate(self._filter_retrievable_blocks(blocks)):
            if block.kind == "footnote":
                for marker, note in self._split_footnote_entries(block.text):
                    footnotes.append((index, marker, note))
            else:
                content.append([index, block.kind, block.text])

        if footnotes:
            self._attach_footnotes_to_blocks(content, footnotes)
        return self._pack_adaptive(content)

    def chunk_book_sections(
        self,
        pages: Sequence[Any],
        leaf_sections: Optional[Sequence[Any]] = None,
    ) -> List[SectionChunk]:
        """Pack each leaf `BookSection` independently into `SectionChunk` rows.

        1. Page-local footnote binding (`① ② ③`, `[1]`, `(1)`) before cross-page joining.
        2. Cross-page `'prose'` stitching when page `p` ends with a hyphen or lacks
           terminal sentence punctuation (`'verse'`, `'table'`, `'heading'` never stitch).
        3. Page-provenance adaptive packing (`1500` / `200` / `350` / `4000`) with
           unprefixed `Chunk.text`, inherited `section_id`, and `sha256` `text_hash`.
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
        from app.services.book_structure_service import (
            _detect_repeated_running_headers,
            close_span_before_next,
        )

        running_headers = _detect_repeated_running_headers(ordered_pages)
        parsed_by_page = {
            _p_num(p): parse_page_blocks(
                _p_text(p),
                is_toc=False,
                repeated_running_headers=running_headers,
            )
            for p in ordered_pages
        }

        raw_input_sections: List[Any] = list(leaf_sections or [])
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
            # Slice any parent chapter down to its own preamble/intro before its first child
            # using the shared `close_span_before_next` rule (which ignores meta_noise).
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
            # Each unit in `section_units` is `[kind, text, start_page, end_page]`
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
                page_footnotes: List[tuple[int, str, str]] = []
                for local_idx, blk in enumerate(sliced):
                    if blk.kind == "footnote":
                        for marker, note in self._split_footnote_entries(blk.raw_text):
                            page_footnotes.append((local_idx, marker, note))
                    else:
                        page_content.append([local_idx, blk.kind, blk.raw_text])

                if page_footnotes:
                    self._attach_footnotes_to_blocks(page_content, page_footnotes)

                # Step 2: Cross-page prose stitching against trailing block of pnum - 1
                for idx_in_page, (_, kind, text_val) in enumerate(page_content):
                    if (
                        idx_in_page == 0
                        and section_units
                        and section_units[-1][0] == "prose"
                        and kind == "prose"
                        and int(section_units[-1][3]) == pnum - 1
                        and _should_stitch_cross_page_prose(
                            section_units[-1][1], text_val
                        )
                    ):
                        section_units[-1][1] = _stitch_cross_page_prose_text(
                            section_units[-1][1], text_val
                        )
                        section_units[-1][3] = pnum
                    else:
                        section_units.append([kind, text_val, pnum, pnum])

            if not section_units:
                continue

            # Step 3: Adaptive packing with (start_page, end_page) provenance
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
            final_chunks.append(
                SectionChunk(
                    page_number=c_start,
                    end_page_number=max(c_start, c_end),
                    chunk_index=c_idx,
                    section_id=sec_id,
                    text=chunk_text,
                    text_hash=compute_chunk_text_hash(chunk_text),
                )
            )
        return final_chunks

    def _pack_adaptive_with_pages(
        self, units: List[list]
    ) -> List[tuple[str, int, int]]:
        """Pack `[kind, text, start_page, end_page]` units into `(text, start_page, end_page)` chunks."""
        chunks: List[tuple[str, int, int]] = []
        # buffer items: (kind, text, start_page, end_page)
        buffer: List[tuple[str, str, int, int]] = []

        def buffer_text() -> str:
            return _BLOCK_SEPARATOR.join(item[1] for item in buffer)

        def flush(carry_overlap: bool) -> None:
            nonlocal buffer
            if not buffer:
                return
            b_start = min(item[2] for item in buffer)
            b_end = max(item[3] for item in buffer)
            for piece in self._safety_split(buffer_text()):
                if piece.strip():
                    chunks.append((piece, b_start, b_end))
            buffer = self._tail_overlap_units(buffer) if carry_overlap else []

        for kind, text, s_page, e_page in units:
            if (
                kind == "heading"
                and buffer
                and not all(item[0] == "heading" for item in buffer)
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

            buffer.append((kind, text, int(s_page), int(e_page)))

        flush(carry_overlap=False)

        # Merge undersized chunks backward within the same section while propagating page spans
        merged: List[tuple[str, int, int]] = []
        for text, s_page, e_page in chunks:
            if (
                merged
                and len(text) < self.min_chunk_size
                and not self._starts_with_heading(text)
                and len(merged[-1][0]) + len(_BLOCK_SEPARATOR) + len(text)
                <= self.max_chunk_size
            ):
                prev_text, prev_s, prev_e = merged[-1]
                merged[-1] = (
                    prev_text + _BLOCK_SEPARATOR + text,
                    min(prev_s, s_page),
                    max(prev_e, e_page),
                )
            else:
                merged.append((text, s_page, e_page))
        return merged

    def _tail_overlap_units(
        self, buffer: List[tuple[str, str, int, int]]
    ) -> List[tuple[str, str, int, int]]:
        if self.chunk_overlap <= 0:
            return []
        overlap: List[tuple[str, str, int, int]] = []
        total = 0
        for kind, text, s_page, e_page in reversed(buffer):
            if kind == "heading" or _classify_block(text) == "heading":
                break
            separator_len = len(_BLOCK_SEPARATOR) if overlap else 0
            block_len = len(text) + separator_len
            if total + block_len > self.chunk_overlap:
                break
            overlap.insert(0, (kind, text, s_page, e_page))
            total += block_len
        return overlap

    def _attach_footnotes_to_blocks(
        self, content: List[list], footnotes: List[tuple[int, str, str]]
    ) -> None:
        """Merge each footnote into the paragraph that references it on the same page."""
        for position, marker, note in footnotes:
            target: Optional[list] = None
            for item in content:
                if item[0] >= position:
                    break
                if (
                    marker in item[2]
                    or f"[{marker}]" in item[2]
                    or f"({marker})" in item[2]
                ):
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
        buffer: List[tuple[int, str]] = []

        def buffer_text() -> str:
            return _BLOCK_SEPARATOR.join(text for _, text in buffer)

        def flush(carry_overlap: bool) -> None:
            nonlocal buffer
            if not buffer:
                return
            chunks.extend(self._safety_split(buffer_text()))
            buffer = self._tail_overlap_pairs(buffer) if carry_overlap else []

        for index, kind, text in content:
            texts = [item[1] for item in buffer]
            if kind == "heading" and buffer and not self._only_headings(texts):
                flush(carry_overlap=False)

            current_len = len(buffer_text())
            addition = len(text) + (len(_BLOCK_SEPARATOR) if buffer else 0)
            if (
                buffer
                and current_len + addition > self.target_size
                and current_len >= self.min_chunk_size
            ):
                flush(carry_overlap=True)

            buffer.append((index, text))

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

    def _split_footnote_entries(self, block: str) -> List[tuple[str, str]]:
        entries: List[tuple[str, str]] = []
        marker: Optional[str] = None
        lines: List[str] = []
        for raw_line in block.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line[0] in _FOOTNOTE_MARKERS:
                if marker is not None:
                    entries.append((marker, "\n".join(lines).strip()))
                marker = line[0]
                lines = [line]
                continue
            parsed_fn = parse_footnote_line(line)
            if parsed_fn is not None:
                if marker is not None:
                    entries.append((marker, "\n".join(lines).strip()))
                marker = parsed_fn[0]
                lines = [line]
            elif marker is not None:
                lines.append(line)
        if marker is not None:
            entries.append((marker, "\n".join(lines).strip()))
        return entries

    def _has_document_structure(self, blocks: List[Block]) -> bool:
        return any(
            block.kind in {"heading", "toc", "table", "footnote", "verse"}
            for block in blocks
        )

    def _filter_retrievable_blocks(self, blocks: List[Block]) -> List[Block]:
        """Drop TOC blocks (and following TOC-entry tables/lists) and meta_noise blocks,
        while retaining real content tables, prose, verse, headings, and footnotes."""
        filtered = []
        skipping_toc = False
        for block in blocks:
            if block.kind == "meta_noise":
                continue
            if block.kind == "toc":
                skipping_toc = True
                continue
            if skipping_toc:
                if block.kind in {"table", "body", "prose"} and _looks_like_toc_entries(
                    block.text
                ):
                    continue
                skipping_toc = False
            filtered.append(block)
        return filtered

    def _tail_overlap_pairs(
        self, buffer: List[tuple[int, str]]
    ) -> List[tuple[int, str]]:
        if self.chunk_overlap <= 0:
            return []

        overlap: List[tuple[int, str]] = []
        total = 0
        for index, block in reversed(buffer):
            if _classify_block(block) == "heading":
                break
            separator_len = len(_BLOCK_SEPARATOR) if overlap else 0
            block_len = len(block) + separator_len
            if total + block_len > self.chunk_overlap:
                break
            overlap.insert(0, (index, block))
            total += block_len
        return overlap

    def _only_headings(self, blocks: List[str]) -> bool:
        return all(_classify_block(block) == "heading" for block in blocks)

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
