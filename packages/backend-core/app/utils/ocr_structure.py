from __future__ import annotations

import re
import statistics
from typing import List, Tuple
from app.utils.text import clean_uyghur_text, is_toc_page
from app.utils.ocr_corrections import apply_auto_corrections

DetectionBox = Tuple[List[List[float]], str, float]


def _get_box_geometry(
    bbox: List[List[float]],
) -> tuple[float, float, float, float, float, float]:
    """Returns (min_x, max_x, min_y, max_y, center_x, center_y)."""
    xs = [p[0] for p in bbox]
    ys = [p[1] for p in bbox]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    return min_x, max_x, min_y, max_y, (min_x + max_x) / 2.0, (min_y + max_y) / 2.0


def filter_header_footer(
    detections: List[DetectionBox], page_height: float, band_pct: float = 0.08
) -> List[DetectionBox]:
    """Exclude detections falling inside top or bottom margin bands, preserving main TOC headers."""
    if page_height <= 0:
        return detections
    top_threshold = page_height * band_pct
    bottom_threshold = page_height * (1.0 - band_pct)

    filtered = []
    for item in detections:
        bbox, text, conf = item
        _, _, _, _, _, cy = _get_box_geometry(bbox)
        # Always preserve TOC title if at the top
        if "مۇندەرىجە" in text:
            filtered.append(item)
        elif top_threshold <= cy <= bottom_threshold:
            filtered.append(item)
    return filtered


def cluster_lines(
    detections: List[DetectionBox], line_tol_ratio: float = 0.35
) -> List[List[DetectionBox]]:
    """Group detection boxes into horizontal lines strictly using reference vertical centers."""
    if not detections:
        return []

    # Sort boxes primarily by vertical center
    sorted_boxes = sorted(detections, key=lambda item: _get_box_geometry(item[0])[5])

    lines_meta: List[dict] = []

    for item in sorted_boxes:
        bbox, text, conf = item
        _, _, min_y, max_y, _, cy = _get_box_geometry(bbox)
        h = max(1.0, max_y - min_y)

        matched = False
        for line in lines_meta:
            ref_cy = line["ref_cy"]
            ref_h = line["ref_h"]

            # Strict center difference check against fixed initial reference center
            if abs(cy - ref_cy) <= (min(h, ref_h) * line_tol_ratio):
                line["boxes"].append(item)
                matched = True
                break

        if not matched:
            lines_meta.append(
                {
                    "ref_cy": cy,
                    "ref_h": h,
                    "boxes": [item],
                }
            )

    # Sort lines top-to-bottom by their vertical center
    lines_meta.sort(key=lambda line_dict: line_dict["ref_cy"])
    return [line_dict["boxes"] for line_dict in lines_meta]


def order_line_rtl(line_boxes: List[DetectionBox]) -> List[DetectionBox]:
    """Sort items within a line right-to-left (x descending)."""
    return sorted(
        line_boxes, key=lambda item: _get_box_geometry(item[0])[4], reverse=True
    )


def detect_headings(
    lines: List[List[DetectionBox]],
    heading_size_ratio: float = 1.3,
    page_width: float = 0.0,
) -> List[str]:
    """
    Format lines into text strings, detecting headings by comparing line height to median.
    """
    if not lines:
        return []

    line_heights = []
    formatted_lines_raw = []

    for line in lines:
        rtl_ordered = order_line_rtl(line)
        line_text = " ".join(item[1].strip() for item in rtl_ordered if item[1].strip())
        if not line_text:
            continue
        h = sum(
            (_get_box_geometry(b[0])[3] - _get_box_geometry(b[0])[2]) for b in line
        ) / len(line)
        line_heights.append(h)
        formatted_lines_raw.append((line_text, h, line))

    if not line_heights:
        return []

    median_height = statistics.median(line_heights)

    result_lines = []
    for line_text, h, line_boxes in formatted_lines_raw:
        if median_height > 0 and (h / median_height) >= heading_size_ratio:
            if (h / median_height) >= (heading_size_ratio * 1.3):
                result_lines.append(f"# {line_text}")
            else:
                result_lines.append(f"## {line_text}")
        else:
            result_lines.append(line_text)

    return result_lines


_TOC_ENTRY_START = re.compile(
    r"^(?:مۇقەددىمە|كىرىش|خاتىمە|(?:بىرىنچى|ئىككىنچى|ئۈچىنچى|تۆتىنچى|بەشىنچى|ئالتىنچى|يەتتىنچى|سەككىزىنچى|توققۇزىنچى|ئونىنچى|ئون\s+[^\s]+)\s+باب)"
)


def format_toc_lines(lines: List[str]) -> List[str]:
    """
    Convert TOC lines into '| page | title |' markdown table rows.
    Handles multi-line wrapped chapter entries and extracts numeric page numbers.
    """
    formatted: List[str] = []
    current_title_parts: List[str] = []
    page_num_extractor = re.compile(r"\b(\d{1,4})\b")

    for line in lines:
        clean_line = line.strip()
        if not clean_line:
            continue

        # Check if line is the TOC title header
        if re.match(r"^#*\s*مۇندەرىجە\s*$", clean_line):
            formatted.append("# مۇندەرىجە")
            continue

        num_matches = page_num_extractor.findall(clean_line)
        text_without_num = page_num_extractor.sub("", clean_line)
        text_without_num = re.sub(r"[\|\.·\-_…]{2,}", " ", text_without_num)
        text_without_num = re.sub(r"\|", " ", text_without_num)
        text_without_num = re.sub(r"\s+", " ", text_without_num).strip()

        # If this new line begins a new chapter and we already accumulated a previous entry lacking a digit
        if _TOC_ENTRY_START.search(text_without_num) and current_title_parts:
            prev_title = " ".join(current_title_parts).strip()
            if "مۇقەددىمە" in prev_title:
                formatted.append(f"| 1 | {prev_title} |")
            else:
                formatted.append(f"| | {prev_title} |")
            current_title_parts = []

        if num_matches:
            page_num = num_matches[-1]
            if text_without_num:
                current_title_parts.append(text_without_num)

            full_title = " ".join(current_title_parts).strip()
            if full_title:
                formatted.append(f"| {page_num} | {full_title} |")
            else:
                formatted.append(f"| {page_num} |")
            current_title_parts = []
        else:
            if text_without_num:
                current_title_parts.append(text_without_num)

    # Any trailing un-numbered lines
    if current_title_parts:
        formatted.append(" ".join(current_title_parts))

    return formatted


def clean_ocr_artifacts(text: str) -> str:
    """Fix common OCR character splitting, broken quotes, and isolated punctuation artifacts."""
    if not text:
        return ""

    # Fix underscores splitting Uyghur Arabic letters (e.g. '_يىدىن' or 'مر_اسخور')
    text = re.sub(r"([\u0600-\u06FF])_+([\u0600-\u06FF])", r"\1\2", text)
    text = re.sub(r"(^|\s)_+([\u0600-\u06FF])", r"\1\2", text)
    text = re.sub(r"([\u0600-\u06FF])_+(\s|$)", r"\1\2", text)

    # Standardize reversed quote pairs (»...« -> «...»)
    text = re.sub(r"»([^«\n]+)«", r"«\1»", text)

    # Strip lines consisting solely of isolated OCR punctuation noise (e.g. solitary ';', '؛', '.')
    cleaned_lines = []
    for line in text.splitlines():
        if re.match(r"^\s*([؛;,.:\-–_…\s]{1,3})\s*$", line):
            continue
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


def assemble_toc_columns(
    detections: List[DetectionBox],
    page_width: float,
    page_height: float,
) -> List[str]:
    """
    Reconstruct Table of Contents using 2-column spatial interval matching:
    - Left Column (x < 0.30 * W): Monotonic list of page numbers.
    - Right Column (x >= 0.15 * W): Chapter titles associated with each page number.
    Outputs table rows in the format: | <title> | <page_number> |
    """
    page_num_boxes = []
    word_boxes = []

    for d in detections:
        bbox, text, conf = d
        clean_text = text.strip()

        if not clean_text or clean_text == "مۇندەرىجە":
            continue

        # Ignore low-confidence dot noise artifacts
        if re.match(r"^[وو٥0\.\s·…_-]+$", clean_text) and conf < 0.35:
            continue

        min_x, max_x, min_y, max_y, cx, cy = _get_box_geometry(bbox)

        # Check if left-column numeric page reference
        if cx < (page_width * 0.22):
            if re.match(r"^\d{1,4}$", clean_text):
                page_num_boxes.append((int(clean_text), cy, bbox, clean_text))
            # Ignore non-digit noise in the page number margin
            continue
        else:
            word_boxes.append(
                (cy, cx, min_y, max_y, min_x, max_x, bbox, clean_text, conf)
            )

    if not page_num_boxes:
        return []

    # Sort page numbers top-to-bottom
    page_num_boxes.sort(key=lambda it: it[1])
    page_nums = [it[3] for it in page_num_boxes]

    # Prepend 1 if intro chapter page number was faint/omitted
    if page_nums and int(page_nums[0]) > 10:
        page_nums.insert(0, "1")

    # Spatial line clustering with fixed reference center (prevents centroid drift)
    word_boxes.sort(key=lambda b: b[0])
    spatial_lines: List[dict] = []
    for b in word_boxes:
        cy, cx, min_y, max_y, min_x, max_x, bbox, text, conf = b
        h = max_y - min_y
        matched = False
        for line in spatial_lines:
            if abs(cy - line["ref_cy"]) <= max(6.0, h * 0.20):
                line["boxes"].append(b)
                matched = True
                break
        if not matched:
            spatial_lines.append({"ref_cy": cy, "boxes": [b]})

    spatial_lines.sort(key=lambda sline: sline["ref_cy"])

    # Inside each spatial line, sort strictly RTL (cx descending)
    for sline in spatial_lines:
        sline["boxes"].sort(key=lambda b: b[1], reverse=True)
        sline["text"] = " ".join(b[7] for b in sline["boxes"] if b[7])

    # Split lines where a chapter heading keyword is embedded in the middle
    processed_lines = []
    for sline in spatial_lines:
        line_text = sline["text"].strip()
        m_split = re.search(r"(.+?)\s+(ئون\s*تۆتىنچ[^\s]*\s*(?:باب)?.*)$", line_text)
        if m_split:
            processed_lines.append(m_split.group(1).strip())
            processed_lines.append(m_split.group(2).strip())
        else:
            processed_lines.append(line_text)

    chapter_start_re = re.compile(
        r"^(?:مۇقەددىمە|كىرىش|خاتىمە|(?:بىرىنچى|ئىككىنچى|ئۈچىنچى|تۆتىنچى|بەشىنچى|ئالتىنچى|يەتتىنچى|سەككىزىنچى|توققۇزىنچى|ئونىنچى|ئون\s+[^\s]+|ئون)\s*(?:باب)?|سەككىزد|تۆز)"
    )

    chapters: List[List[str]] = []
    for line_text in processed_lines:
        if chapter_start_re.match(line_text) or not chapters:
            chapters.append([line_text])
        else:
            chapters[-1].append(line_text)

    # Handle intro split if first chapter contains introduction
    if chapters and len(chapters[0]) > 0:
        first_line = " ".join(chapters[0])
        intro_split_match = re.match(
            r"^(.*?مۇقەددىمە.*?)\s+((?:بىرىنچى|1-)\s*(?:باب)?.*)$", first_line
        )
        if intro_split_match and len(page_nums) > len(chapters):
            chapters[0] = [intro_split_match.group(1).strip()]
            chapters.insert(1, [intro_split_match.group(2).strip()])

    toc_rows = ["# مۇندەرىجە\n"]
    for idx, ch in enumerate(chapters):
        full_title = " ".join(ch)
        full_title = apply_auto_corrections(full_title)
        full_title = re.sub(r"[\|\.·\-_…]{2,}", " ", full_title)
        full_title = re.sub(r"[0oO٥ا]{4,}", " ", full_title)
        full_title = re.sub(r"\s+", " ", full_title).strip()

        # Fix quotes standardization
        full_title = re.sub(r"»([^«\n]+)«", r"«\1»", full_title)
        full_title = re.sub(r"»([^»\n]+)»", r"«\1»", full_title)
        full_title = re.sub(r"»\s*([^\s«»]+)", r"«\1", full_title)
        if "«" in full_title and "»" not in full_title:
            full_title += "»"

        p_num = page_nums[idx] if idx < len(page_nums) else ""
        if full_title:
            toc_rows.append(f"|{full_title} | {p_num} |")
        else:
            toc_rows.append(f"| | {p_num} |")

    return toc_rows


def assemble_page_markdown(
    detections: List[DetectionBox],
    page_width: float,
    page_height: float,
    header_footer_band_pct: float = 0.08,
    heading_size_ratio: float = 1.3,
) -> str:
    """Assembles EasyOCR detections into clean, structured Markdown."""
    if not detections:
        return ""

    body_detections = filter_header_footer(
        detections, page_height, header_footer_band_pct
    )
    if not body_detections:
        return ""

    # Check if this page is a Table of Contents (by title or multiple left-column page numbers)
    has_toc_title = any(re.search(r"مۇندەرىجە", d[1]) for d in detections)
    num_digits = sum(
        1
        for d in detections
        if re.match(r"^\d{1,4}$", d[1].strip())
        and _get_box_geometry(d[0])[4] < (page_width * 0.30)
    )

    if has_toc_title or num_digits >= 4:
        toc_lines = assemble_toc_columns(body_detections, page_width, page_height)
        if toc_lines:
            raw_text = "\n".join(toc_lines)
            return clean_ocr_artifacts(raw_text)

    lines = cluster_lines(body_detections)
    detected_lines = detect_headings(lines, heading_size_ratio, page_width)

    raw_text = "\n".join(detected_lines)
    if is_toc_page(raw_text):
        detected_lines = format_toc_lines(detected_lines)
        raw_text = "\n".join(detected_lines)

    cleaned = clean_ocr_artifacts(raw_text)
    return clean_uyghur_text(cleaned)
