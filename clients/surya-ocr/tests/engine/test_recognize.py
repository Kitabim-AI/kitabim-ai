import io

import pytest
from unittest.mock import MagicMock, patch

from PIL import Image

import engine.recognize as svc


@pytest.fixture(autouse=True)
def reset_singleton():
    svc._recognition_predictor = None
    yield
    svc._recognition_predictor = None


def _fake_png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (10, 10)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_get_recognition_predictor_constructs_once_and_caches():
    with patch("engine.recognize.RecognitionPredictor") as mock_cls:
        mock_cls.return_value = "predictor-instance"
        p1 = await svc.get_recognition_predictor()
        p2 = await svc.get_recognition_predictor()
    assert p1 == "predictor-instance"
    assert p1 is p2
    mock_cls.assert_called_once_with()


def test_recognize_page_calls_predictor_full_page_and_returns_first_result():
    mock_predictor = MagicMock()
    mock_result = MagicMock()
    mock_predictor.return_value = [mock_result]

    result = svc.recognize_page(mock_predictor, image="fake-image")

    mock_predictor.assert_called_once_with(["fake-image"], full_page=True)
    assert result is mock_result


def test_label_sets_are_disjoint():
    assert not (svc.FOOTNOTE_LABELS & svc.DISCARD_LABELS)


def test_is_page_blank_true_for_uniform_pixels():
    pix = MagicMock()
    pix.samples = bytes([200] * 3000)
    assert svc.is_page_blank(pix) is True


def test_is_page_blank_false_for_varied_pixels():
    pix = MagicMock()
    pix.samples = bytes(([10, 250] * 1500))
    assert svc.is_page_blank(pix) is False


def _block(label, html, position=0, skipped=False, error=False, confidence=0.9):
    b = MagicMock()
    b.label = label
    b.html = html
    b.reading_order = position
    b.skipped = skipped
    b.error = error
    b.confidence = confidence
    return b


def test_process_page_sync_renders_each_block_type_and_appends_footnotes_last():
    img = Image.new("RGB", (200, 200))
    mock_predictor = MagicMock()
    mock_result = MagicMock()
    mock_result.blocks = [
        _block("SectionHeader", "<h1>چوڭ ماۋزۇ</h1>", position=0),
        _block("Text", "<p>بۇ ئادەتتىكى تېكىست.</p>", position=1),
        _block("TableOfContents", "<ol><li>3 ..... باب بىر</li></ol>", position=2),
        _block("Footnote", "<p>پايدىلانما 12</p>", position=3),
        _block("Picture", "", position=4, skipped=True),
    ]

    with patch("engine.recognize.recognize_page", return_value=mock_result):
        markdown, mean_conf = svc._process_page_sync(img, mock_predictor)

    blocks = markdown.split("\n\n")
    assert blocks[0] == "# چوڭ ماۋزۇ"
    assert blocks[1] == "بۇ ئادەتتىكى تېكىست."
    assert blocks[2] == "| باب بىر | 3 |"
    assert blocks[3] == "پايدىلانما 12"
    assert mean_conf == 0.9


def test_process_page_sync_skips_discarded_and_errored_blocks():
    img = Image.new("RGB", (200, 200))
    mock_predictor = MagicMock()
    mock_result = MagicMock()
    mock_result.blocks = [
        _block("PageHeader", "<p>running header</p>", position=0),
        _block("PageFooter", "<p>3</p>", position=1),
        _block("Text", "<p>real content</p>", position=2, error=True),
        _block("Text", "<p>good content</p>", position=3),
    ]

    with patch("engine.recognize.recognize_page", return_value=mock_result):
        markdown, _ = svc._process_page_sync(img, mock_predictor)

    assert markdown == "good content"


@pytest.mark.asyncio
async def test_ocr_page_with_surya_happy_path():
    mock_page = MagicMock()
    mock_pix = MagicMock()
    mock_pix.samples = bytes(([10, 250] * 1500))
    mock_pix.tobytes.return_value = _fake_png_bytes()
    mock_page.get_pixmap.return_value = mock_pix

    with (
        patch("engine.recognize._process_page_sync", return_value=("متن", 0.9)),
        patch("engine.recognize.clean_uyghur_text", side_effect=lambda t: t),
    ):
        result = await svc.ocr_page_with_surya(
            mock_page, MagicMock(), min_confidence=0.3
        )

    assert result == "متن"


@pytest.mark.asyncio
async def test_ocr_page_with_surya_blank_page_returns_empty_without_processing():
    mock_page = MagicMock()
    mock_pix = MagicMock()
    mock_pix.samples = bytes([128] * 3000)
    mock_page.get_pixmap.return_value = mock_pix

    with patch("engine.recognize._process_page_sync") as mock_process:
        result = await svc.ocr_page_with_surya(mock_page, MagicMock())

    assert result == ""
    mock_process.assert_not_called()


@pytest.mark.asyncio
async def test_ocr_page_with_surya_retries_on_low_confidence():
    mock_page = MagicMock()
    mock_pix = MagicMock()
    mock_pix.samples = bytes(([10, 250] * 1500))
    mock_pix.tobytes.return_value = _fake_png_bytes()
    mock_page.get_pixmap.return_value = mock_pix

    with (
        patch(
            "engine.recognize._process_page_sync",
            return_value=("low conf text", 0.1),
        ),
        patch("engine.recognize.clean_uyghur_text", side_effect=lambda t: t),
        patch("engine.recognize.OCR_MAX_RETRIES", 2),
    ):
        with pytest.raises(svc.LowConfidenceOcrError):
            await svc.ocr_page_with_surya(mock_page, MagicMock(), min_confidence=0.5)

    assert mock_page.get_pixmap.call_count == 2


@pytest.mark.asyncio
async def test_ocr_page_with_surya_retries_on_degenerate_repetition_loop():
    mock_page = MagicMock()
    mock_pix = MagicMock()
    mock_pix.samples = bytes(([10, 250] * 1500))
    mock_pix.tobytes.return_value = _fake_png_bytes()
    mock_page.get_pixmap.return_value = mock_pix

    degenerate_text = " ".join(["مۇزىكا"] * 300)

    with (
        patch(
            "engine.recognize._process_page_sync",
            return_value=(degenerate_text, 0.95),
        ),
        patch("engine.recognize.clean_uyghur_text", side_effect=lambda t: t),
        patch("engine.recognize.OCR_MAX_RETRIES", 2),
    ):
        with pytest.raises(svc.LowConfidenceOcrError):
            await svc.ocr_page_with_surya(mock_page, MagicMock(), min_confidence=0.3)

    assert mock_page.get_pixmap.call_count == 2
