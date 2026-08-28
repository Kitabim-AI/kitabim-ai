from __future__ import annotations

import re
import statistics
from typing import List, Tuple
from app.utils.text import clean_uyghur_text, is_toc_page

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
        if num_matches:
            page_num = num_matches[-1]
            text_without_num = page_num_extractor.sub("", clean_line)
            text_without_num = re.sub(r"[\|\.·\-_…]{2,}", " ", text_without_num)
            text_without_num = re.sub(r"\|", " ", text_without_num)
            text_without_num = re.sub(r"\s+", " ", text_without_num).strip()

            if text_without_num:
                current_title_parts.append(text_without_num)

            full_title = " ".join(current_title_parts).strip()
            if full_title:
                formatted.append(f"| {page_num} | {full_title} |")
            else:
                formatted.append(f"| {page_num} |")
            current_title_parts = []
        else:
            current_title_parts.append(clean_line)

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

    lines = cluster_lines(body_detections)
    detected_lines = detect_headings(lines, heading_size_ratio, page_width)

    raw_text = "\n".join(detected_lines)
    if is_toc_page(raw_text):
        detected_lines = format_toc_lines(detected_lines)
        raw_text = "\n".join(detected_lines)

    cleaned = clean_ocr_artifacts(raw_text)
    return clean_uyghur_text(cleaned)
