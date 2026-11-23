from types import SimpleNamespace
from app.services.book_structure_service import (
    extract_book_sections,
    parse_page_blocks,
    solve_content_page_numbers,
)


def _mk_page(
    page_number: int,
    text: str = "",
    *,
    is_toc: bool = False,
    detected_page_number: int | None = None,
    content_page_number: str | None = None,
    content_page_number_manual: bool = False,
):
    return SimpleNamespace(
        page_number=page_number,
        text=text,
        is_toc=is_toc,
        detected_page_number=detected_page_number,
        content_page_number=content_page_number,
        content_page_number_manual=content_page_number_manual,
    )


def test_parse_page_blocks_handles_headers_paragraphs_and_footnotes():
    text = "# بىرىنچى قىسىم\n\n## 1-باب\n\nبىرىنچى ئابزاس تېكىستى.\n\n[1]: بۇ بىرىنچى ئىزاھات."
    blocks = parse_page_blocks(text)
    assert len(blocks) == 4
    assert blocks[0].kind == "heading"
    assert blocks[0].heading_level == 1
    assert blocks[1].kind == "heading"
    assert blocks[1].heading_level == 1  # 1-باب is a structural chapter title
    assert blocks[2].kind == "prose"
    assert blocks[2].raw_text == "بىرىنچى ئابزاس تېكىستى."
    assert blocks[3].kind == "footnote"


def test_solve_content_page_numbers_piecewise_constant_offset():
    pages = [
        _mk_page(1, is_toc=False, detected_page_number=None),
        _mk_page(2, is_toc=True, detected_page_number=None),
        _mk_page(3, is_toc=False, detected_page_number=None),
        _mk_page(4, is_toc=False, detected_page_number=1),
        _mk_page(5, is_toc=False, detected_page_number=2),
        _mk_page(6, is_toc=False, detected_page_number=3),
        _mk_page(7, is_toc=False, detected_page_number=None),
        _mk_page(8, is_toc=False, detected_page_number=5),
    ]
    solved, modal_offset = solve_content_page_numbers(pages)
    assert modal_offset == 3
    assert solved[1] is None  # cover
    assert solved[2] is None  # toc
    assert solved[3] is None  # front matter before p_content=1
    assert solved[4] == "1"
    assert solved[5] == "2"
    assert solved[6] == "3"
    assert solved[7] == "4"  # interpolated
    assert solved[8] == "5"


def test_solve_content_page_numbers_manual_anchor_takes_precedence():
    pages = [
        _mk_page(1, is_toc=False, detected_page_number=99),
        _mk_page(2, is_toc=True, detected_page_number=None),
        _mk_page(
            3,
            is_toc=False,
            detected_page_number=50,
            content_page_number="1",
            content_page_number_manual=True,
        ),
        _mk_page(4, is_toc=False, detected_page_number=None),
    ]
    solved, _ = solve_content_page_numbers(pages)
    assert solved[1] is None
    assert solved[2] is None
    assert solved[3] == "1"
    assert solved[4] == "2"


def test_extract_book_sections_toc_authority_and_h2_inheritance():
    pages = [
        _mk_page(1, "مۇقاۋا", is_toc=False, content_page_number=None),
        _mk_page(
            2,
            "بىرىنچى قىسىم | 1\nئالتۇن كۈز | 1\nباھار شامىلى | 3",
            is_toc=True,
            content_page_number=None,
        ),
        _mk_page(
            3,
            "# بىرىنچى قىسىم\n\n## ئالتۇن كۈز\n\nبىرىنچى ئەسەر مەزمۇنى.",
            is_toc=False,
            content_page_number="1",
        ),
        _mk_page(
            4,
            "ئىككىنچى بەت تېكىستى داۋامى.",
            is_toc=False,
            content_page_number="2",
        ),
        _mk_page(
            5,
            "## باھار شامىلى\n\nئىككىنچى ئەسەر مەزمۇنى.",
            is_toc=False,
            content_page_number="3",
        ),
    ]
    toc_entries = [
        ("بىرىنچى قىسىم", 1),
        ("ئالتۇن كۈز", 1),
        ("باھار شامىلى", 3),
    ]
    sections = extract_book_sections(pages, toc_entries)
    titles = [s["title"] for s in sections]
    assert "بىرىنچى قىسىم" in titles
    assert "ئالتۇن كۈز" in titles
    assert "باھار شامىلى" in titles

    sec_by_title = {s["title"]: s for s in sections}
    w1 = sec_by_title["ئالتۇن كۈز"]
    w2 = sec_by_title["باھار شامىلى"]
    assert w1["start_page"] == 3
    assert w1["end_page"] == 4
    assert w2["start_page"] == 5
    assert w2["end_page"] == 5


def test_extract_book_sections_header_only_fallback_with_running_header_filter():
    pages = [
        _mk_page(1, "مۇقاۋا بەت تېكىستى.", is_toc=False, content_page_number=None),
        _mk_page(
            2,
            "# كىتاب نامى\n\n## بىرىنچى باب\n\nمەزمۇن 1 تېكىستى.",
            is_toc=False,
            content_page_number="1",
        ),
        _mk_page(
            3,
            "# كىتاب نامى\n\nمەزمۇن 2 تېكىستى.",
            is_toc=False,
            content_page_number="2",
        ),
        _mk_page(
            4,
            "# كىتاب نامى\n\nمەزمۇن 3 تېكىستى.",
            is_toc=False,
            content_page_number="3",
        ),
        _mk_page(
            5,
            "# كىتاب نامى\n\nمەزمۇن 4 تېكىستى.",
            is_toc=False,
            content_page_number="4",
        ),
        _mk_page(
            6,
            "# كىتاب نامى\n\nمەزمۇن 5 تېكىستى.",
            is_toc=False,
            content_page_number="5",
        ),
        _mk_page(
            7,
            "# كىتاب نامى\n\n## ئىككىنچى باب\n\nمەزمۇن 6 تېكىستى.",
            is_toc=False,
            content_page_number="6",
        ),
    ]
    sections = extract_book_sections(pages)
    titles = [s["title"] for s in sections]
    assert "كىتاب نامى" not in titles
    assert titles == ["باش قىسىم", "بىرىنچى باب", "ئىككىنچى باب"]
    assert sections[1]["start_page"] == 2
    assert sections[1]["end_page"] == 6
    assert sections[2]["start_page"] == 7
    assert sections[2]["end_page"] == 7


def test_extract_book_sections_closes_chapter_children_before_next_chapter():
    pages = [
        _mk_page(
            2,
            "# بىرىنچى باب\n\nبىرىنچى باب كىرىش سۆزى.\n\n## شېئىر 1\n\nشېئىر 1 تېكىستى.",
            is_toc=False,
            content_page_number="1",
        ),
        _mk_page(
            3,
            "# ئىككىنچى باب\n\nئىككىنچى باب كىرىش سۆزى.",
            is_toc=False,
            content_page_number="2",
        ),
        _mk_page(
            4,
            "## شېئىر 2\n\nشېئىر 2 تېكىستى.",
            is_toc=False,
            content_page_number="3",
        ),
    ]
    sections = extract_book_sections(pages)
    by_title = {s["title"]: s for s in sections}
    # شېئىر 1 must stop on page 2 before ئىككىنچى باب starts on page 3
    assert by_title["شېئىر 1"]["end_page"] == 2
    assert by_title["بىرىنچى باب"]["end_page"] == 2
    assert by_title["ئىككىنچى باب"]["start_page"] == 3
    assert by_title["ئىككىنچى باب"]["end_page"] == 4


import pytest
from unittest.mock import AsyncMock
from app.services.book_structure_service import BookStructureService


@pytest.mark.asyncio
async def test_analyze_and_persist_respects_manually_unflagged_toc_page():
    mock_session = AsyncMock()
    mock_book = SimpleNamespace(id="b1", title="Test", content_page_offset=0)
    mock_session.get = AsyncMock(return_value=mock_book)

    # Page 2 looks like a ToC page, but an editor manually un-flagged it (updated_by is set)
    toc_like_text = "\n".join(f"ماۋزۇ {i} ........ {i * 5}" for i in range(1, 10))
    p1 = SimpleNamespace(
        page_number=1,
        text="مۇقاۋا",
        is_toc=False,
        updated_by=None,
        detected_page_number=None,
        content_page_number=None,
        content_page_number_manual=False,
    )
    p2 = SimpleNamespace(
        page_number=2,
        text=toc_like_text,
        is_toc=False,
        updated_by="editor@example.com",
        detected_page_number=1,
        content_page_number=None,
        content_page_number_manual=False,
    )
    svc = BookStructureService(mock_session)
    svc.pages_repo.find_by_book = AsyncMock(return_value=[p1, p2])
    svc.sections_repo.replace_for_book = AsyncMock(return_value=[])

    await svc._run_analyze_and_persist("b1")
    assert p2.is_toc is False


def test_numbered_prose_not_classified_as_footnote():
    from app.services.chunking_service import ChunkingService
    from app.utils.text import parse_footnote_line

    assert parse_footnote_line("(1) بىرىنچى نۇقتا تېكىستى.") is None
    assert parse_footnote_line("[2] ئىككىنچى نۇقتا تېكىستى.") is None
    assert parse_footnote_line("① بىرىنچى ئىزاھات.") == ("1", "بىرىنچى ئىزاھات.")
    assert parse_footnote_line("¹ بىرىنچى ئىزاھات.") == ("1", "بىرىنچى ئىزاھات.")
    assert parse_footnote_line("[1]: بىرىنچى ئىزاھات.") == ("1", "بىرىنچى ئىزاھات.")

    text = "كىرىش ئابزاس تېكىستى.\n\n(1) بىرىنچى نۇقتا تېكىستى.\n\n[2] ئىككىنچى نۇقتا تېكىستى."
    blocks = parse_page_blocks(text)
    assert [b.kind for b in blocks] == ["prose", "prose", "prose"]

    svc = ChunkingService(chunk_size=500, chunk_overlap=50)
    chunks = svc.split_text(text)
    assert len(chunks) == 1
    # Ensure numbered paragraphs stay in original order and are not hoisted as footnotes
    idx_intro = chunks[0].find("كىرىش ئابزاس")
    idx_one = chunks[0].find("(1) بىرىنچى نۇقتا")
    idx_two = chunks[0].find("[2] ئىككىنچى نۇقتا")
    assert 0 <= idx_intro < idx_one < idx_two


@pytest.mark.asyncio
async def test_mark_structure_dirty_uses_preserve_active_structure_claim():
    from app.services.book_structure_service import (
        mark_structure_dirty,
        structure_dirty_values,
    )

    vals = structure_dirty_values(status="ready")
    assert vals["structure_milestone"] == "idle"
    assert vals["status"] == "ready"
    assert "CASE" in str(vals["structure_claimed_at"]).upper()

    mock_session = AsyncMock()
    await mark_structure_dirty(mock_session, ["book-1", "book-2"])
    mock_session.execute.assert_called_once()
    stmt_sql = str(mock_session.execute.call_args.args[0])
    assert "CASE" in stmt_sql.upper()
    assert "structure_claimed_at" in stmt_sql


def test_parse_toc_entries_and_reconcile_anthology_entries_with_authors_and_parentheses():
    from app.utils.text import parse_toc_entries

    toc_text = (
        "## مۇندەرىجە\n\n"
        "تۇل خوتۇن ..... ئۆمەرجان ساۋۇت ( 1 )\n"
        "| بۇ چۈش ئەمەس مەمتىمىن ھوشۇر | ( 12 ) |\n"
        "سادا ….. زۇلپىقار (121)\n"
    )
    entries = parse_toc_entries(toc_text)
    assert entries == [
        ("تۇل خوتۇن ئۆمەرجان ساۋۇت", 1),
        ("بۇ چۈش ئەمەس مەمتىمىن ھوشۇر", 12),
        ("سادا زۇلپىقار", 121),
    ]

    pages = [
        _mk_page(
            1,
            "## مۇندەرىجە\n| تۇل خوتۇن ئۆمەرجان ساۋۇت | 1 |\n| بۇ چۈش ئەمەس مەمتىمىن ھوشۇر | 2 |",
            is_toc=True,
        ),
        _mk_page(2, "# تۇل خوتۇن\n\nبىرىنچى ھېكايە تېكىستى.", detected_page_number=1),
        _mk_page(
            3, "# بۇ چۈش ئەمەس\n\nئىككىنچى ھېكايە تېكىستى.", detected_page_number=2
        ),
    ]
    page_map, _ = solve_content_page_numbers(pages, entries[:2])
    for p in pages:
        p.content_page_number = page_map[p.page_number]

    sections = extract_book_sections(
        pages, [("تۇل خوتۇن ئۆمەرجان ساۋۇت", 1), ("بۇ چۈش ئەمەس مەمتىمىن ھوشۇر", 2)]
    )
    leaf_sections = [s for s in sections if s["source"] == "toc_matched"]
    assert len(leaf_sections) == 2
    assert leaf_sections[0]["start_page"] == 2
    assert leaf_sections[1]["start_page"] == 3


def test_is_structural_chapter_title_recognizes_compound_ordinals_and_punctuated_subtitles():
    from app.services.book_structure_service import is_structural_chapter_title

    assert is_structural_chapter_title("ئون بىرىنچى باب تەقدىر") is True
    assert is_structural_chapter_title("ئون ئىككىنچى باب خورلانغان ئەرك") is True
    assert is_structural_chapter_title("ئون ئۈچىنچى باب دېرەكسىز غايىب بولۇش") is True
    assert is_structural_chapter_title("يىگىرمە بەشىنچى باب سەپەر") is True
    assert is_structural_chapter_title("بىرىنچى باب ئانا، نەدە سەن؟") is True
    assert is_structural_chapter_title("ئون بىرىنچى باب خوشلىشىش") is True
    assert is_structural_chapter_title("تۇل خوتۇن ئۆمەرجان ساۋۇت") is False


def test_parse_toc_entries_supports_reverse_dot_leader_and_reverse_pipe_tables():
    from app.utils.text import parse_toc_entries

    toc_text = (
        "# مۇندەرىجە\n\n"
        "* 1 ................... قار گۈللىرى\n"
        "- 13 .................. قەبرە بېشىدىكى چۈش\n"
        "| 28 | روزىمەت خۇشال |\n"
        "* I باب ئاساسىي تارىخىي مەنبەلەر (49)\n"
        "* 77 توردى ھالىم\n"
    )
    entries = parse_toc_entries(toc_text)
    assert entries == [
        ("قار گۈللىرى", 1),
        ("قەبرە بېشىدىكى چۈش", 13),
        ("روزىمەت خۇشال", 28),
        ("I باب ئاساسىي تارىخىي مەنبەلەر", 49),
        ("توردى ھالىم", 77),
    ]


def test_parse_page_blocks_handles_numbered_h2_and_filters_publisher_and_trailing_prose_lines():
    text = (
        "# ياقۇببەگ ھاكىمىيىتى توغرىسىدا\n\n"
        "## 1. ئومۇمىي ئەھۋال\n\n"
        "شىنجاڭ خەلق نەشرىياتى\n\n"
        "بېيجىن - 1958\n\n"
        "× × ×\n\n"
        "بىرىنچى ئابزاس تېكىستى تولۇق جۈملە بىلەن ئاخىرلىشىدۇ.\n\n"
        "ئېنگلىيە مۇستەملىكىچىلىرى بىر تەرەپتىن ئۆزلىرىنىڭ ئوتتۇرا"
    )
    blocks = parse_page_blocks(text)
    headings = [(b.heading_level, b.raw_text) for b in blocks if b.kind == "heading"]
    assert headings == [
        (1, "# ياقۇببەگ ھاكىمىيىتى توغرىسىدا"),
        (2, "## 1. ئومۇمىي ئەھۋال"),
    ]
    assert blocks[-1].kind == "prose"


def test_extract_book_sections_filters_title_stacks_colon_labels_and_recurring_rubrics():
    pages = [
        _mk_page(
            1,
            "# تەپسىر جەۋھەرلىرى\n\n# مۇھەممەد يۈسۈپ\n\n# 2-توم\n\n## تەپسىرنى كۆرۈپ چىققۇچىلار:",
            is_toc=False,
        ),
        _mk_page(
            2,
            "## 1-مەزمۇن ماۋزۇسى\n\n### تەرجىمىسى\n\nئايەت تەرجىمىسى تېكىستى.\n\n### تەپسىرى\n\nتەپسىر تېكىستى.\n\n### مۇھىم نۇقتىلىرى\n\nنۇقتا تېكىستى.",
            is_toc=False,
            content_page_number="1",
        ),
        _mk_page(
            3,
            "## 2-مەزمۇن ماۋزۇسى\n\n### تەرجىمىسى\n\nئىككىنچى تەرجىمە.\n\n### تەپسىرى\n\nئىككىنچى تەپسىر.\n\n### مۇھىم نۇقتىلىرى\n\nئىككىنچى نۇقتا.",
            is_toc=False,
            content_page_number="2",
        ),
        _mk_page(
            4,
            "## 3-مەزمۇن ماۋزۇسى\n\n### تەرجىمىسى\n\nئۈچىنچى تەرجىمە.\n\n### تەپسىرى\n\nئۈچىنچى تەپسىر.\n\n### مۇھىم نۇقتىلىرى\n\nئۈچىنچى نۇقتا.",
            is_toc=False,
            content_page_number="3",
        ),
    ]
    sections = extract_book_sections(pages, book_title="تەپسىر جەۋھەرلىرى")
    titles = [s["title"] for s in sections]
    assert "تەرجىمىسى" not in titles
    assert "تەپسىرى" not in titles
    assert "مۇھىم نۇقتىلىرى" not in titles
    assert "تەپسىرنى كۆرۈپ چىققۇچىلار:" not in titles
    assert "مۇھەممەد يۈسۈپ" not in titles
    assert titles == [
        "باش قىسىم",
        "1-مەزمۇن ماۋزۇسى",
        "2-مەزمۇن ماۋزۇسى",
        "3-مەزمۇن ماۋزۇسى",
    ]


def test_extract_book_sections_nests_chapters_under_parts_and_closes_on_khatime():
    toc = [
        ("بىرىنچى قىسىم ھايات", 1),
        ("بىرىنچى باب دىدار", 2),
        ("ئىككىنچى باب سوۋغا", 5),
        ("ئىككىنچى قىسىم يىراقتا", 8),
        ("بىرىنچى باب سەپەر", 9),
        ("خاتىمە", 12),
    ]
    pages = [
        _mk_page(1, "بىرىنچى قىسىم\n\n# ھايات", content_page_number="1"),
        _mk_page(2, "# بىرىنچى باب دىدار\n\nمەزمۇن 1.", content_page_number="2"),
        _mk_page(5, "# ئىككىنچى باب سوۋغا\n\nمەزمۇن 2.", content_page_number="5"),
        _mk_page(8, "ئىككىنچى قىسىم\n\n# يىراقتا", content_page_number="8"),
        _mk_page(9, "# بىرىنچى باب سەپەر\n\nمەزمۇن 3.", content_page_number="9"),
        _mk_page(12, "# خاتىمە\n\nئاخىرقى خۇلاسە.", content_page_number="12"),
    ]
    sections = extract_book_sections(pages, toc)
    by_idx = {s["section_index"]: s for s in sections}
    part1 = next(s for s in sections if "بىرىنچى قىسىم" in s["title"])
    part2 = next(s for s in sections if "ئىككىنچى قىسىم" in s["title"])
    ch_saper = next(s for s in sections if "سەپەر" in s["title"])
    khatime = next(s for s in sections if s["title"] == "خاتىمە")

    assert part1["level"] == 1
    assert part1["end_page"] == 7
    assert part2["level"] == 1
    assert part2["end_page"] == 11
    assert ch_saper["level"] == 2
    assert by_idx[ch_saper["parent_section_index"]]["title"] == part2["title"]
    assert khatime["level"] == 1
    assert khatime["parent_section_index"] is None


def test_running_headers_detected_after_page_numbers_and_book_title_filtered():
    pages = [
        _mk_page(1, "# ياقۇببەگ ھاكىمىيىتى توغرىسىدا", content_page_number=None),
        _mk_page(
            2,
            "1\n\n[Header] ياقۇببەگ ھاكىمىيىتى توغرىسىدا\n\n## 1. ئومۇمىي ئەھۋال\n\nمەزمۇن 1.",
            content_page_number="1",
        ),
        _mk_page(
            3,
            "2\n\n# ياقۇببەگ ھاكىمىيىتى توغرىسىدا\n\n## 2. خۇلاسە\n\nمەزمۇن 2.",
            content_page_number="2",
        ),
        _mk_page(
            4,
            "3\n\nمەزمۇن 3.\n\n# ياقۇببەگ ھاكىمىيىتى توغرىسىدا",
            content_page_number="3",
        ),
    ]
    sections = extract_book_sections(pages, book_title="ياقۇببەگ ھاكىمىيىتى توغرىسىدا")
    titles = [s["title"] for s in sections]
    assert "ياقۇببەگ ھاكىمىيىتى توغرىسىدا" not in titles
    assert "1. ئومۇمىي ئەھۋال" in titles
    assert "2. خۇلاسە" in titles


def test_chapter_running_headers_do_not_wipe_out_real_chapter_section():
    pages = [
        _mk_page(
            1,
            "# بىرىنچى باب\n\nبىرىنچى بابنىڭ باشلىنىش تېكىستى.",
            content_page_number="1",
        ),
        *[
            _mk_page(
                i,
                f"[Header] بىرىنچى باب\n\nبۇ {i}-بەتنىڭ مەزمۇنى.",
                content_page_number=str(i),
            )
            for i in range(2, 8)
        ],
        _mk_page(
            8,
            "# تارىخىي شەرت-شارائىت\n\nئىككىنچى بۆلەكنىڭ باشلىنىش تېكىستى.",
            content_page_number="8",
        ),
        *[
            _mk_page(
                i,
                f"[Header] تارىخىي شەرت-شارائىت\n\nبۇ {i}-بەتنىڭ مەزمۇنى.",
                content_page_number=str(i),
            )
            for i in range(9, 15)
        ],
    ]
    sections = extract_book_sections(pages)
    titles = [s["title"] for s in sections]
    assert "بىرىنچى باب" in titles
    assert "تارىخىي شەرت-شارائىت" in titles


@pytest.mark.asyncio
async def test_colophon_pipe_page_not_parsed_as_toc_and_healed_on_reprocess():
    from unittest.mock import AsyncMock, MagicMock
    from app.services.book_structure_service import BookStructureService
    from app.utils.text import is_colophon_page, is_toc_page, parse_toc_entries

    colophon_text = (
        "| مەسئۇل مۇھەررىر : ئەخمەتجان ھوشۇر | 1 |\n"
        "| ئادرېسى : بېيجىڭ شەھىرى خېپىڭلى شىمالىي كوچا | 14 |\n"
        "| پوچتا نومۇرى : 1000 | 13 |\n"
        "| تېلېفون نومۇرى : 010-6429 | 62 |\n"
        "| نەشرى : 2010-يىل 8-ئايدا 1-قېتىم نەشر قىلىندى | 2010 |\n"
        "| بېسىلىشى : 2014-يىل 3-ئايدا بېسىلدى | 2014 |\n"
        "| ئۆلچىمى : 880x1230 م م . 32 كەسلەم | 32 |\n"
        "| باسما تاۋىقى : 14 | 125 |\n"
        "| باھاسى : 45.00 يۈەن | 45 |"
    )
    assert is_colophon_page(colophon_text) is True
    assert is_toc_page(colophon_text) is False
    assert parse_toc_entries(colophon_text) == []

    # Verify BookStructureService heals a stale auto-detected is_toc=True on a colophon page
    body_p = _mk_page(1, "تارىخىي رومان تېكىستى داۋاملىشىدۇ.")
    stale_colophon_p = _mk_page(2, colophon_text, is_toc=True)
    stale_colophon_p.updated_by = "surya_local"

    mock_session = AsyncMock()
    mock_book = MagicMock(id="b1", title="باھادىرنامە", content_page_offset=0)
    mock_session.get = AsyncMock(return_value=mock_book)

    svc = BookStructureService(mock_session)
    svc.pages_repo = MagicMock(
        find_by_book=AsyncMock(return_value=[body_p, stale_colophon_p])
    )
    svc.sections_repo = MagicMock(
        replace_for_book=AsyncMock(return_value=[MagicMock()])
    )

    await svc._run_analyze_and_persist("b1")
    assert stale_colophon_p.is_toc is False
    persisted_sections = svc.sections_repo.replace_for_book.call_args.args[1]
    assert all("پوچتا نومۇرى" not in s["title"] for s in persisted_sections)
