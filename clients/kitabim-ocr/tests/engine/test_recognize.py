import io
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

import engine.recognize as svc


@pytest.fixture(autouse=True)
def reset_singleton():
    svc._surya_predictor = None
    svc._savitr_predictor = None
    yield
    svc._surya_predictor = None
    svc._savitr_predictor = None


def _fake_png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (10, 10)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_get_recognition_predictor_surya_constructs_once_and_caches():
    with patch("surya.recognition.RecognitionPredictor") as mock_cls:
        mock_cls.return_value = "predictor-instance"
        p1 = await svc.get_recognition_predictor(engine="surya")
        p2 = await svc.get_recognition_predictor(engine="surya")
    assert p1 == "predictor-instance"
    assert p1 is p2
    mock_cls.assert_called_once_with()


@pytest.mark.asyncio
async def test_get_recognition_predictor_savitr_constructs_and_caches():
    with (
        patch("engine.recognize.is_apple_silicon", return_value=True),
        patch("engine.savitr_engine.SavitrPredictor") as mock_cls,
    ):
        mock_cls.return_value = "savitr-instance"
        p1 = await svc.get_recognition_predictor(engine="savitr")
        p2 = await svc.get_recognition_predictor(engine="savitr")
    assert p1 == "savitr-instance"
    assert p1 is p2
    mock_cls.assert_called_once()


@pytest.mark.asyncio
async def test_get_recognition_predictor_savitr_raises_on_non_apple_silicon():
    with patch("engine.recognize.is_apple_silicon", return_value=False):
        with pytest.raises(
            RuntimeError, match="Savitr OCR is optimized for Apple Silicon"
        ):
            await svc.get_recognition_predictor(engine="savitr")


@pytest.mark.asyncio
async def test_get_recognition_predictor_unknown_engine_raises_value_error():
    with pytest.raises(ValueError, match="Unknown OCR engine"):
        await svc.get_recognition_predictor(engine="nonexistent")


def test_recognize_page_calls_predictor_full_page_and_returns_first_result():
    mock_predictor = MagicMock()
    mock_result = MagicMock()
    mock_predictor.return_value = [mock_result]

    result = svc.recognize_page(mock_predictor, image="fake-image")

    mock_predictor.assert_called_once_with(["fake-image"], full_page=True)
    assert result is mock_result


def test_recognize_page_with_savitr_predictor():
    mock_predictor = MagicMock(spec=svc.SavitrPredictor)
    mock_predictor.recognize_image.return_value = ("<p>test</p>", 1.0)

    result = svc.recognize_page(mock_predictor, image="fake-image")

    mock_predictor.recognize_image.assert_called_once_with("fake-image")
    assert result == ("<p>test</p>", 1.0)


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


def test_process_page_sync_with_savitr_predictor():
    img = Image.new("RGB", (200, 200))
    mock_predictor = MagicMock(spec=svc.SavitrPredictor)
    mock_predictor.recognize_image.return_value = (
        "<h1>چوڭ ماۋزۇ</h1><p>بۇ ئادەتتىكى تېكىست.</p><table><tr><td>باب بىر</td><td>3</td></tr></table>",
        1.0,
    )

    markdown, mean_conf = svc._process_page_sync(img, mock_predictor)
    assert "# چوڭ ماۋزۇ" in markdown
    assert "بۇ ئادەتتىكى تېكىست." in markdown
    assert mean_conf == 1.0


def test_process_savitr_html_nested_containers_no_duplication():
    nested_html = """
    <div>
        <div>
            <p>مەسئۇل مۇھەررىرى: ئابلىكىم ھەسەن</p>
            <p>مەسئۇل كۇررېكتورى: دىليار تۇرسۇن</p>
        </div>
        <h2>گۈلنىڭ ئېچىلىشى قىيىن</h2>
        <p>(رومان)</p>
    </div>
    """
    result = svc._process_savitr_html(nested_html)
    assert result.count("مەسئۇل مۇھەررىرى: ئابلىكىم ھەسەن") == 1
    assert result.count("مەسئۇل كۇررېكتورى: دىليار تۇرسۇن") == 1
    assert result.count("گۈلنىڭ ئېچىلىشى قىيىن") == 1
    assert "## گۈلنىڭ ئېچىلىشى قىيىن" in result
    assert result.count("(رومان)") == 1


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
async def test_ocr_page_happy_path():
    mock_page = MagicMock()
    mock_pix = MagicMock()
    mock_pix.samples = bytes(([10, 250] * 1500))
    mock_pix.tobytes.return_value = _fake_png_bytes()
    mock_page.get_pixmap.return_value = mock_pix

    with (
        patch("engine.recognize._process_page_sync", return_value=("متن", 0.9)),
        patch("engine.recognize.clean_uyghur_text", side_effect=lambda t: t),
    ):
        result = await svc.ocr_page(mock_page, MagicMock(), min_confidence=0.3)

    assert result == "متن"


@pytest.mark.asyncio
async def test_ocr_page_blank_page_returns_empty_without_processing():
    mock_page = MagicMock()
    mock_pix = MagicMock()
    mock_pix.samples = bytes([128] * 3000)
    mock_page.get_pixmap.return_value = mock_pix

    with patch("engine.recognize._process_page_sync") as mock_process:
        result = await svc.ocr_page(mock_page, MagicMock())

    assert result == ""
    mock_process.assert_not_called()


@pytest.mark.asyncio
async def test_ocr_page_retries_on_low_confidence():
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
            await svc.ocr_page(mock_page, MagicMock(), min_confidence=0.5)

    assert mock_page.get_pixmap.call_count == 2


@pytest.mark.asyncio
async def test_ocr_page_retries_on_degenerate_repetition_loop():
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
            await svc.ocr_page(mock_page, MagicMock(), min_confidence=0.3)

    assert mock_page.get_pixmap.call_count == 2


@pytest.mark.asyncio
async def test_ocr_page_timeout_aborts_immediately_without_further_retries():
    mock_page = MagicMock()
    mock_pix = MagicMock()
    mock_pix.samples = bytes(([10, 250] * 1500))
    mock_pix.tobytes.return_value = _fake_png_bytes()
    mock_page.get_pixmap.return_value = mock_pix

    with (
        patch("asyncio.wait_for", side_effect=TimeoutError("timed out")),
        patch("engine.recognize.OCR_MAX_RETRIES", 4),
    ):
        with pytest.raises(TimeoutError, match="OCR timed out after"):
            await svc.ocr_page(mock_page, MagicMock(), timeout=5.0)

    # Must abort immediately on timeout without trying zoom attempts 2, 3, 4
    assert mock_page.get_pixmap.call_count == 1


@pytest.mark.asyncio
async def test_ocr_page_respects_custom_max_retries():
    mock_page = MagicMock()
    mock_pix = MagicMock()
    mock_pix.samples = bytes(([10, 250] * 1500))
    mock_pix.tobytes.return_value = _fake_png_bytes()
    mock_page.get_pixmap.return_value = mock_pix

    with (
        patch("engine.recognize._process_page_sync", return_value=("low conf", 0.1)),
        patch("engine.recognize.clean_uyghur_text", side_effect=lambda t: t),
        patch("engine.recognize.OCR_MAX_RETRIES", 4),
    ):
        with pytest.raises(svc.LowConfidenceOcrError):
            await svc.ocr_page(
                mock_page, MagicMock(), min_confidence=0.5, max_retries=1
            )

    # Explicit max_retries=1 means single attempt with zero retries
    assert mock_page.get_pixmap.call_count == 1


def test_get_executor_scales_and_reuses():
    svc._executor = None
    exec1 = svc._get_executor(2)
    assert exec1._max_workers == 2

    # Calling with the same worker count reuses the existing executor
    exec2 = svc._get_executor(2)
    assert exec2 is exec1

    # Calling with a larger worker count expands the executor
    exec3 = svc._get_executor(4)
    assert exec3._max_workers == 4
    assert exec3 is not exec1

    # Calling with a smaller worker count shrinks the executor back down
    exec4 = svc._get_executor(1)
    assert exec4._max_workers == 1
    assert exec4 is not exec3
    svc._executor = None


@pytest.mark.asyncio
async def test_ocr_page_passes_max_parallel_to_executor():
    mock_page = MagicMock()
    mock_pix = MagicMock()
    mock_pix.samples = bytes(([10, 250] * 1500))
    mock_pix.tobytes.return_value = _fake_png_bytes()
    mock_page.get_pixmap.return_value = mock_pix

    with (
        patch("engine.recognize._process_page_sync", return_value=("متن", 0.9)),
        patch("engine.recognize.clean_uyghur_text", side_effect=lambda t: t),
    ):
        result = await svc.ocr_page(mock_page, MagicMock(), max_parallel_pages=4)

    assert result == "متن"
    assert svc._executor is not None
    assert svc._executor._max_workers == 4
    svc._executor = None


@pytest.mark.asyncio
async def test_ocr_page_caps_surya_concurrency_to_max_four():
    mock_page = MagicMock()
    mock_pix = MagicMock()
    mock_pix.samples = bytes(([10, 250] * 1500))
    mock_pix.tobytes.return_value = _fake_png_bytes()
    mock_page.get_pixmap.return_value = mock_pix

    with (
        patch("engine.recognize._process_page_sync", return_value=("متن", 0.9)),
        patch("engine.recognize.clean_uyghur_text", side_effect=lambda t: t),
    ):
        result = await svc.ocr_page(mock_page, MagicMock(), max_parallel_pages=8)

    assert result == "متن"
    assert svc._executor is not None
    assert svc._executor._max_workers == 4
    svc._executor = None


@pytest.mark.asyncio
async def test_ocr_page_executes_concurrently_in_parallel():
    import asyncio
    import time

    svc._executor = None

    def _slow_sync_process(img, predictor):
        time.sleep(0.08)
        return "متن", 0.95

    mock_page = MagicMock()
    mock_pix = MagicMock()
    mock_pix.samples = bytes(([10, 250] * 1500))
    mock_pix.tobytes.return_value = _fake_png_bytes()
    mock_page.get_pixmap.return_value = mock_pix

    with (
        patch("engine.recognize._process_page_sync", side_effect=_slow_sync_process),
        patch("engine.recognize.clean_uyghur_text", side_effect=lambda t: t),
    ):
        start = time.perf_counter()
        tasks = [
            svc.ocr_page(mock_page, MagicMock(), max_parallel_pages=4) for _ in range(4)
        ]
        results = await asyncio.gather(*tasks)
        elapsed = time.perf_counter() - start

    assert len(results) == 4
    assert elapsed < 0.28, f"Expected parallel execution (<0.28s), got {elapsed:.3f}s"
    svc._executor = None
