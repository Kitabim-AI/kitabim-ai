"""Which words end a printed line with a hyphen, read from the page image.

Surya's full-page OCR reflows each block into running text, so a line-end
hyphen ("ھەز-" / "رىتى" on the next line) comes back as "ھەز - رىتى" and can't
be told apart from a real pair or a dash. Surya's text-line detector still sees
the printed lines: reading just the end of each line (its left edge, since
Uyghur runs right to left) tells us which words were split by a line break.
"""

from __future__ import annotations

import re
import threading
from typing import Any

from bs4 import BeautifulSoup
from PIL import Image

from engine.text_cleanup import normalize_uyghur_chars

# Part of each line, from its left (end) edge, sent for recognition. Narrower
# strips push the recognizer toward Arabic/Persian letter forms and the whole
# line makes it drop the end; 0.6 read the most line ends correctly on a test
# page. The cut-off first word is ignored.
_LINE_END_FRACTION = 0.6
# Lines narrower than this share of the widest line (page numbers, headers,
# short last lines of a paragraph) can't end with a split word.
_MIN_LINE_WIDTH_FRACTION = 0.25
_HYPHENS = "-\u2010\u2011\u2012\u2013\u2014\u00ad\u0640"
# Arabic heh (U+0647) never occurs in Uyghur text; on a line-end crop it is
# the recognizer's reading of Uyghur ae (U+06D5), e.g. "خه-" for "خە-".
_ARABIC_HEH = "\u0647"
_UYGHUR_AE = "\u06d5"
_TRAILING_HYPHEN_RE = re.compile(rf"[\s{re.escape(_HYPHENS)}]+$")

_detector: Any = None
_detector_lock = threading.Lock()


def get_line_detector() -> Any:
    """Return the process-wide Surya text-line detector, loading it on first use."""
    global _detector
    with _detector_lock:
        if _detector is None:
            from surya.detection import DetectionPredictor

            _detector = DetectionPredictor.local()
    return _detector


def read_line_end_words(image: Image.Image, detector: Any, recognizer: Any) -> set[str]:
    """Return the normalized words that end a printed line with a hyphen."""
    from surya.layout.schema import LayoutBox, LayoutResult

    lines = detector([image])[0].bboxes
    if not lines:
        return set()
    widest = max(line.bbox[2] - line.bbox[0] for line in lines)

    boxes: list[LayoutBox] = []
    for line in sorted(lines, key=lambda b: b.bbox[1]):
        x0, y0, x1, y1 = line.bbox
        if x1 - x0 < _MIN_LINE_WIDTH_FRACTION * widest:
            continue
        boxes.append(
            LayoutBox(
                polygon=[x0, y0, x0 + _LINE_END_FRACTION * (x1 - x0), y1],
                label="Text",
                raw_label="Text",
                position=len(boxes),
                count=60,
            )
        )
    if not boxes:
        return set()

    w, h = image.size
    layout = LayoutResult(bboxes=boxes, image_bbox=[0, 0, float(w), float(h)])
    blocks = recognizer([image], [layout], full_page=False)[0].blocks

    words: set[str] = set()
    for block in blocks:
        if block.error or not block.html:
            continue
        line_end = BeautifulSoup(block.html, "html.parser").get_text(" ", strip=True)
        body = _TRAILING_HYPHEN_RE.sub("", line_end)
        tail = line_end[len(body) :]
        if not body or not any(c in _HYPHENS for c in tail):
            continue
        last = body.split()[-1].replace(_ARABIC_HEH, _UYGHUR_AE)
        words.add(normalize_uyghur_chars(last))
    return words
