"""Unit tests for `UyghurOcrAutoHealer` and `auto_heal_book_pages` (`ocr_auto_heal_service.py`)."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.db.models import Book, Page, PageSpellIssue
from app.services.ocr_auto_heal_service import (
    UyghurOcrAutoHealer,
    auto_heal_book_pages,
)


SAMPLE_LEXICON = {
    # Base nouns + anchors
    "يىگىرمە",
    "چاررۇسىيە",
    "ئەمەلدار",
    "ئەمەلدارلار",
    "ئەمەلدارى",
    "ئەمەلدارلىرى",
    "ئەمەلدارلىقى",
    "لىنىيە",
    "لىنىيىلەر",
    "لىنىيىسى",
    "لىنىيىلىرى",
    "ئۈكەك",
    "ئۈكىكى",
    "ئۈكەككە",
    "كۈن",
    "كۈنلەر",
    "كۈنى",
    # Competing pairs for 1-edit uniqueness veto tests
    "مورا",
    "مورىسى",
    "مورىسىدىكى",
    "مۈرە",
    "مۈرىسى",
    "مۈرىسىدىكى",
    "كۆچۈرۈلدى",
    "ئۆچۈرۈلدى",
    "تىكىلگەن",
    "تېگىلگەن",
    # Roots for dynamic protection tests
    "تېگىن",
    "تېگىنگە",
    "تېكىن",
    "تېكىنلەر",
    "نامزات",
    "نامزاتلار",
    "نامرات",
    "نامراتلار",
    "ئاش",
    "ئېشى",
    "ئېشىم",
    "ئېشىڭ",
    "ئېشىڭلار",
    # Verb infinitives for negative imperative protection
    "ئۆتكۈزمەك",
    "رەنجىمەك",
}


def test_heals_unambiguous_static_and_dynamic_ocr_errors_with_line_numbers():
    healer = UyghurOcrAutoHealer(SAMPLE_LEXICON, protected_words={"دۇنايى"})
    page_text = (
        "بىرىنچى قۇردا يىگىزمە سەر كۈمۈش ۋە چارروسىيە بار.\n"
        "ئىككىنچى قۇردا مۈلكىي ئەمەلدارلىزى ۋە تۆمۈريول لىنىيىلىرىنىك ھەممىسى بار.\n"
        "ئۈچىنچى قۇردا سېپىلنىڭ ئۈگەكلىرى ۋە نەچچە كۈنلەردىگىچە ساقلىدى."
    )

    healed_text, records = healer.heal_page_text(page_text)

    assert "يىگىرمە" in healed_text
    assert "چاررۇسىيە" in healed_text
    assert "ئەمەلدارلىرى" in healed_text
    assert "لىنىيىلىرىنىڭ" in healed_text
    assert "ئۈكەكلىرى" in healed_text
    assert "كۈنلەردىكىچە" in healed_text

    by_orig = {r.original_word: r for r in records}
    assert set(by_orig.keys()) == {
        "يىگىزمە",
        "چارروسىيە",
        "ئەمەلدارلىزى",
        "لىنىيىلىرىنىك",
        "ئۈگەكلىرى",
        "كۈنلەردىگىچە",
    }
    assert by_orig["يىگىزمە"].line_number == 1
    assert by_orig["ئەمەلدارلىزى"].line_number == 2
    assert by_orig["ئەمەلدارلىزى"].rule_label == "-لىزى→-لىرى"
    assert by_orig["لىنىيىلىرىنىك"].line_number == 2
    assert by_orig["لىنىيىلىرىنىك"].verification_source == "dynamic"
    assert by_orig["ئۈگەكلىرى"].line_number == 3
    assert by_orig["ئۈگەكلىرى"].verification_source == "dynamic"
    assert by_orig["كۈنلەردىگىچە"].line_number == 3


def test_vetoes_ambiguous_1edit_competitors_and_protects_valid_morphology():
    healer = UyghurOcrAutoHealer(SAMPLE_LEXICON, protected_words={"دۇنايى"})
    page_text = (
        "مۇرىسىدىكى قارچىغىسى ۋە گۆچۈرۈلدى ۋە تېكىلگەن شىم.\n"
        "تېگىنلەرنىڭ ۋە نامزاتلىرىمىزدىن ۋە دۇنايى خەلىپە.\n"
        "ئۆتكۈزمەڭلەر ۋە رەنجىمەڭلەر ۋە قويغانىدىن كېيىن ئېشىكلىرىنى سۈرتتى."
    )

    healed_text, records = healer.heal_page_text(page_text)

    assert records == []
    assert healed_text == page_text


def test_skips_toc_pipe_rows():
    healer = UyghurOcrAutoHealer(SAMPLE_LEXICON)
    page_text = "| چارروسىيە ھەققىدە | 15 |\nچارروسىيە ھۆكۈمىتى"
    healed_text, records = healer.heal_page_text(page_text)

    assert len(records) == 1
    assert records[0].line_number == 2
    assert healed_text.splitlines()[0] == "| چارروسىيە ھەققىدە | 15 |"
    assert healed_text.splitlines()[1] == "چاررۇسىيە ھۆكۈمىتى"


def test_honorific_following_title_protects_rare_personal_names():
    lex = SAMPLE_LEXICON | {"دونايى", "قۇشبېگى", "ھۆرمەتلىك", "خەلىپە", "تەيجى"}
    healer = UyghurOcrAutoHealer(lex)
    page_text = (
        "دانىيال خوجا، دۇنايى خەلىپە ۋە ھۈرمەتلىك تەيجى بىلەن ياقۇب قوشبېگى كەلدى."
    )

    healed_text, records = healer.heal_page_text(page_text)

    # `دۇنايى` immediately before `خەلىپە` must NOT be overwritten to `دونايى`
    assert "دۇنايى خەلىپە" in healed_text
    # Known salutation `ھۆرمەتلىك` and non-honorific-followed `قۇشبېگى` still heal
    assert "ھۆرمەتلىك تەيجى" in healed_text
    assert "ياقۇب قوشبېگى" not in healed_text
    assert "ياقۇب قۇشبېگى" in healed_text
    assert [r.healed_word for r in records] == ["ھۆرمەتلىك", "قۇشبېگى"]


@pytest.mark.asyncio
async def test_auto_heal_book_pages_updates_dirty_pages_and_syncs_spell_issues():
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.add_all = MagicMock()

    mock_book = MagicMock(spec=Book)
    mock_book.id = "book-42"

    # Page 1 has two auto-heals (`چارروسىيە`, `يىگىزمە`), one ignored typo (`گۆچۈرۈلدى`),
    # and one ambiguous remaining typo (`مۇرىسىدىكى` -> 2 candidates: `مورىسىدىكى`, `مۈرىسىدىكى`).
    page1 = MagicMock(spec=Page)
    page1.id = 101
    page1.book_id = "book-42"
    page1.page_number = 1
    page1.is_toc = False
    page1.text = "چارروسىيە بىلەن يىگىزمە ۋە گۆچۈرۈلدى ھەم مۇرىسىدىكى قارچىغا."

    page2_toc = MagicMock(spec=Page)
    page2_toc.id = 102
    page2_toc.book_id = "book-42"
    page2_toc.page_number = 2
    page2_toc.is_toc = True
    page2_toc.text = "چارروسىيە 15"

    # Page 3 is unmodified, but has an old false-positive open issue (`تېگىنلەرنىڭ`)
    page3_clean = MagicMock(spec=Page)
    page3_clean.id = 103
    page3_clean.book_id = "book-42"
    page3_clean.page_number = 3
    page3_clean.is_toc = False
    page3_clean.text = "تېگىنلەرنىڭ پاكىز بېتى."

    # Existing spell issues across the book:
    iss_healed = MagicMock(spec=PageSpellIssue)
    iss_healed.id = 1
    iss_healed.page_id = 101
    iss_healed.word = "چارروسىيە"
    iss_healed.status = "open"

    iss_ignored = MagicMock(spec=PageSpellIssue)
    iss_ignored.id = 2
    iss_ignored.page_id = 101
    iss_ignored.word = "گۆچۈرۈلدى"
    iss_ignored.status = "ignored"

    iss_ambig_old = MagicMock(spec=PageSpellIssue)
    iss_ambig_old.id = 3
    iss_ambig_old.page_id = 101
    iss_ambig_old.word = "مۇرىسىدىكى"
    iss_ambig_old.status = "open"

    iss_false_pos_unmodified = MagicMock(spec=PageSpellIssue)
    iss_false_pos_unmodified.id = 4
    iss_false_pos_unmodified.page_id = 103
    iss_false_pos_unmodified.word = "تېگىنلەرنىڭ"
    iss_false_pos_unmodified.status = "open"

    res_book = MagicMock()
    res_book.scalar_one_or_none.return_value = mock_book

    res_rules = MagicMock()
    res_rules.fetchall.return_value = []

    res_pages = MagicMock()
    res_pages.scalars.return_value.all.return_value = [page1, page2_toc, page3_clean]

    res_issues = MagicMock()
    res_issues.scalars.return_value.all.return_value = [
        iss_healed,
        iss_ignored,
        iss_ambig_old,
        iss_false_pos_unmodified,
    ]

    mock_session.execute = AsyncMock(
        side_effect=[
            res_book,
            res_rules,
            res_pages,
            res_issues,
            MagicMock(),  # update Page 101
            MagicMock(),  # update corrected PageSpellIssue
            MagicMock(),  # delete stale/false-positive PageSpellIssue
            MagicMock(),  # update Book (auto_correct_milestone='complete' + structure dirty)
        ]
    )

    mock_cfg = MagicMock()
    mock_cfg.get_value = AsyncMock(return_value="true")

    with (
        patch(
            "app.services.ocr_auto_heal_service.SystemConfigsRepository",
            return_value=mock_cfg,
        ),
        patch("app.services.ocr_auto_heal_service.cache_service") as mock_cache,
    ):
        mock_cache.delete = AsyncMock()
        mock_cache.delete_pattern = AsyncMock()
        mock_cache.bump_namespace_version = AsyncMock()

        summary = await auto_heal_book_pages(
            mock_session,
            "book-42",
            updated_by="admin@kitabim.ai",
            lexicon_override=(SAMPLE_LEXICON, set()),
        )

    assert summary.book_id == "book-42"
    assert summary.pages_scanned == 2  # skips ToC page
    assert summary.pages_modified == 1
    assert summary.ocr_heals == 2
    assert summary.total_replacements == 2
    assert summary.issues_marked_corrected == 1
    assert summary.false_positives_cleared == 1

    # Ignored `گۆچۈرۈلدى` must NOT be re-added; only remaining `مۇرىسىدىكى` gets a fresh issue
    mock_session.add_all.assert_called_once()
    recreated = mock_session.add_all.call_args.args[0]
    assert [it.word for it in recreated] == ["مۇرىسىدىكى"]
    mock_session.add.assert_called_once()
    mock_session.commit.assert_awaited_once()
    mock_cache.delete.assert_awaited_once_with("book:book-42")
