"""
Unit tests for RagService._is_author_or_catalog_query

Tests real Uyghur question patterns that should (or should not) trigger
the author/catalog lookup path.
Run with: pytest packages/backend-core/tests/test_author_catalog_query.py -v
"""


def is_author_or_catalog_query(question: str) -> bool:
    """Inline copy of RagService._is_author_or_catalog_query for isolated testing."""
    if not question:
        return False
    q = question.strip()
    keywords = [
        # Author-related — "who wrote X" / "author of X"
        "مۇئەللىپ", "مۇئەللىپى", "يازغۇچى", "يازغۇچىسى", "ئاپتور", "ئاپتورى",
        "كىم يازغان", "يازغان كىشى", "يازغان كىم",
        "كىم تەرىپىدىن", "يازغانلىقى", "كىمنىڭ", "كىمنىكى",
        # Author-related — "X's books / works"
        "ئەسەر يازغان", "ئەسەرلىرى", "كىتابلىرى",
        # Catalog / book-list related
        "كىتابلىرىڭىز", "كىتاب بارمۇ", "كىتابخانىڭىز",
        "كىتاب تىزىملىكى", "قانچە كىتاب", "نەچچە كىتاب",
        "قايسى كىتابلار", "قايسى ئەسەر",
    ]
    return any(k in q for k in keywords)


is_q = is_author_or_catalog_query


# ---------------------------------------------------------------------------
# "Who is the author of book X?" patterns
# ---------------------------------------------------------------------------

class TestWhoIsAuthor:

    def test_muelip_kim(self):
        # مۇئەللىپى كىم؟ — "who is the author?"
        assert is_q("ئانا يۇرت كىتابىنىڭ مۇئەللىپى كىم؟") is True

    def test_aptor_kim(self):
        # ئاپتورى كىم؟ — "who is the author?"
        assert is_q("بۇ كىتابنىڭ ئاپتورى كىم؟") is True

    def test_yazghuchy_kim(self):
        # يازغۇچىسى كىم؟ — "who is the writer?"
        assert is_q("بۇ رومانىڭ يازغۇچىسى كىم؟") is True

    def test_kim_yazghan(self):
        # كىم يازغان؟ — "who wrote?"
        assert is_q("ئانا يۇرتنى كىم يازغان؟") is True

    def test_yazghan_kishi(self):
        # يازغان كىشى كىم؟ — "who is the person who wrote?"
        assert is_q("بۇ كىتابنى يازغان كىشى كىم؟") is True

    def test_kim_teripdin(self):
        # كىم تەرىپىدىن — "by whom"
        assert is_q("بۇ ئەسەر كىم تەرىپىدىن يېزىلغان؟") is True

    def test_kimnyki(self):
        # كىمنىكى — "whose"
        assert is_q("بۇ كىتاب كىمنىكى؟") is True


# ---------------------------------------------------------------------------
# "What books did author Y write?" patterns
# ---------------------------------------------------------------------------

class TestAuthorBooks:

    def test_kitabliri(self):
        # كىتابلىرى — "their books"
        assert is_q("زوردۇن سابىرنىڭ كىتابلىرى قايسىلار؟") is True

    def test_eserliri(self):
        # ئەسەرلىرى — "their works"
        assert is_q("ئابدۇرەھىم ئۆتكۈرنىڭ ئەسەرلىرى") is True

    def test_eser_yazghan(self):
        # ئەسەر يازغان — "wrote works"
        assert is_q("ئەسەر يازغان مۇئەللىپلار") is True

    def test_yazghanliqi(self):
        # يازغانلىقى — "what they wrote"
        assert is_q("ئۇنىڭ يازغانلىقى نەمە؟") is True


# ---------------------------------------------------------------------------
# Catalog queries — "what books do you have?"
# ---------------------------------------------------------------------------

class TestCatalogQueries:

    def test_kitabliringiz(self):
        assert is_q("كىتابلىرىڭىز قايسىلار؟") is True

    def test_kitab_barmu(self):
        assert is_q("تارىخ ھەققىدە كىتاب بارمۇ؟") is True

    def test_kitabxaningiz(self):
        assert is_q("كىتابخانىڭىزدا نەچچە كىتاب بار؟") is True

    def test_kitab_tizimliqi(self):
        assert is_q("كىتاب تىزىملىكىنى كۆرسەت") is True

    def test_qanche_kitab(self):
        assert is_q("قانچە كىتاب بار؟") is True

    def test_nechchе_kitab(self):
        assert is_q("نەچچە كىتاب ئىندېكسلاندى؟") is True

    def test_qaysi_kitablar(self):
        assert is_q("قايسى كىتابلار بار؟") is True

    def test_qaysi_eser(self):
        assert is_q("قايسى ئەسەر ئوقۇشقا ماس كېلىدۇ؟") is True


# ---------------------------------------------------------------------------
# Should NOT trigger — regular content queries
# ---------------------------------------------------------------------------

class TestShouldNotTrigger:

    def test_regular_content_question(self):
        assert is_q("قارلۇغاچ قانداق پەرۋاز قىلىدۇ؟") is False

    def test_historical_question(self):
        assert is_q("ئۇيغۇر خانلىقى قاچان قۇرۇلغان؟") is False

    def test_definition_question(self):
        assert is_q("ئىسلام دىنى نېمە؟") is False

    def test_empty_string(self):
        assert is_q("") is False

    def test_whitespace_only(self):
        assert is_q("   ") is False

    def test_greeting(self):
        assert is_q("ياخشىمۇسىز") is False
