from app.db.repositories.dictionary_repository import (
    _build_strict_term_where,
)
from app.db.models import HistoryDictionary


def test_strict_term_where_excludes_loose_common_word_branch():
    # Regression for a 2026-08-03 production incident: the shared search-tolerant
    # matcher's "shares one common word + similarity > 0.4" branch caused
    # extraction dedup to false-match "تارىخى رەشىدى" (a book) against "رىم تارىخى"
    # ("History of Rome", similarity 0.47) and "سۇلتان سەئىدخان" (a person)
    # against the bare word "سۇلتان" (similarity 0.5) — silently discarding
    # every extracted entity as if it already existed. The strict matcher used
    # for dedup must never match on a single shared common word.
    clause = _build_strict_term_where(HistoryDictionary.term, "تارىخى رەشىدى")
    compiled = str(clause.compile(compile_kwargs={"literal_binds": True}))
    assert "0.4" not in compiled
    assert "0.7" in compiled
