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
    """Exclude detections falling inside top or bottom margin bands."""
    if page_height <= 0:
        return detections
    top_threshold = page_height * band_pct
    bottom_threshold = page_height * (1.0 - band_pct)

    filtered = []
    for item in detections:
        bbox, text, conf = item
        _, _, _, _, _, cy = _get_box_geometry(bbox)
        if top_threshold <= cy <= bottom_threshold:
            filtered.append(item)
    return filtered


def cluster_lines(
    detections: List[DetectionBox], line_tol_ratio: float = 0.6
) -> List[List[DetectionBox]]:
    """Group detection boxes into horizontal lines based on overlapping vertical coordinates."""
    if not detections:
        return []

    # Sort boxes primarily by vertical center
    sorted_boxes = sorted(detections, key=lambda it: _get_box_geometry(it[0])[5])

    lines: List[List[DetectionBox]] = []
    current_line: List[DetectionBox] = []
    current_line_y = 0.0
    current_line_h = 0.0

    for item in sorted_boxes:
        bbox, text, conf = item
        _, _, min_y, max_y, _, cy = _get_box_geometry(bbox)
        h = max_y - min_y

        if not current_line:
            current_line.append(item)
            current_line_y = cy
            current_line_h = h
            continue

        tolerance = max(current_line_h, h) * line_tol_ratio
        if abs(cy - current_line_y) <= tolerance:
            current_line.append(item)
            current_line_y = sum(
                _get_box_geometry(b[0])[5] for b in current_line
            ) / len(current_line)
            current_line_h = max(current_line_h, h)
        else:
            lines.append(current_line)
            current_line = [item]
            current_line_y = cy
            current_line_h = h

    if current_line:
        lines.append(current_line)

    return lines


def order_line_rtl(line_boxes: List[DetectionBox]) -> List[DetectionBox]:
    """Sort items within a line right-to-left (x descending)."""
    return sorted(line_boxes, key=lambda it: _get_box_geometry(it[0])[4], reverse=True)


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
    """Convert lines with dot leaders / trailing page numbers into '| title | page |' markdown table rows."""
    dot_pattern = re.compile(r"(\.{3,}|_{3,}|-{3,}|·{3,}|…{2,})")
    formatted = []
    for line in lines:
        if dot_pattern.search(line):
            m = re.search(r"^(.*?)\s*(?:[\.·\-_…]{2,}|\s{3,})\s*(\d+)\s*$", line)
            if m:
                title, page_num = m.group(1).strip(), m.group(2).strip()
                formatted.append(f"| {title} | {page_num} |")
                continue
        formatted.append(line)
    return formatted


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

    return clean_uyghur_text(raw_text)
