"""Which words end a printed line with a hyphen, read from the page image."""

from __future__ import annotations

import re
import threading
from typing import Any

from bs4 import BeautifulSoup
from PIL import Image

from engine.text_cleanup import normalize_uyghur_chars

_LINE_END_FRACTION = 0.6
_MIN_LINE_WIDTH_FRACTION = 0.25
_HYPHENS = "-\u2010\u2011\u2012\u2013\u2014\u00ad\u0640"
_ARABIC_HEH = "\u0647"
_UYGHUR_AE = "\u06d5"
_TRAILING_HYPHEN_RE = re.compile(rf"[\s{re.escape(_HYPHENS)}]+$")

_detector: Any = None
_detector_lock = threading.Lock()


def get_line_detector() -> Any:
    """Return the line detector if available, or None."""
    global _detector
    with _detector_lock:
        if _detector is None:
            try:
                from surya.detection import DetectionPredictor

                _detector = DetectionPredictor.local()
            except ImportError:
                _detector = None
    return _detector


def read_line_end_words(image: Image.Image, detector: Any, recognizer: Any) -> set[str]:
    """Return the normalized words that end a printed line with a hyphen."""
    if detector is None or recognizer is None:
        return set()

    try:
        from surya.layout.schema import LayoutBox, LayoutResult
    except ImportError:
        from dataclasses import dataclass, field

        @dataclass
        class LayoutBox:
            polygon: list[float]
            label: str = "Text"
            raw_label: str = "Text"
            position: int = 0
            count: int = 60
            bbox: list[float] = field(init=False)

            def __post_init__(self):
                self.bbox = [
                    self.polygon[0],
                    self.polygon[1],
                    self.polygon[2],
                    self.polygon[3],
                ]

        @dataclass
        class LayoutResult:
            bboxes: list[LayoutBox]
            image_bbox: list[float]

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
