"""
Unit tests for RagService._entity_matches_question

Tests real Uyghur question patterns for author and book title matching.
Run with: pytest packages/backend-core/tests/test_entity_matching.py -v
"""
import pytest


def match(entity: str, question: str) -> bool:
    """Inline copy of RagService._entity_matches_question for isolated testing."""
    entity_words = entity.strip().split()
    if len(entity_words) < 2:
        return False
    q_words = question.strip().split()
    return all(
        any(q_word.startswith(e_word) for q_word in q_words)
        for e_word in entity_words
    )


# ---------------------------------------------------------------------------
# Author matching — "what books did Y write?"
# ---------------------------------------------------------------------------

class TestAuthorMatching:

    def test_author_with_genitive_suffix(self):
        # زوردۇن سابىرنىڭ كىتابلىرى — "Zordun Sabir's books"
        assert match("زوردۇن سابىر", "زوردۇن سابىرنىڭ كىتابلىرى قايسىلار؟") is True

    def test_author_with_plural_possessive(self):
        # ئابدۇرەھىم ئۆتكۈرنىڭ ئەسەرلىرى — "Abdureyim Ötkür's works"
        assert match("ئابدۇرەھىم ئۆتكۈر", "ئابدۇرەھىم ئۆتكۈرنىڭ ئەسەرلىرى نەملەر؟") is True

    def test_author_bare_name_in_question(self):
        # Author name appears without suffix
        assert match("زوردۇن سابىر", "زوردۇن سابىر نىڭ كىتابلىرى") is True

    def test_author_with_topic_suffix(self):
        # Y ھەققىدە — "about Y"
        assert match("مۇھەممەد ئىمىن", "مۇھەممەد ئىمىننىڭ يازغان كىتابلىرى") is True

    def test_author_not_in_question(self):
        assert match("زوردۇن سابىر", "بۇ كىتابنىڭ مۇئەللىپى كىم؟") is False

    def test_author_partial_first_word_only(self):
        # Only first name matches — should fail (requires ALL words)
        assert match("زوردۇن سابىر", "زوردۇن يازغان كىتابلار") is False

    def test_single_word_author_always_false(self):
        # Single-word entities are skipped to avoid false positives
        assert match("سابىر", "سابىرنىڭ كىتابلىرى") is False


# ---------------------------------------------------------------------------
# Book title matching — "who is the author of book X?"
# ---------------------------------------------------------------------------

class TestBookTitleMatching:

    def test_book_title_with_genitive(self):
        # ئانا يۇرت كىتابىنىڭ مۇئەللىپى كىم؟ — "who is the author of Ana Yurt?"
        assert match("ئانا يۇرت", "ئانا يۇرتنىڭ مۇئەللىپى كىم؟") is True
        assert match("ئانا يۇرت", "ئانا يۇرتنىڭ ئاپتورى كىم؟") is True

    def test_book_title_with_accusative_suffix(self):
        # X نى كىم يازغان؟ — "who wrote X?"
        assert match("ئانا يۇرت", "ئانا يۇرتنى كىم يازغان؟") is True
        assert match("ئانا يۇرت", "ئانا يۇرت كىمنىڭ؟") is True

    def test_book_title_bare(self):
        assert match("ئانا يۇرت", "ئانا يۇرت ھەققىدە مەلۇمات بەر") is True

    def test_book_title_not_in_question(self):
        assert match("ئانا يۇرت", "بۇ كىتابنى كىم يازغان؟") is False

    def test_book_title_with_locative_suffix(self):
        # X دا — "in X"
        assert match("ئانا يۇرت", "ئانا يۇرتتا قانداق مەزمۇنلار بار؟") is True


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_empty_entity(self):
        assert match("", "زوردۇن سابىرنىڭ كىتابلىرى") is False

    def test_empty_question(self):
        assert match("زوردۇن سابىر", "") is False

    def test_three_word_entity_all_match(self):
        assert match("ئابدۇللا تايجى خان", "ئابدۇللا تايجى خاننىڭ تارىخى") is True

    def test_three_word_entity_partial_match(self):
        # Middle word missing
        assert match("ئابدۇللا تايجى خان", "ئابدۇللا خاننىڭ تارىخى") is False

    def test_entity_words_out_of_order(self):
        # Both words present but in different order — still matches (order not required)
        assert match("زوردۇن سابىر", "سابىرنىڭ زوردۇن دېگەن كىتابى") is True
