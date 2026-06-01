import re
import numpy as np

# Portable Unicode escape range for Arabic/Uyghur character block
# Matches Uyghur letters, dots/leaders, and final page number digits
TOC_LINE_PATTERN = re.compile(r'^[\u0600-\u06FF\s\W]+[\s\.·•∙⋅․﹒｡…_-]+\d{1,4}$')


def calculate_median(values: list[float]) -> float:
    """Calculate median of a list of floats."""
    if not values:
        return 0.0
    return float(np.median(values))


def parse_toc_line(line_text: str) -> str:
    """Convert a ToC line (Title ....... PageNum) to standard Markdown pipe table format."""
    page_num_match = re.search(r'\d+$', line_text)
    if page_num_match:
        page_num = page_num_match.group()
        # Strip trailing dot leaders, spaces, and dashes from the title portion
        title = line_text[:page_num_match.start()].strip(" \t.·•∙⋅․﹒｡_—–-…")
        if title:
            return f"| {title} | {page_num} |"
    return line_text


def detect_poem_block(lines: list[dict]) -> bool:
    """Detect if a block of lines is a poem based on spatial line width uniformity."""
    if len(lines) < 4:
        return False

    widths = [line["right"] - line["left"] for line in lines]
    mean_width = sum(widths) / len(widths)

    if mean_width <= 0:
        return False

    variance = sum((w - mean_width) ** 2 for w in widths) / len(widths)
    std_dev = variance ** 0.5
    cv = std_dev / mean_width

    # Coefficient of variation < 0.15 (15% width variation) indicates high alignment uniformity (poetry columns)
    return cv < 0.15


def analyze_layout(ocr_results: list, img_width: int, img_height: int) -> str:
    """
    Reconstruct document layout from EasyOCR's bounding boxes and dimensions.
    Returns a Markdown-formatted string mimicking Gemini OCR output structures.
    """
    if not ocr_results:
        return ""

    boxes = []
    for res in ocr_results:
        box, text, confidence = res
        text = str(text).strip()
        if not text:
            continue

        # Extract coordinates from EasyOCR's 4-point list: [[x0, y0], [x1, y1], [x2, y2], [x3, y3]]
        left = min(pt[0] for pt in box)
        right = max(pt[0] for pt in box)
        top = min(pt[1] for pt in box)
        bottom = max(pt[1] for pt in box)
        height = bottom - top
        width = right - left

        boxes.append({
            "text": text,
            "conf": float(confidence),
            "left": int(left),
            "top": int(top),
            "right": int(right),
            "bottom": int(bottom),
            "height": float(height),
            "width": int(width),
            "yc": (top + bottom) / 2.0  # Vertical center
        })

    if not boxes:
        return ""

    # Group word bounding boxes into horizontal lines based on vertical overlap
    boxes.sort(key=lambda b: b["yc"])
    grouped_lines = []
    for box in boxes:
        placed = False
        for line in grouped_lines:
            line_avg_yc = sum(b["yc"] for b in line) / len(line)
            line_avg_height = sum(b["height"] for b in line) / len(line)
            
            # If the box center is within 60% of the line height from the line center, group them
            if abs(box["yc"] - line_avg_yc) < (line_avg_height * 0.6):
                line.append(box)
                placed = True
                break
        if not placed:
            grouped_lines.append([box])

    # Sort lines top-to-bottom based on their average vertical center
    grouped_lines.sort(key=lambda line: sum(b["yc"] for b in line) / len(line))

    # Construct the final sorted lines list, sorting words from right to left (RTL) within each line
    lines = []
    for line in grouped_lines:
        line.sort(key=lambda b: -b["left"])
        line_text = " ".join(b["text"] for b in line)
        
        line_left = min(b["left"] for b in line)
        line_right = max(b["right"] for b in line)
        line_top = min(b["top"] for b in line)
        line_bottom = max(b["bottom"] for b in line)
        
        lines.append({
            "text": line_text,
            "conf": sum(b["conf"] for b in line) / len(line),
            "left": line_left,
            "right": line_right,
            "top": line_top,
            "bottom": line_bottom,
            "mean_height": float(line_bottom - line_top),
            "width": line_right - line_left
        })

    # Classify Zones: Headers & Footers
    # Page regions: Top 8% is header zone, bottom 8% is footer zone
    header_threshold = img_height * 0.08
    footer_threshold = img_height * 0.92

    headers = []
    footers = []
    body_lines = []

    for line in lines:
        if line["top"] < header_threshold:
            headers.append(f"[Header] {line['text']}")
        elif line["top"] > footer_threshold:
            footers.append(f"[Footer] {line['text']}")
        else:
            body_lines.append(line)

    if not body_lines:
        return "\n".join(headers + footers)

    # Heading Detection
    # Determine the median height of body lines to compare relative size differences
    body_heights = [line["mean_height"] for line in body_lines]
    median_height = calculate_median(body_heights) or 15.0

    # Minimum absolute height threshold (in pixels) to avoid noise in tiny fonts
    MIN_HEADING_PX = 25.0

    for line in body_lines:
        h = line["mean_height"]
        # Chapter / Large Header: > 2.2x median
        if h > median_height * 2.2 and h >= MIN_HEADING_PX:
            line["text"] = f"# {line['text']}"
            line["is_heading"] = True
        # Section / Medium Header: > 1.6x median
        elif h > median_height * 1.6 and h >= MIN_HEADING_PX:
            line["text"] = f"## {line['text']}"
            line["is_heading"] = True
        else:
            line["is_heading"] = False

        # Table of Contents entry check
        if not line["is_heading"] and TOC_LINE_PATTERN.match(line["text"]):
            line["text"] = parse_toc_line(line["text"])

    # Group body lines into paragraphs/blocks based on vertical line gaps
    # Calculate median line gap between consecutive body lines
    gaps = []
    for i in range(len(body_lines) - 1):
        gap = body_lines[i+1]["top"] - body_lines[i]["bottom"]
        if gap > 0:
            gaps.append(gap)
    median_gap = calculate_median(gaps) if gaps else 10.0

    # A vertical gap larger than 1.8x median gap indicates a paragraph break
    paragraph_threshold = max(median_gap * 1.8, 12.0)

    blocks = []
    current_block = [body_lines[0]]

    for i in range(1, len(body_lines)):
        prev_line = body_lines[i-1]
        curr_line = body_lines[i]
        
        # Check vertical gap between lines
        gap = curr_line["top"] - prev_line["bottom"]
        
        # If the gap is larger than threshold, or if either line is a heading, start a new block
        if gap > paragraph_threshold or prev_line.get("is_heading") or curr_line.get("is_heading"):
            blocks.append(current_block)
            current_block = [curr_line]
        else:
            current_block.append(curr_line)
    
    if current_block:
        blocks.append(current_block)

    body_blocks_formatted = []
    for block_lines in blocks:
        # Check if the block represents a poem
        if detect_poem_block(block_lines):
            # Poem: Preserve hard line breaks
            block_text = "\n".join(line["text"] for line in block_lines)
        else:
            # Standard block/paragraph: join lines with spaces.
            # Preserve headings and pipe tables separate.
            lines_text = []
            current_paragraph = []
            
            for line in block_lines:
                if line.get("is_heading") or line["text"].startswith("|"):
                    if current_paragraph:
                        lines_text.append(" ".join(current_paragraph))
                        current_paragraph = []
                    lines_text.append(line["text"])
                else:
                    current_paragraph.append(line["text"])
                    
            if current_paragraph:
                lines_text.append(" ".join(current_paragraph))
                
            block_text = "\n".join(lines_text)

        if block_text.strip():
            body_blocks_formatted.append(block_text)

    # Assemble everything
    output_parts = []
    if headers:
        output_parts.append("\n".join(headers))
    if body_blocks_formatted:
        output_parts.append("\n\n".join(body_blocks_formatted))
    if footers:
        output_parts.append("\n".join(footers))

    return "\n\n".join(output_parts)
