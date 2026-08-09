import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.rag.answer_builder import Document

from app.services.rag.utils import (
    is_current_volume_query,
    is_current_page_query,
    normalize_uyghur,
    is_author_or_catalog_query,
    entity_matches_question,
    is_islam_or_quran_query,
    is_who_is_query,
)
from app.services.rag.answer_builder import format_document
from app.services.rag.handlers.catalog import CatalogHandler


def test_is_current_volume_query():
    assert is_current_volume_query("ئۇشبۇ تومدا بارمۇ؟") is True
    assert is_current_volume_query("") is False
    assert is_current_volume_query(None) is False


def test_is_current_page_query():
    assert is_current_page_query("بۇ بەتتە نېمە بار؟") is True
    assert is_current_page_query("") is False
    assert is_current_page_query(None) is False


def test_normalize_uyghur():
    orig = "ئېيى"
    norm = normalize_uyghur(orig)
    assert norm == normalize_uyghur("ئىيى")


def test_is_author_or_catalog_query():
    assert is_author_or_catalog_query("بۇ كىتابنىڭ ئاپتورى كىم؟") is True
    assert is_author_or_catalog_query("بەت 10 نى ئوقۇ") is False


def test_entity_matches_question():
    assert entity_matches_question("زوردۇن سابىر", "زوردۇن سابىرنىڭ ئەسىرى") is True
    assert entity_matches_question("زوردۇن سابىر", "يازغۇچى كىم؟") is False


def test_entity_matches_question_quotes_grant_single_word_match():
    """A quoted single-word title in a multi-word question matches entity_matches_question."""
    question = "مەن «ھايات» دەيدىغان سۆزنى ئاڭلىدىم"
    assert entity_matches_question("ھايات", question) is True


def test_entity_matches_question_sentence_start_still_matches_single_word():
    question = "ھايات توغرىسىدا نېمە بىلىسەن؟"
    assert entity_matches_question("ھايات", question) is True


def test_format_document():
    doc = Document(
        page_content="Content",
        metadata={
            "book_id": "b1",
            "title": "Title",
            "author": "Author",
            "volume": 1,
            "page": 10,
        },
    )
    formatted = format_document(doc)
    assert "Content" in formatted
    assert "Title" in formatted
    assert "BookID: b1" in formatted


@pytest.mark.asyncio
async def test_build_catalog_context_title_match():
    session = AsyncMock()

    # 1st execute is select Book.title to get all title candidates
    mock_titles = MagicMock()
    mock_titles.fetchall.return_value = [("ئانا يۇرت",)]

    # 2nd execute is select title, author, volume, etc. for matched title
    mock_books = MagicMock()
    mock_books.fetchall.return_value = [
        MagicMock(
            title="ئانا يۇرت",
            author="زوردۇن سابىر",
            volume=1,
            total_pages=500,
            status="ready",
        )
    ]

    session.execute.side_effect = [mock_titles, mock_books]

    ctx, count = await CatalogHandler._build_catalog_context(
        "ئانا يۇرتتا نېمە بار؟", session
    )
    assert "ئانا يۇرت" in ctx
    assert "زوردۇن سابىر" in ctx
    assert count == 1


def test_detect_intent():
    from app.services.rag.agent.llm_routed_handler import _detect_intent
    from app.services.rag.context import QueryContext

    ctx = MagicMock(spec=QueryContext)
    ctx.current_page = None

    questions = [
        "ئانا يۇرت رومانىنىڭ ئاپتورى كىم؟",
        "ئانا يۇرت رومانى كىمنىڭ؟",
        "ئانا يۇرت رومانىنى كىم يازغان؟",
        "ئانا يۇرت رومانى قايسى داڭلىق يازغۇچىنىڭ؟",
        "ئانا يۇرت كىمنىڭ؟",
        "ئانا يۇرتنىڭ ئاپتورى كىم؟",
    ]
    for q in questions:
        assert _detect_intent(q, ctx) == "content_search"


def test_grade_context_local_grading():
    from app.services.rag.agent.llm_routed_handler import _grade_context

    # Simulate two search calls.
    # Search A: high similarity scores (e.g. 0.95, 0.90) -> top_score = 0.95, floor = 0.8075 (keeps both)
    # Search B: lower similarity scores (e.g. 0.78, 0.77) -> top_score = 0.78, floor = 0.6630 (keeps both)
    # Under global grading, Search B would be completely pruned because 0.78 < (0.95 * 0.85 = 0.8075).
    # Under local grading, Search B keeps both chunks.
    observations = [
        {
            "tool": "search_chunks",
            "result": {
                "ok": True,
                "data": {
                    "chunks": [
                        {
                            "book_id": "book_a",
                            "page": 10,
                            "text": "Content A1 from book A",
                            "score": 0.95,
                            "title": "Book A",
                        },
                        {
                            "book_id": "book_a",
                            "page": 11,
                            "text": "Content A2 from book A",
                            "score": 0.90,
                            "title": "Book A",
                        },
                    ]
                },
            },
        },
        {
            "tool": "search_chunks",
            "result": {
                "ok": True,
                "data": {
                    "chunks": [
                        {
                            "book_id": "book_b",
                            "page": 20,
                            "text": "Content B1 from book B",
                            "score": 0.78,
                            "title": "Book B",
                        },
                        {
                            "book_id": "book_b",
                            "page": 21,
                            "text": "Content B2 from book B",
                            "score": 0.77,
                            "title": "Book B",
                        },
                    ]
                },
            },
        },
    ]

    graded_context, before_count, after_count = _grade_context(observations)

    # 4 chunks before, 4 chunks after
    assert before_count == 4
    assert after_count == 4

    assert "Book A" in graded_context
    assert "Book B" in graded_context
    assert "Content A1" in graded_context
    assert "Content B1" in graded_context


def test_build_instructions_dynamic_numbering():
    from app.services.rag.answer_builder import build_instructions

    # 1. Test Permissive Mode with all extra flags
    instr_permissive = build_instructions(
        strict_no_answer=False,
        suppress_page_notice=True,
        is_global=True,
        has_categories=True,
    )

    # Verify numbering sequence contains up to 11
    lines = [line.strip() for line in instr_permissive.split("\n") if line.strip()]
    numbered_lines = [line for line in lines if line[0].isdigit() and "." in line[:3]]

    # Extract just the numbers
    numbers = [int(line.split(".")[0]) for line in numbered_lines]

    # They should be strictly sequential starting at 1
    assert numbers == list(range(1, len(numbers) + 1))
    assert len(numbers) == 13

    # Check key contents
    assert "Markdown structural characters" in instr_permissive
    assert "omit the 'ref:' link and cite inline as" in instr_permissive
    assert "Librarian (زېرەكچاق)" in instr_permissive
    assert "multiple volumes" in instr_permissive.lower()

    # 2. Test Strict Mode with all extra flags
    instr_strict = build_instructions(
        strict_no_answer=True,
        suppress_page_notice=True,
        is_global=True,
        has_categories=True,
    )

    lines_strict = [line.strip() for line in instr_strict.split("\n") if line.strip()]
    numbered_lines_strict = [
        line for line in lines_strict if line[0].isdigit() and "." in line[:3]
    ]
    numbers_strict = [int(line.split(".")[0]) for line in numbered_lines_strict]

    # They should be strictly sequential starting at 1 (9 rules in strict mode)
    assert numbers_strict == list(range(1, len(numbers_strict) + 1))
    assert len(numbers_strict) == 9

    assert "Markdown structural characters" in instr_strict
    assert (
        "format citations in Uyghur as a markdown link using the EXACT author"
        in instr_strict
    )
    assert "multiple volumes" in instr_strict.lower()


def test_is_islam_or_quran_query():
    assert is_islam_or_quran_query("ئىسلامدىكى بەش پەرز نېمە؟") is True
    assert is_islam_or_quran_query("قۇرئاندىكى بەقەرە سۈرىسى") is True
    assert is_islam_or_quran_query("What does the Quran say about charity?") is True
    assert is_islam_or_quran_query("ئانا يۇرت رومانى قاچان يېزىلغان؟") is False
    assert is_islam_or_quran_query("What is the temperature in Paris?") is False


def test_is_who_is_query():
    # English queries
    assert is_who_is_query("Who is Mahmud Kashgari?") is True
    assert is_who_is_query("who was Yusuf?") is True
    assert is_who_is_query("Whose book is this?") is False
    assert is_who_is_query("who's the author?") is True
    assert is_who_is_query("What is the meaning of life?") is False

    # Uyghur queries
    assert is_who_is_query("ئۆمەرجان كىم؟") is True
    assert is_who_is_query("ئۇ كىمدۇر؟") is True
    assert is_who_is_query("كىم ئۇ ئۆمەرجان؟") is True
    assert is_who_is_query("يۈسۈپ خاس ھاجىپ كىم بولغان؟") is True
    assert is_who_is_query("ئانا يۇرت رومانى كىمنىڭ ئەسىرى؟") is False
    assert is_who_is_query("ئانا يۇرت كىمنىڭ؟") is False
    assert is_who_is_query("ئانا يۇرت رومانى قاچان يېزىلغان؟") is False
    assert is_who_is_query("ئالىم دېگەن ئىسىم مەنىسى نېمە؟") is False
