from app.utils.citation_fixer import fix_malformed_citations

def test_fix_malformed_citations_nested():
    # Pattern 0: Nested markdown
    text = "[بەت14]([مەنبە](ref:book123:14))"
    expected = "[بەت14](ref:book123:14)"
    assert fix_malformed_citations(text) == expected

def test_fix_malformed_citations_missing_bracket_simple():
    # Pattern 1: Missing opening bracket
    text = "ref:26]بەت179 تاريخى نۇرى"
    # Result should be [تاريخى نۇرى، 179 بەت](ref:26:179)
    # The code puts pages_display = '، '.join(['179']) = '179'
    # full_citation = "تاريخى نۇرى، 179 بەت"
    expected = "[تاريخى نۇرى، 179 بەت](ref:26:179)"
    assert fix_malformed_citations(text) == expected

def test_fix_malformed_citations_standalone():
    # Pattern 2: Standalone ref:ID:pages
    text = "See ref:26:178,179 for details"
    expected = "See [مەنبە](ref:26:178,179) for details"
    assert fix_malformed_citations(text) == expected

def test_fix_malformed_citations_none():
    assert fix_malformed_citations(None) is None
    assert fix_malformed_citations("") == ""
