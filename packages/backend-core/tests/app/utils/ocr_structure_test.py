from app.utils.ocr_structure import (
    order_line_rtl,
    filter_header_footer,
    detect_headings,
    format_toc_lines,
    assemble_page_markdown,
)


def test_order_line_rtl():
    # Boxes across the same line from left to right (x=10, x=50, x=100)
    # Uyghur is RTL, so text should be sorted descending by X (x=100 first, then 50, then 10)
    b1 = ([[10, 100], [30, 100], [30, 120], [10, 120]], "بىر", 0.9)
    b2 = ([[50, 100], [80, 100], [80, 120], [50, 120]], "ئىككى", 0.95)
    b3 = ([[100, 100], [140, 100], [140, 120], [100, 120]], "ئۈچ", 0.92)

    ordered = order_line_rtl([b1, b2, b3])
    texts = [item[1] for item in ordered]
    assert texts == ["ئۈچ", "ئىككى", "بىر"]


def test_filter_header_footer():
    page_height = 1000.0
    band_pct = 0.08  # 80px from top and bottom
    # Top header at y=40
    header_box = ([[50, 30], [200, 30], [200, 50], [50, 50]], "Header Title", 0.9)
    # Body line at y=500
    body_box = ([[50, 490], [400, 490], [400, 510], [50, 510]], "Body Content", 0.95)
    # Footer line at y=960
    footer_box = ([[200, 950], [250, 950], [250, 970], [200, 970]], "12", 0.9)

    filtered = filter_header_footer(
        [header_box, body_box, footer_box], page_height, band_pct
    )
    assert len(filtered) == 1
    assert filtered[0][1] == "Body Content"


def test_detect_headings():
    # Normal body lines height ~20px
    line1 = [
        ([[50, 100], [500, 100], [500, 120], [50, 120]], "بىرىنچى ئابزاس مەزمۇنى", 0.9)
    ]
    line2 = [
        ([[50, 130], [500, 130], [500, 150], [50, 150]], "ئىككىنچى ئابزاس مەزمۇنى", 0.9)
    ]
    # Big heading line height ~35px
    heading_line = [([[100, 50], [300, 50], [300, 90], [100, 90]], "كىرىش سۆز", 0.95)]

    lines = [heading_line, line1, line2]
    res = detect_headings(lines, heading_size_ratio=1.3)
    assert res[0].startswith("# ")
    assert "كىرىش سۆز" in res[0]
    assert not res[1].startswith("#")


def test_format_toc_lines():
    toc_raw = [
        "# مۇندەرىجە",
        "مۇقەددىمە نەمەنگانلىق خوجا 1",
        "بىرىنچى باب موغۇلىستانغا يۈرۈش قىلىش .................... 31",
        "ئاددىي بىر جۈملە تېكىست.",
    ]
    formatted = format_toc_lines(toc_raw)
    assert formatted[0] == "# مۇندەرىجە"
    assert formatted[1] == "| 1 | مۇقەددىمە نەمەنگانلىق خوجا |"
    assert formatted[2] == "| 31 | بىرىنچى باب موغۇلىستانغا يۈرۈش قىلىش |"
    assert formatted[3] == "ئاددىي بىر جۈملە تېكىست."


def test_assemble_page_markdown_integration():
    page_width = 600.0
    page_height = 800.0
    # Header at y=30 (should be excluded)
    header = ([[50, 20], [200, 20], [200, 40], [50, 40]], "كىتاب نامى", 0.99)
    # Heading at y=100 (height 40px)
    heading = ([[150, 80], [450, 80], [450, 120], [150, 120]], "1-باپ", 0.95)
    # Body text at y=160
    body = ([[50, 150], [550, 150], [550, 170], [50, 170]], "بۇ بىر سىناق جۈملە.", 0.9)
    # Footer at y=760 (should be excluded)
    footer = ([[280, 750], [320, 750], [320, 770], [280, 770]], "15", 0.9)

    detections = [header, heading, body, footer]
    md = assemble_page_markdown(detections, page_width, page_height)
    assert "كىتاب نامى" not in md
    assert "15" not in md
    assert "# 1-باپ" in md
    assert "بۇ بىر سىناق جۈملە." in md
