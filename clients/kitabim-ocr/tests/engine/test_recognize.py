import io
from unittest.mock import MagicMock, patch

import engine.recognize as svc
import pytest
from engine.text_cleanup import clean_uyghur_text
from PIL import Image


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
    pix.samples = bytes([10, 250] * 1500)
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


def test_process_page_sync_preserves_page_footer_with_text_content():
    img = Image.new("RGB", (200, 200))
    mock_predictor = MagicMock()
    mock_result = MagicMock()
    mock_result.blocks = [
        _block("Text", "<p>شېئىر مىسرالىرى</p>", position=0),
        _block("PageFooter", "<p>1983 - يىل 24 - فېۋرال، ئۈرۈمچى</p>", position=1),
    ]

    with patch("engine.recognize.recognize_page", return_value=mock_result):
        markdown, _ = svc._process_page_sync(img, mock_predictor)

    assert "شېئىر مىسرالىرى" in markdown
    assert "1983 - يىل 24 - فېۋرال، ئۈرۈمچى" in markdown


@pytest.mark.asyncio
async def test_ocr_page_happy_path():
    mock_page = MagicMock()
    mock_pix = MagicMock()
    mock_pix.samples = bytes([10, 250] * 1500)
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
    mock_pix.samples = bytes([10, 250] * 1500)
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
    mock_pix.samples = bytes([10, 250] * 1500)
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
    mock_pix.samples = bytes([10, 250] * 1500)
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
    mock_pix.samples = bytes([10, 250] * 1500)
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
    mock_pix.samples = bytes([10, 250] * 1500)
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
    mock_pix.samples = bytes([10, 250] * 1500)
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
    mock_pix.samples = bytes([10, 250] * 1500)
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


def test_suppress_bleed_through_cleans_faint_pixels():
    import numpy as np

    # Create an image with:
    # - Paper background: 240
    # - Real text strokes: 30
    # - Faint bleed-through text: 215
    arr = np.full((100, 100), 240, dtype=np.uint8)
    arr[10:20, 10:20] = 30  # Real text
    arr[50:60, 50:60] = 215  # Faint bleed-through
    img = Image.fromarray(arr, mode="L")

    cleaned = svc.suppress_bleed_through(img)
    clean_arr = np.array(cleaned)

    # Real text remains dark
    assert np.mean(clean_arr[10:20, 10:20]) < 50
    # Bleed-through is washed out to 255
    assert np.all(clean_arr[50:60, 50:60] == 255)


def test_suppress_bleed_through_bypasses_dark_pages():
    import numpy as np

    # Dark background (e.g. 50)
    arr = np.full((100, 100), 50, dtype=np.uint8)
    img = Image.fromarray(arr, mode="L")
    cleaned = svc.suppress_bleed_through(img)
    assert np.array_equal(np.array(cleaned), arr)


def test_is_phantom_bleed_through_block():
    import numpy as np

    gray_arr = np.full((100, 100), 240, dtype=np.uint8)
    gray_arr[10:20, 10:20] = 30  # Real text area
    # Bleed-through area has only faint pixels
    gray_arr[50:60, 50:60] = 210

    real_block = MagicMock()
    real_block.polygon = [[10, 10], [20, 10], [20, 20], [10, 20]]

    phantom_block = MagicMock()
    phantom_block.polygon = [[50, 50], [60, 50], [60, 60], [50, 60]]

    assert svc._is_phantom_bleed_through_block(real_block, gray_arr) is False
    assert svc._is_phantom_bleed_through_block(phantom_block, gray_arr) is True


def test_process_page_sync_discards_phantom_and_hallucinated_blocks():
    import numpy as np

    img_arr = np.full((200, 200), 240, dtype=np.uint8)
    img_arr[10:30, 10:30] = 20  # Real text area
    img = Image.fromarray(img_arr, mode="L")

    # Real block
    b0 = MagicMock()
    b0.reading_order = 0
    b0.label = "Text"
    b0.confidence = 0.95
    b0.skipped = False
    b0.error = False
    b0.polygon = [[10, 10], [30, 10], [30, 30], [10, 30]]
    b0.html = "<p>بۇ ھەقىقىي ئۇيغۇرچە تېكىست ماقالىسىدۇر.</p>"

    # Phantom block (no dark ink)
    b1 = MagicMock()
    b1.reading_order = 1
    b1.label = "Text"
    b1.confidence = 0.80
    b1.skipped = False
    b1.error = False
    b1.polygon = [[100, 100], [150, 100], [150, 150], [100, 150]]
    b1.html = "<p>ھەممە نەرسە قۇرۇق ئورۇن.</p>"

    # Repetition loop block
    b2 = MagicMock()
    b2.reading_order = 2
    b2.label = "Text"
    b2.confidence = 0.80
    b2.skipped = False
    b2.error = False
    b2.polygon = [[10, 10], [30, 10], [30, 30], [10, 30]]
    b2.html = "<p>" + ("تەكرار تەكرار تەكرار سۆز ") * 8 + "</p>"

    # Hallucinated Arabic block
    b3 = MagicMock()
    b3.reading_order = 3
    b3.label = "Text"
    b3.confidence = 0.80
    b3.skipped = False
    b3.error = False
    b3.polygon = [[10, 10], [30, 10], [30, 30], [10, 30]]
    b3.html = "<p>في المثال رفاعه وعنايه ولسسنه ؟ فمستولهم من القنبله ولا وعلا عليه للـهلمه ولقلا بـوا فرعه</p>"

    mock_result = MagicMock()
    mock_result.blocks = [b0, b1, b2, b3]

    mock_predictor = MagicMock()
    mock_predictor.return_value = [mock_result]

    markdown, confidence = svc._process_page_sync(img, mock_predictor)

    assert "بۇ ھەقىقىي ئۇيغۇرچە تېكىست ماقالىسىدۇر." in markdown
    assert "ھەممە نەرسە قۇرۇق ئورۇن." not in markdown
    assert "تەكرار تەكرار" not in markdown
    assert "في المثال" not in markdown


def test_block_html_to_markdown_preserves_poem_lines_and_merges_prose():
    poem_html = (
        "<p>غېبى جانان، دېفى ھىجران تۇگەتتى ياش باھارمىنى،<br/>"
        "مېنى كىم كۆرسە پەرق ئەتمەس خازاندىن لالىزارمىنى .<br/>"
        "ئاقار سەل ئورنىدا ياشىم، غېرىب بولدى ئەزىز باشىم،<br/>"
        "ماڭا تار ئەيلىدى چۈنكى بۇ دەۋران ئۆز دىيارمىنى .</p>"
    )
    # Poem should keep newlines in block markdown and after clean_uyghur_text
    poem_md = svc._block_html_to_markdown(poem_html)
    assert poem_md.count("\n") == 3
    assert poem_md.split("\n")[0] == "غېبى جانان، دېفى ھىجران تۇگەتتى ياش باھارمىنى،"
    assert clean_uyghur_text(poem_md).count("\n") == 3

    prose_html = (
        "<p>خەيرىيەت، ئەمدى تاھارىتىڭنى ئال. مەن نامىزىمنى ئۆتۈۋېرەي، -<br/>"
        "دېدى شېرىكى كۈلۈمسىرەپ ئۇنىڭغا پىسەنت قىلماي.</p>"
    )
    # Block markdown preserves lines; clean_uyghur_text merges mid-sentence wrapped lines
    prose_md = svc._block_html_to_markdown(prose_html)
    assert prose_md.count("\n") == 1
    cleaned = clean_uyghur_text(prose_md)
    assert "\n" not in cleaned
    assert "خەيرىيەت" in cleaned
    assert "شېرىكى" in cleaned


def test_prose_dialogue_lines_preserved_during_cleanup():
    prose_dialogue = (
        "دىرەنزە، ھويلىلاردىن مارىشىپ، ھاسانشاھنى زاڭلىق قىلىشتى، قاقاقلاپ كۈلۈشتى:\n"
        "— ياغلىقلا تاڭسا چىرايلىق چوكان بولغۇدەك! - ھا - ھا - ھا!\n"
        "— پۆرمىلىك كۆينەك كىيسە ئېرىگىنى تارتىۋالامدو تېخى!\n"
        "— ۋاھ - ھا - ھا! ھېيى - ھېي!"
    )
    cleaned = clean_uyghur_text(prose_dialogue)
    assert cleaned.count("\n") == 3
    lines = cleaned.split("\n")
    assert lines[0].endswith("قاقاقلاپ كۈلۈشتى:")
    assert lines[1].startswith("— ياغلىقلا تاڭسا")
    assert lines[2].startswith("— پۆرمىلىك كۆينەك")
    assert lines[3].startswith("— ۋاھ - ھا - ھا!")


def test_enhance_dots_and_contrast():
    img = Image.new("RGB", (50, 50), color=(200, 200, 200))
    enhanced = svc.enhance_dots_and_contrast(img)
    assert enhanced.size == (50, 50)
    assert enhanced.mode == "RGB"

    # Also converts non-RGB mode
    gray_img = Image.new("L", (30, 30), color=128)
    enhanced_gray = svc.enhance_dots_and_contrast(gray_img)
    assert enhanced_gray.mode == "RGB"


def test_get_adaptive_page_zoom():
    mock_page = MagicMock()

    # Small pocketbook page (415 pt width) -> scales up to reach >= 1500 px
    mock_page.rect.width = 415.0
    zoom = svc.get_adaptive_page_zoom(
        mock_page, base_zoom=3.0, min_target_width_px=1500.0
    )
    assert zoom > 3.0
    assert 3.5 <= zoom <= 3.7

    # Large A4 page (595 pt width) -> keeps base_zoom
    mock_page.rect.width = 595.0
    assert svc.get_adaptive_page_zoom(mock_page, base_zoom=3.0) == 3.0

    # Exception during rect access safely falls back to base_zoom
    mock_page_err = MagicMock()
    mock_page_err.rect = None
    assert svc.get_adaptive_page_zoom(mock_page_err, base_zoom=3.0) == 3.0


def test_get_block_bbox():
    # Polygon with 4 points
    b1 = MagicMock()
    b1.polygon = [[10.0, 20.0], [50.0, 20.0], [50.0, 60.0], [10.0, 60.0]]
    b1.bbox = None
    assert svc._get_block_bbox(b1) == (10.0, 50.0, 20.0, 60.0)

    # Bbox fallback [x0, y0, x1, y1] -> (x0, x1, y0, y1)
    b2 = MagicMock()
    b2.polygon = None
    b2.bbox = [5.0, 15.0, 45.0, 55.0]
    assert svc._get_block_bbox(b2) == (5.0, 45.0, 15.0, 55.0)

    # Missing geometry
    b3 = MagicMock()
    b3.polygon = None
    b3.bbox = None
    assert svc._get_block_bbox(b3) is None


def test_process_page_sync_groups_verse_lines_into_couplets_and_separates_stanzas():
    """Verify single-line verse blocks with tight line spacing are grouped into stanzas,
    while wider stanza gaps result in distinct stanzas separated by empty lines."""
    img = Image.new("RGB", (1000, 1000))
    mock_predictor = MagicMock()
    mock_result = MagicMock()

    # Stanza 1: 4 lines, height=50 each, gap=2 px
    # Stanza 2: 4 lines, starting with gap=50 px from Stanza 1
    def make_verse_block(order, y0, y1, text):
        b = MagicMock()
        b.label = "Text"
        b.html = f"<p>{text}</p>"
        b.reading_order = order
        b.skipped = False
        b.error = False
        b.confidence = 0.95
        b.polygon = [
            [300.0, float(y0)],
            [800.0, float(y0)],
            [800.0, float(y1)],
            [300.0, float(y1)],
        ]
        b.bbox = None
        return b

    mock_result.blocks = [
        # Stanza 1
        make_verse_block(0, 100, 150, "زىنداننىڭ ئىچىدەك قاراڭغۇ كېچە..."),
        make_verse_block(1, 152, 202, "ھۇۋىلايدۇ ئىزغىرىن قۇترىغان بوران ."),
        make_verse_block(2, 204, 254, "ئېگىلىپ دەرەخلەر، سۇنىدۇ شاخلار،"),
        make_verse_block(3, 256, 306, "ئۇچىدۇ سارغايغان ياپراقلار ھەر يان ."),
        # Stanza 2 (gap = 356 - 306 = 50 px, line_height=50 -> gap/h = 1.0)
        make_verse_block(4, 356, 406, "گۈركىرەپ ماشىنا، دىرىلدىدى تام،"),
        make_verse_block(5, 408, 458, "ئاچقۇچە ئۈلگۈرمەي سۇندى دەرۋازا ."),
        make_verse_block(6, 460, 510, "كىرىشتى باستۇرۇپ بىر توپ «ئىسيانچى»،"),
        make_verse_block(7, 512, 562, "چىراغتا پارقىرار قالپاق ۋە نەيزە ."),
    ]

    with patch("engine.recognize.recognize_page", return_value=mock_result), patch(
        "engine.recognize._is_phantom_bleed_through_block", return_value=False
    ):
        markdown, mean_conf = svc._process_page_sync(img, mock_predictor)

    stanzas = markdown.split("\n\n")
    assert (
        len(stanzas) == 2
    ), f"Expected 2 stanzas separated by empty line, got {len(stanzas)}: {stanzas}"

    # Each stanza should contain exactly 4 lines separated by single newlines
    stanza1_lines = stanzas[0].split("\n")
    assert len(stanza1_lines) == 4
    assert stanza1_lines[0] == "زىنداننىڭ ئىچىدەك قاراڭغۇ كېچە..."
    assert stanza1_lines[3] == "ئۇچىدۇ سارغايغان ياپراقلار ھەر يان ."

    stanza2_lines = stanzas[1].split("\n")
    assert len(stanza2_lines) == 4
    assert stanza2_lines[0] == "گۈركىرەپ ماشىنا، دىرىلدىدى تام،"
    assert stanza2_lines[3] == "چىراغتا پارقىرار قالپاق ۋە نەيزە ."


def test_process_page_sync_merges_grouped_prose_lines_that_fail_poem_check():
    """When Surya over-segments a single prose paragraph into short per-line
    Text blocks (tight vertical spacing groups them as verse candidates), but
    the group fails is_poem_block (irregular lengths, no rhyme/verse-ending
    punctuation), the lines must be reflowed as continuous prose (merged with
    spaces) - not treated as separate paragraphs split by blank lines."""
    img = Image.new("RGB", (1000, 1000))
    mock_predictor = MagicMock()
    mock_result = MagicMock()

    def make_line_block(order, y0, y1, text):
        b = MagicMock()
        b.label = "Text"
        b.html = f"<p>{text}</p>"
        b.reading_order = order
        b.skipped = False
        b.error = False
        b.confidence = 0.95
        b.polygon = [
            [300.0, float(y0)],
            [800.0, float(y0)],
            [800.0, float(y1)],
            [300.0, float(y1)],
        ]
        b.bbox = None
        return b

    mock_result.blocks = [
        make_line_block(0, 100, 150, "ئۇ ئۆيدىن چىقىپ كوچىغا قاراپ ماڭدى"),
        make_line_block(
            1, 152, 202, "يولدا كۆپ ئادەم بار ئىدى ئەمما ھېچكىم ئۇنى تونۇمايتتى"
        ),
        make_line_block(2, 204, 254, "ئاخىرى بازارغا يېتىپ باردى"),
    ]

    with patch("engine.recognize.recognize_page", return_value=mock_result), patch(
        "engine.recognize._is_phantom_bleed_through_block", return_value=False
    ):
        markdown, mean_conf = svc._process_page_sync(img, mock_predictor)

    assert "\n\n" not in markdown, (
        f"Expected the grouped non-poem lines to merge into one flowing "
        f"paragraph, got separate blocks: {markdown!r}"
    )
    assert "ئۇ ئۆيدىن چىقىپ كوچىغا قاراپ ماڭدى يولدا" in markdown


def test_process_page_sync_merges_dense_prose_page_into_flowing_paragraphs():
    """Regression test from a real book page: Surya segmented one continuous
    prose paragraph (narration interleaved with em-dash dialogue) into 24
    separate single-line Text blocks. _is_single_line_verse_block's
    width-ratio and dash-start checks - meant to exclude non-poem content -
    also blocked ordinary full-width prose lines and dialogue-attribution
    lines from ever being considered for grouping at all, so each printed
    line ended up rendered as its own paragraph. Those checks are redundant
    with is_poem_block's own (already-tested) equivalent checks applied to
    the assembled group, so removing them at the grouping-eligibility stage
    should let is_poem_block correctly reject the group as non-verse and
    route it to the prose-reflow (space-join) branch instead."""
    img = Image.new("RGB", (1500, 2270))
    mock_predictor = MagicMock()
    mock_result = MagicMock()

    def make_line_block(order, label, box, html):
        b = MagicMock()
        b.label = label
        b.html = html
        b.reading_order = order
        b.skipped = False
        b.error = False
        b.confidence = 0.95
        x0, x1, y0, y1 = box
        b.polygon = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
        b.bbox = None
        return b

    # Captured verbatim from Surya's real recognition output on the failing page.
    real_blocks = [
        (
            0,
            "Text",
            (205.5, 1360.5, 297.37, 542.53),
            "<p>ئالدىراش كېتىشۋاتاتتى. ئۇلارنىڭ ئارىسىدا ئۇچىسىغا جۈببەئى سىنجاپ يېپىنچاقلىۋالغان، ئۈستىگە يېشىل يېپەكتىن جۈببەۋە داستار كىيگەن، يېشى ئاتمىشلاردا بار بىر مويسىپىت كىشى ھەممىنىڭ ئالدىدا كېتىپ باراتتى.</p>",
        ),
        (
            1,
            "Text",
            (205.5, 1260.0, 540.26, 612.9),
            "<p>— مەنزىلگە يەنە قانچىلىك قالدۇق؟ — دەپ سورىدى ئۇ</p>",
        ),
        (
            2,
            "Text",
            (780.0, 1356.0, 603.82, 662.84),
            "<p>كەينىدىن كېلىۋاتقان بىرىدىن.</p>",
        ),
        (
            3,
            "Text",
            (205.5, 1260.0, 660.57, 726.4),
            "<p>— ئاز قالدۇق، نېمەتلىك پىرىم، ئەنە ئاۋۇ كۆرۈنگەن</p>",
        ),
        (
            4,
            "Text",
            (205.5, 1363.5, 719.59, 851.25),
            "<p>تۆپىلىكتىن ئاشساقلا ھەزرىتى سۇلتان مازىرىنىڭ ئالتۇن قۇببىلىرى كۆرۈنىدۇ! — دەپ جاۋاب بەردى ھېلىقى كىشى.</p>",
        ),
        (
            5,
            "Text",
            (205.5, 1260.0, 842.17, 908.0),
            "<p>— ھۆرمەتلىك مەككە خوجا، — دېدى بۇ چاغدا ئاتلىق</p>",
        ),
        (
            6,
            "Text",
            (205.5, 1363.5, 901.19, 964.75),
            "<p>كېتىۋاتقانلارنىڭ ئارىسىدىكى ياش بىرى، — سىلىنىڭ: «مانا</p>",
        ),
        (
            7,
            "Text",
            (205.5, 1363.5, 960.21, 1021.5),
            "<p>ئاز قالدۇق!» دېگەن سۆزلىرىنى بۈگۈن ئونىنچى قېتىم</p>",
        ),
        (
            8,
            "Text",
            (205.5, 1363.5, 1016.96, 1082.79),
            "<p>ئاڭلاۋاتىمىز! بىراق، قاق سەھەردىن باشلاپ ماڭغىلى</p>",
        ),
        (
            9,
            "Text",
            (205.5, 1363.5, 1078.25, 1144.08),
            "<p>تۇرىۋىدۇق، ئەلھال، ناماز ئەسىر ۋاقتىمۇ بولاي دەپ قالدى،</p>",
        ),
        (
            10,
            "Text",
            (205.5, 1363.5, 1139.54, 1205.37),
            "<p>قېنى ئۇ سىلى دېگەن ھەزرىتى سۇلتان مازىرىنىڭ ئالتۇن</p>",
        ),
        (
            11,
            "Text",
            (790.5, 1363.5, 1200.83, 1264.39),
            "<p>قۇببىسى؟ ھېچ كۆرۈنمەيدىغۇ؟</p>",
        ),
        (
            12,
            "Text",
            (205.5, 1260.0, 1264.39, 1327.95),
            "<p>— ئىنەللاھا مەئەسسابىرىن، سەۋر قىل ئى پەرزەنت</p>",
        ),
        (
            13,
            "Text",
            (205.5, 1363.5, 1323.41, 1389.24),
            "<p>مۇھەممەتئىمىن ئىشان! ئاللا بەندىلىرىگە سەۋر قىلىڭلار! دەپ</p>",
        ),
        (
            14,
            "Text",
            (205.5, 1363.5, 1382.43, 1448.26),
            "<p>ئۆگەتكەن، — دېدى ھېلىقى مويسىپىت كىشى بوش ئاۋاز بىلەن.</p>",
        ),
        (
            15,
            "Text",
            (205.5, 1260.0, 1443.72, 1507.28),
            "<p>— ئىنشائاللا، نېمەتلىك ئۇلۇغ پىرىم، ئەپۇ قىلغايسىز،</p>",
        ),
        (
            16,
            "Text",
            (205.5, 1363.5, 1502.74, 1566.3),
            "<p>مەن خېلىدىن بېرى ساياھەتكە چىقمىغانىدىم، — دېدى ئاتلىق</p>",
        ),
        (
            17,
            "Text",
            (205.5, 1363.5, 1561.76, 1627.59),
            "<p>ئادەملەرنىڭ ئارىسىدىكى مۇھەممەتئىمىن ئىشان دەپ ئاتالغان</p>",
        ),
        (
            18,
            "Text",
            (205.5, 1363.5, 1623.05, 1688.88),
            "<p>ھېلىقى يىگىت خۇشخۇيلۇق بىلەن كۈلۈپ تۇرۇپ، —</p>",
        ),
        (
            19,
            "Text",
            (205.5, 1363.5, 1684.34, 1750.17),
            "<p>ئۆسمۈرلۈك چاغلىرىمىزدا بىر نەچچە قېتىم پەدەرىمگە ئەگىشىپ</p>",
        ),
        (
            20,
            "Text",
            (205.5, 1363.5, 1745.63, 1811.46),
            "<p>ئەنجان، مەرغىلانغا سەپەر قىلغاننى ھېسابقا ئالمىغاندا، بۇنداق</p>",
        ),
        (
            21,
            "Text",
            (205.5, 1363.5, 1806.92, 1872.75),
            "<p>نەچچە كۈنلەپ ئۇزاق يول مېڭىپ باقمىغانىكەنمەن! بۇ ھەقىقەتەن</p>",
        ),
        (
            22,
            "Text",
            (562.5, 1363.5, 1865.94, 1929.5),
            "<p>ھاياتىمدىكى ئەڭ كۆڭۈللۈك سەپەر بولدى.</p>",
        ),
        (
            23,
            "Text",
            (205.5, 1260.0, 1924.96, 1990.79),
            "<p>— ئى پەرزەنت، ئاشۇ كۆڭۈلسىز پەرغانىنى تىلغا</p>",
        ),
        (24, "PageFooter", (1288.5, 1320.0, 2008.95, 2045.27), "<p>2</p>"),
    ]
    mock_result.blocks = [make_line_block(*data) for data in real_blocks]

    with patch("engine.recognize.recognize_page", return_value=mock_result), patch(
        "engine.recognize._is_phantom_bleed_through_block", return_value=False
    ):
        markdown, mean_conf = svc._process_page_sync(img, mock_predictor)

    paragraphs = markdown.split("\n\n")
    assert len(paragraphs) <= 4, (
        f"Expected the dense dialogue page to collapse into a handful of "
        f"flowing paragraphs, not one per printed line: got "
        f"{len(paragraphs)}: {paragraphs}"
    )
    # A dash-prefixed dialogue line and its non-dash continuation (previously
    # excluded from grouping entirely) must now reflow as one paragraph.
    assert (
        "— مەنزىلگە يەنە قانچىلىك قالدۇق؟ — دەپ سورىدى ئۇ كەينىدىن كېلىۋاتقان بىرىدىن."
        in markdown
    )
    # The opening (already internally-merged by Surya) paragraph is untouched.
    assert paragraphs[0].startswith("ئالدىراش كېتىشۋاتاتتى.")


def test_process_page_sync_preserves_prose_paragraphs_as_separate_blocks():
    """Verify that multi-line prose paragraphs detected by Surya are preserved as separate
    blocks separated by empty lines (\n\n) and not merged together as a single block."""
    img = Image.new("RGB", (859, 1200))
    mock_predictor = MagicMock()
    mock_result = MagicMock()

    def make_prose_block(order, bbox, text):
        b = MagicMock()
        b.label = "Text"
        b.html = f'<div data-label="Text"><p>{text}</p></div>'
        b.reading_order = order
        b.skipped = False
        b.error = False
        b.confidence = 0.98
        b.bbox = bbox
        b.polygon = None
        return b

    mock_result.blocks = [
        make_prose_block(
            0,
            (57.0, 132.0, 802.0, 261.0),
            "كەلتۈرگەن، شۇنداقلا ئۇيغۇر ھازىرقى زامان شېئىرىيىتىنىڭ ئالدىنقى قاراتارىدىكى ۋەكىللىرىنىڭ بىرىگە ئايلانغان. ئۇنىڭ «تاڭ شاماللىرى»، «ياخشى»، «مەن ئاق بايراق ئەمەس» قاتارلىق شېئىرلىرى، «ئۇلۇغ ئانا ھەققىدە چۆچەك»، «قەشقەر كېچىسى» قاتارلىق داستانلىرى ھازىرقى زامان ئۇيغۇر شېئىرىيىتىدە ئالاھىدە ئورۇن تۇتىدۇ.",
        ),
        make_prose_block(
            1,
            (57.0, 257.0, 802.0, 363.0),
            "ئابدۇرېھىم ئۆتكۈز 1980 - يىللاردىن تارتىپ بەدىئىي جەھەتتىكى تالانتىنى تارىخىي رومان ئىجادىيىتىگە قارىتىپ «ئىز»، «ئويغانغان زېمىن» رومانلىرىنى يازغان. بۇ رومانلار ئۇيغۇر رومانچىلىقىنىڭ شەكىللىك ئىشىگە ئاساس سالغان رومانلار بولۇپ ھېسابلىنىدۇ.",
        ),
        make_prose_block(
            2,
            (57.0, 358.0, 802.0, 435.0),
            "ئابدۇرېھىم ئۆتكۈز يەنە «تۈركىي تىللار دىۋانى»، «قۇتادغۇ بىدىلىك» قاتارلىق نادىر كلاسسىك ئەسەرلەرنى ھازىرقى زامان ئۇيغۇر تىلىدا نەشرگە تەييارلاش ئىشىدا ئالاھىدە تۆھپە قوشقان تەتقىقاتچى.",
        ),
        make_prose_block(
            3,
            (57.0, 432.0, 802.0, 687.0),
            "ھازىرغا قەدەر ئابدۇرېھىم ئۆتكۈزىنىڭ «يۈرەك مۇڭلىرى» (1946 - يىلى، لەنجۇ)، «تارىم بويلىرى» (1948 - يىلى، تيانشان نەشرىياتى) ناملىق شېئىرلار توپلىمى، «قەشقەر كېچىسى» (1980 - يىلى، شىنجاڭ خەلق نەشرىياتى) ناملىق داستانى، «ئۇمۇر مەنزىللىرى» (1985 - يىلى، شىنجاڭ ياشلار - ئۆسمۈرلەر نەشرىياتى) ناملىق شېئىرلار توپلىمى، «ئىز» (1985 - يىلى، شىنجاڭ خەلق نەشرىياتى)، «ئويغانغان زېمىن» (ئىككى قىسىم، 1988 -، 1994 - يىللىرى، شىنجاڭ خەلق نەشرىياتى) ناملىق رومانلىرى، «خەزىنىلەر بوسۇغىسىدا» (1996 - يىلى، شىنجاڭ خەلق نەشرىياتى) ناملىق ئىلمىي ماقالىلەر توپلىمى نەشر قىلىنغان.",
        ),
        make_prose_block(
            4,
            (57.0, 686.0, 802.0, 737.0),
            "بۇ توپلامغا شائىر ئابدۇرېھىم ئۆتكۈزىنىڭ ۋەكىللىك خاراكتېرىگە ئىگە لىرىك شېئىرلىرى كىرگۈزۈلدى.",
        ),
    ]

    with patch("engine.recognize.recognize_page", return_value=mock_result), patch(
        "engine.recognize._is_phantom_bleed_through_block", return_value=False
    ):
        markdown, mean_conf = svc._process_page_sync(img, mock_predictor)

    paragraphs = markdown.split("\n\n")
    assert (
        len(paragraphs) == 5
    ), f"Expected 5 paragraphs, got {len(paragraphs)}: {paragraphs}"
    cleaned = clean_uyghur_text(markdown)
    cleaned_paras = cleaned.split("\n\n")
    assert (
        len(cleaned_paras) == 5
    ), f"Expected 5 cleaned paragraphs, got {len(cleaned_paras)}"
    assert cleaned_paras[0].startswith("كەلتۈرگەن، شۇنداقلا")
    assert cleaned_paras[1].startswith("ئابدۇرېھىم ئۆتكۈز 1980")
    assert cleaned_paras[4].startswith("بۇ توپلامغا شائىر")
