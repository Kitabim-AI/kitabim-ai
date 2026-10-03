from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from PIL import Image

logger = logging.getLogger("kitabim_ocr_client.engine.paddle")


@dataclass
class PaddleBlock:
    """Surya-compatible block representation of PaddleOCR text detection."""

    reading_order: int
    confidence: float
    html: str
    label: str = "Text"
    bbox: list[int] = field(default_factory=list)
    polygon: list[list[int]] = field(default_factory=list)
    skipped: bool = False
    error: bool = False


@dataclass
class PaddleRecognitionResult:
    """Surya-compatible page recognition result holding detected blocks."""

    blocks: list[PaddleBlock] = field(default_factory=list)


def normalize_uyghur_text_direction(text: str) -> str:
    """Normalize text direction for Uyghur Arabic text.

    Ensures the string is stored in Unicode logical order (RTL character sequence).
    """
    cleaned = (text or "").strip()
    return cleaned


def cluster_lines_into_reading_order(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Sort text boxes into natural reading order for Uyghur script.

    Groups bounding boxes into horizontal line bands (top-to-bottom), then sorts
    items within each line band from right to left (descending x-coordinate).
    """
    if not items:
        return []

    # Sort primarily by vertical top coordinate
    sorted_by_y = sorted(items, key=lambda it: (it["bbox"][1], it["bbox"][0]))

    bands: list[list[dict[str, Any]]] = []

    for item in sorted_by_y:
        box = item["bbox"]
        min_x, min_y, max_x, max_y = box
        height = max(1, max_y - min_y)
        mid_y = (min_y + max_y) / 2.0

        placed = False
        for band in bands:
            # Check overlap with band's vertical span
            band_mid_y = sum((b["bbox"][1] + b["bbox"][3]) / 2.0 for b in band) / len(
                band
            )
            band_avg_height = sum(
                max(1, b["bbox"][3] - b["bbox"][1]) for b in band
            ) / len(band)
            # Boxes in the same line band typically overlap by at least 50% line height
            if abs(mid_y - band_mid_y) <= 0.5 * max(height, band_avg_height):
                band.append(item)
                placed = True
                break

        if not placed:
            bands.append([item])

    # Sort bands top-to-bottom by average mid_y
    bands.sort(
        key=lambda band: sum((b["bbox"][1] + b["bbox"][3]) / 2.0 for b in band)
        / len(band)
    )

    # Within each band, sort Right-to-Left (descending right edge max_x)
    ordered_items: list[dict[str, Any]] = []
    for band in bands:
        band.sort(key=lambda b: b["bbox"][2], reverse=True)
        ordered_items.extend(band)

    return ordered_items


class PaddleEnginePredictor:
    """Predictor adapter for Baidu PaddleOCR multilingual Uyghur model."""

    def __init__(self, ocr_instance: Any = None, use_gpu: bool = False) -> None:
        if ocr_instance is not None:
            self.engine = ocr_instance
            return

        try:
            from paddleocr import PaddleOCR  # type: ignore
        except ImportError as err:
            raise ImportError(
                "PaddleOCR engine requires 'paddlepaddle' and 'paddleocr'.\n"
                "Install them with:\n"
                "    pip install paddlepaddle paddleocr\n"
            ) from err

        logger.info("Initializing PaddleOCR with lang='ug'...")
        try:
            self.engine = PaddleOCR(lang="ug", use_textline_orientation=True)
        except Exception:
            self.engine = PaddleOCR(lang="ug")
        logger.info("PaddleOCR engine initialized successfully.")

    def recognize_image(self, image: "Image.Image") -> PaddleRecognitionResult:
        """Run PaddleOCR on a PIL image and return Surya-compatible blocks."""
        # Convert PIL image to RGB numpy array
        rgb_image = image.convert("RGB")
        img_arr = np.array(rgb_image)

        raw_result = None
        try:
            if hasattr(self.engine, "predict"):
                raw_result = self.engine.predict(img_arr)
            elif hasattr(self.engine, "ocr"):
                raw_result = self.engine.ocr(img_arr, cls=True)
        except Exception as e:
            logger.error("PaddleOCR recognition failed: %s", e)
            return PaddleRecognitionResult(blocks=[])

        if not raw_result or raw_result[0] is None:
            return PaddleRecognitionResult(blocks=[])

        raw_items: list[dict[str, Any]] = []

        # Format 1: PaddleX / PaddleOCR 3.7+ dict result: [{'rec_texts': [...], 'rec_scores': [...], ...}]
        if (
            isinstance(raw_result, list)
            and raw_result
            and isinstance(raw_result[0], dict)
        ):
            page_data = raw_result[0]
            texts = page_data.get("rec_texts", [])
            scores = page_data.get("rec_scores", [])
            polys = page_data.get("rec_polys", [])
            boxes = page_data.get("rec_boxes", [])

            for i, text in enumerate(texts):
                cleaned_text = normalize_uyghur_text_direction(str(text))
                if not cleaned_text:
                    continue
                score = float(scores[i]) if i < len(scores) else 0.0

                if i < len(polys) and polys[i] is not None:
                    poly = [[int(pt[0]), int(pt[1])] for pt in polys[i]]
                    xs = [pt[0] for pt in poly]
                    ys = [pt[1] for pt in poly]
                    bbox = [min(xs), min(ys), max(xs), max(ys)]
                elif i < len(boxes) and boxes[i] is not None:
                    box = [int(v) for v in boxes[i]]
                    bbox = box
                    poly = [
                        [box[0], box[1]],
                        [box[2], box[1]],
                        [box[2], box[3]],
                        [box[0], box[3]],
                    ]
                else:
                    bbox = [0, 0, 100, 30]
                    poly = [[0, 0], [100, 0], [100, 30], [0, 30]]

                raw_items.append(
                    {
                        "bbox": bbox,
                        "polygon": poly,
                        "text": cleaned_text,
                        "confidence": score,
                    }
                )

        # Format 2: Legacy list result: [[ [box, (text, conf)], ... ]]
        elif (
            isinstance(raw_result, list)
            and raw_result
            and isinstance(raw_result[0], list)
        ):
            page_entries = raw_result[0]
            for entry in page_entries:
                if not entry or len(entry) < 2:
                    continue
                box_points, text_info = entry[0], entry[1]
                if not text_info or len(text_info) < 2:
                    continue
                text, conf = str(text_info[0]), float(text_info[1])
                cleaned_text = normalize_uyghur_text_direction(text)
                if not cleaned_text:
                    continue

                xs = [p[0] for p in box_points]
                ys = [p[1] for p in box_points]
                bbox = [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]

                raw_items.append(
                    {
                        "bbox": bbox,
                        "polygon": [[int(p[0]), int(p[1])] for p in box_points],
                        "text": cleaned_text,
                        "confidence": conf,
                    }
                )

        # Sort into RTL reading order
        ordered = cluster_lines_into_reading_order(raw_items)

        blocks: list[PaddleBlock] = []
        for idx, item in enumerate(ordered):
            html = f'<p dir="rtl">{item["text"]}</p>'
            block = PaddleBlock(
                reading_order=idx,
                confidence=item["confidence"],
                html=html,
                label="Text",
                bbox=item["bbox"],
                polygon=item["polygon"],
            )
            blocks.append(block)

        return PaddleRecognitionResult(blocks=blocks)
