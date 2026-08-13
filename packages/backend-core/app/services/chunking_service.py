import re
from dataclasses import dataclass
from typing import List, Optional, Callable
from app.core.config import settings


_BLOCK_SEPARATOR = "\n\n"
# Hard character ceiling for a single chunk, sized to stay under the embedding
# model's 2048-token input limit even for Uyghur Arabic script (~1.3 chars/token
# conservative). Only atomic units larger than this are force-split.
_EMBED_SAFE_CHARS = 2600
_MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+\S")
# Structural noise that must never become its own chunk: HTML page comments
# (e.g. "<!-- page 3 -->") and horizontal rules ("---", "***", "___").
_NOISE_LINE_RE = re.compile(r"^(?:<!--.*-->|-{3,}|\*{3,}|_{3,})$")
# OCR page header/footer markers (from the OCR prompt), either on their own line
# ("[Footer] 1") or glued to the end of a content line ("...خانىسى.[Footer] 3"). The
# marker and everything after it to end of line is page furniture, not
# retrievable content, so it is stripped wherever it appears.
_OCR_HEADER_FOOTER_RE = re.compile(r"\s*\[(?:Header|Footer)\].*", re.IGNORECASE)
_UYGHUR_HEADING_RE = re.compile(r"^(?:.+\s+باب|(?:.+\s+.)?مۇقەددىمە|خاتىمە)\s*$")
_FOOTNOTE_MARKERS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
_FOOTNOTE_RE = re.compile(rf"^[{_FOOTNOTE_MARKERS}]\s+")
# A table-of-contents entry: a bullet/number marker followed shortly by a page
# number ("* 090 ..."), or prose trailing off into a dot-leader run ending in a
# page number ("... باب ..................... 15"). Used to tell a real TOC
# entry apart from ordinary body prose that happens to follow one, so the
# TOC-skip below stops at the first block that isn't actually more TOC.
_TOC_ENTRY_RE = re.compile(
    r"^(?:[-*•]|\d+[.)])\s*\d{1,4}\b|.*[.·•∙⋅]{3,}\s*\d{1,4}\s*$"
)


@dataclass(frozen=True)
class Block:
    """A single logical unit of a document -- a heading, body paragraph,
    footnote, table, or table-of-contents entry (see ``kind``).

    ``Block`` is the contract between parsing and chunking: ``OcrMarkdownParser``
    turns a source string into a list of ``Block``s, and ``ChunkingService``
    packs them into embedding-sized chunks without inspecting the source markdown.
    """

    text: str
    kind: str


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
        return "body"
    if any("مۇندەرىجە" in line for line in lines):
        return "toc"
    if _is_table_block(lines):
        return "table"
    if len(lines) <= 2 and any(_is_heading_line(line) for line in lines):
        return "heading"
    if _FOOTNOTE_RE.match(lines[0]):
        return "footnote"
    return "body"


def _split_block_on_headings(block: str) -> List[str]:
    """Split a raw block so each markdown heading line stands alone.

    OCR/markdown output often stacks a heading and its body (or several
    headings) with only single newlines, which would hide the heading from
    structure detection. Emitting each heading line as its own segment lets
    the heading be recognized and lets body text pack separately.
    """
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


class OcrMarkdownParser:
    """Parser for OCR-pipeline markdown (headings, paragraphs, pipe tables).

    Blocks are separated by blank lines; each markdown heading is split onto its
    own segment so it is recognized even when OCR stacked it against its body
    with single newlines. Per-line structural noise (page comments, horizontal
    rules) is stripped.
    """

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

        # Split text using the first separator that works
        separator = self._separators[-1]
        for _s in self._separators:
            if _s == "":
                separator = _s
                break
            if _s in text:
                separator = _s
                break

        # Now split
        if separator:
            splits = text.split(separator)
        else:
            splits = list(text)  # Split by char

        # Now merge
        _good_splits = []
        _separator = separator if separator else ""

        for s in splits:
            if self._length_function(s) < self._chunk_size:
                _good_splits.append(s)
            else:
                if _good_splits:
                    final_chunks.extend(self._merge_splits(_good_splits, _separator))
                    _good_splits = []
                # Recursively split long chunks
                if not self._separators:
                    final_chunks.append(s[: self._chunk_size])  # fallback
                else:
                    # Find next separator index
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
                        # logical end
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
                if total > self._chunk_size:
                    # Warning: chunk larger than size
                    pass
                if current_doc:
                    doc = separator.join(current_doc)
                    if doc:
                        docs.append(doc)

                    # Handle overlap
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
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        min_chunk_size: Optional[int] = None,
        max_chunk_size: Optional[int] = None,
    ):
        # `chunk_size` is the soft target: packing of multiple paragraphs closes
        # a chunk once it passes this size at a paragraph boundary. Individual
        # paragraphs (with their attached footnotes) are atomic and are never
        # split below `max_chunk_size` -- so a single large paragraph yields one
        # large chunk, while multi-paragraph regions yield several smaller ones.
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = (
            min_chunk_size if min_chunk_size is not None else max(1, chunk_size // 3)
        )
        # Hard ceiling: only an atomic unit larger than this is force-split, to
        # protect the embedding model's token limit. It is an absolute char
        # budget (not a multiple of the target) so that a large paragraph plus
        # its footnotes still stays whole even when the target is small.
        self.max_chunk_size = (
            max_chunk_size if max_chunk_size is not None else _EMBED_SAFE_CHARS
        )
        # The soft target can never exceed the hard ceiling.
        self.target_size = min(chunk_size, self.max_chunk_size)
        # Sized to the (ceiling-bounded) target so the plain-text fallback and
        # the safety split can never emit a chunk larger than the hard ceiling,
        # even when `chunk_size` is configured above it.
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
        # Fall back to plain splitting when the page carries no structure. The
        # fallback still runs on the parsed/cleaned block text (not the raw
        # input) so OCR noise stripping and heading segmentation always apply,
        # even for a page whose blocks are all plain body paragraphs.
        if not self._has_document_structure(blocks):
            cleaned_text = _BLOCK_SEPARATOR.join(block.text for block in blocks)
            return self._merge_undersized(
                [c for c in self.text_splitter.split_text(cleaned_text) if c.strip()]
            )
        return self.chunk(blocks)

    def chunk(self, blocks: List[Block]) -> List[str]:
        """Pack a parsed block stream into embedding-sized chunks.

        This half is format-agnostic: it inspects only ``Block.kind`` and text,
        never the source markdown. All markdown-specific parsing lives in
        ``OcrMarkdownParser``.
        """
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

    def _attach_footnotes_to_blocks(
        self, content: List[list], footnotes: List[tuple[int, str, str]]
    ) -> None:
        """Merge each footnote into the paragraph that references it.

        The referencing paragraph is the latest content block before the
        footnote (in reading order) whose text contains the matching inline
        marker. Merging at the paragraph level makes the paragraph + its
        footnotes a single atomic unit that packing will never split apart, and
        keeps matching page-local (a marker reused on a later page binds to that
        page's paragraph).
        """

        for position, marker, note in footnotes:
            target: Optional[list] = None
            for item in content:
                if item[0] >= position:
                    break
                if marker in item[2]:
                    target = item
            if target is None:
                preceding = [item for item in content if item[0] < position]
                target = (
                    preceding[-1] if preceding else (content[-1] if content else None)
                )
            if target is not None:
                target[2] = f"{target[2]}{_BLOCK_SEPARATOR}{note}"

    def _pack_adaptive(self, content: List[list]) -> List[str]:
        """Pack atomic paragraphs into chunks with structure-driven sizing.

        A chunk grows by whole paragraphs until it passes `target_size` at a
        paragraph boundary (and is at least `min_chunk_size`), then closes.
        Paragraphs are never split; a paragraph larger than the target simply
        becomes its own (larger) chunk. Headings always start a new chunk.
        """

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
        """Fold a below-minimum chunk into the previous one.

        A short trailing paragraph (e.g. a one-line sentence left after a large
        atomic unit) is noise to embed on its own. It is merged back unless it
        begins with a heading (a new section must start its own chunk) or the
        merge would breach the hard ceiling.
        """

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
            if line and line[0] in _FOOTNOTE_MARKERS:
                if marker is not None:
                    entries.append((marker, "\n".join(lines).strip()))
                marker = line[0]
                lines = [line]
            elif marker is not None:
                lines.append(line)
        if marker is not None:
            entries.append((marker, "\n".join(lines).strip()))
        return entries

    def _has_document_structure(self, blocks: List[Block]) -> bool:
        return any(
            block.kind in {"heading", "toc", "table", "footnote"} for block in blocks
        )

    def _filter_retrievable_blocks(self, blocks: List[Block]) -> List[Block]:
        """Drop TOC blocks and the entry list that follows them.

        A block classified "toc" starts the skip. It only continues through
        subsequent "table"/"body" blocks that still look like TOC entries
        (``_looks_like_toc_entries``) -- the first block that doesn't (real
        prose resuming with no heading in between) ends the skip and is kept,
        so a TOC directly followed by un-headinged content on the same page
        doesn't get silently dropped along with it.
        """
        filtered = []
        skipping_toc = False
        for block in blocks:
            if block.kind == "toc":
                skipping_toc = True
                continue
            if skipping_toc:
                if block.kind in {"table", "body"} and _looks_like_toc_entries(
                    block.text
                ):
                    continue
                skipping_toc = False
            if block.kind == "table":
                continue
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
            # Never carry a block that alone exceeds the overlap budget -- that
            # would duplicate a whole (possibly large) paragraph into the next
            # chunk instead of a small trailing context window.
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
