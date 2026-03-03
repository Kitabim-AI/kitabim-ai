"""Service for extracting text and cover from .docx files."""
from __future__ import annotations

import logging
from pathlib import Path

from app.utils.text import normalize_uyghur_chars

logger = logging.getLogger(__name__)

_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _is_heading_para(para_el) -> bool:
    """
    Return True if the paragraph looks like a section heading.
    Heuristic: every run in the paragraph has bold enabled (w:b),
    and the total text is short enough to be a title (< 200 chars).
    """
    runs = para_el.findall(f"{{{_NS}}}r")
    if not runs:
        return False
    full_text = "".join(
        (t.text or "")
        for r in runs
        for t in r.findall(f"{{{_NS}}}t")
    )
    if not full_text.strip() or len(full_text.strip()) >= 200:
        return False
    return all(r.find(f".//{{{_NS}}}b") is not None for r in runs)


def extract_docx_pages(path: Path) -> list[str]:
    """
    Split a .docx file into pages using lastRenderedPageBreak markers.

    Splits at run level (not paragraph level) to correctly handle paragraphs
    that span multiple pages (i.e. multiple lrpb markers in one paragraph).
    Bold short paragraphs are prefixed with '## ' so the chunking service
    can treat them as section boundaries and the viewer shows them as headings.
    Falls back to fixed 3000-char blocks if no markers are found.
    """
    from docx import Document

    doc = Document(path)

    pages: list[str] = []
    current_page: list[str] = []

    for para in doc.paragraphs:
        is_heading = _is_heading_para(para._p)
        para_chunks: list[list[str]] = [[]]

        for run in para._p.findall(f"{{{_NS}}}r"):
            lrpb = run.find(f"{{{_NS}}}lastRenderedPageBreak")
            t = run.find(f"{{{_NS}}}t")
            text = (t.text or "") if t is not None else ""
            if lrpb is not None:
                para_chunks.append([text])
            else:
                para_chunks[-1].append(text)

        for idx, chunk in enumerate(para_chunks):
            chunk_text = "".join(chunk).strip()
            if not chunk_text:
                if idx > 0:
                    # still flush the page even if this chunk is empty
                    pages.append("\n".join(current_page))
                    current_page = []
                continue

            if idx > 0:
                # page break occurred before this chunk
                pages.append("\n".join(current_page))
                current_page = []

            # Mark headings so chunker & viewer recognise them
            if is_heading:
                chunk_text = f"## {chunk_text}"

            current_page.append(chunk_text)

    if current_page:
        pages.append("\n".join(current_page))

    # Fallback: no page break markers found, split by fixed block size
    if len(pages) <= 1:
        full_text = pages[0] if pages else ""
        block_size = 3000
        pages = [full_text[i:i + block_size] for i in range(0, len(full_text), block_size)]

    result = [normalize_uyghur_chars(p.strip()) for p in pages if p.strip()]
    logger.info("docx_service: extracted %d pages from %s", len(result), path.name)
    return result


def extract_docx_cover(docx_path: Path, cover_path: Path) -> bool:
    """
    Extract the first inline image from a .docx file and save it as cover_path.
    Returns True on success, False if no image found or on error.
    """
    try:
        from docx import Document
        doc = Document(docx_path)
        for rel in doc.part.rels.values():
            if "image" in rel.reltype:
                with open(cover_path, "wb") as f:
                    f.write(rel.target_part.blob)
                return True
    except Exception as e:
        logger.warning("docx_service: failed to extract cover path=%s error=%s", docx_path, e)
    return False
