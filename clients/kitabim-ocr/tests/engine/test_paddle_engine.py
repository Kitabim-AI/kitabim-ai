from __future__ import annotations

from typing import Any
from PIL import Image

from engine.paddle_engine import (
    cluster_lines_into_reading_order,
    normalize_uyghur_text_direction,
    PaddleEnginePredictor,
)


def test_normalize_uyghur_text_direction_standard():
    # Regular logical Uyghur text
    text = "ئۇيغۇر كىتابلىرى"
    normalized = normalize_uyghur_text_direction(text)
    assert normalized == text


def test_cluster_lines_into_reading_order_sorts_rtl_and_ttb():
    # Two lines: line 1 at y~100 (two words right and left), line 2 at y~200
    items = [
        {"bbox": [50, 100, 150, 130], "text": "سۆز2", "confidence": 0.95},  # left word
        {
            "bbox": [200, 100, 300, 130],
            "text": "سۆز1",
            "confidence": 0.98,
        },  # right word (starts first in RTL)
        {
            "bbox": [100, 200, 250, 230],
            "text": "ئىككىنچى قۇر",
            "confidence": 0.92,
        },  # second line
    ]
    sorted_items = cluster_lines_into_reading_order(items)
    # Line 1 right word should come before Line 1 left word
    assert sorted_items[0]["text"] == "سۆز1"
    assert sorted_items[1]["text"] == "سۆز2"
    assert sorted_items[2]["text"] == "ئىككىنچى قۇر"


def test_paddle_predictor_mock_inference():
    class DummyPaddle:
        def ocr(self, img_arr: Any, cls: bool = True) -> list[Any]:
            return [
                [
                    [[[10, 10], [100, 10], [100, 40], [10, 40]], ("سەھىپە بېشى", 0.96)],
                    [
                        [[10, 60], [200, 60], [200, 90], [10, 90]],
                        ("بىرىنچى ئابزاس", 0.91),
                    ],
                ]
            ]

    predictor = PaddleEnginePredictor(ocr_instance=DummyPaddle())
    dummy_img = Image.new("RGB", (300, 300), color="white")
    result = predictor.recognize_image(dummy_img)

    assert len(result.blocks) == 2
    assert result.blocks[0].label == "Text"
    assert "سەھىپە بېشى" in result.blocks[0].html
    assert result.blocks[0].reading_order == 0
    assert result.blocks[1].reading_order == 1


def test_paddle_predictor_empty_inference():
    class EmptyPaddle:
        def ocr(self, img_arr: Any, cls: bool = True) -> list[Any]:
            return [None]

    predictor = PaddleEnginePredictor(ocr_instance=EmptyPaddle())
    dummy_img = Image.new("RGB", (300, 300), color="white")
    result = predictor.recognize_image(dummy_img)

    assert len(result.blocks) == 0
