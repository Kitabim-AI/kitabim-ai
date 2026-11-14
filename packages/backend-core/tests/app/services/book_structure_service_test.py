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
    assert titles == ["مۇقەددىمە", "بىرىنچى باب", "ئىككىنچى باب"]
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
