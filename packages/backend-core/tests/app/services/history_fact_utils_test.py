from app.services.history_fact_utils import (
    fact_text_similarity,
    find_deterministic_duplicate,
    cosine_similarity,
    merge_citation,
    bootstrap_legacy_facts,
)


def test_fact_text_similarity_normalizes_spelling_variants():
    a = "مىرزا ھەيدەر كۆرەگاننىڭ «تارىخى رەشىدى» ئەسىرى"
    b = "مىرزا ھەيدەر كۆرەگاننىڭ «تارىخى رەشىدىي» ئەسىرى"
    assert fact_text_similarity(a, b) >= 0.85


def test_fact_text_similarity_distinct_facts_low_score():
    a = "ياركەند خانلىقىنىڭ خانى."
    b = "ھىجرىيە 915-يىلى تۇغۇلغان."
    assert fact_text_similarity(a, b) < 0.5


def test_find_deterministic_duplicate_returns_matching_id():
    existing = [
        {
            "id": 1,
            "text": "تارىخى رەشىدى ئۇنىڭ نامىغا بېغىشلانغان.",
            "status": "active",
        },
        {"id": 2, "text": "ھىجرىيە 915-يىلى تۇغۇلغان.", "status": "active"},
    ]
    match = find_deterministic_duplicate(
        "تارىخى رەشىدىي ئۇنىڭ نامىغا بېغىشلانغان.", existing
    )
    assert match == 1


def test_find_deterministic_duplicate_ignores_non_active_facts():
    existing = [
        {
            "id": 1,
            "text": "تارىخى رەشىدى ئۇنىڭ نامىغا بېغىشلانغان.",
            "status": "rejected",
        },
    ]
    match = find_deterministic_duplicate(
        "تارىخى رەشىدىي ئۇنىڭ نامىغا بېغىشلانغان.", existing
    )
    assert match is None


def test_find_deterministic_duplicate_no_match_returns_none():
    existing = [{"id": 1, "text": "ياركەند خانلىقىنىڭ خانى.", "status": "active"}]
    match = find_deterministic_duplicate("ھىجرىيە 915-يىلى تۇغۇلغان.", existing)
    assert match is None


def test_cosine_similarity_identical_vectors_returns_one():
    v = [1.0, 2.0, 3.0]
    assert abs(cosine_similarity(v, v) - 1.0) < 1e-9


def test_cosine_similarity_orthogonal_vectors_returns_zero():
    assert abs(cosine_similarity([1.0, 0.0], [0.0, 1.0])) < 1e-9


def test_cosine_similarity_empty_vector_returns_zero():
    assert cosine_similarity([], [1.0]) == 0.0


def test_merge_citation_unions_pages_for_same_book():
    fact = {
        "id": 1,
        "text": "x",
        "citations": [{"book_id": "b1", "book_title": "T", "pages": [10, 12]}],
    }
    merge_citation(fact, {"book_id": "b1", "book_title": "T", "pages": [12, 15]})
    assert fact["citations"][0]["pages"] == [10, 12, 15]


def test_merge_citation_appends_new_book():
    fact = {
        "id": 1,
        "text": "x",
        "citations": [{"book_id": "b1", "book_title": "T", "pages": [10]}],
    }
    merge_citation(fact, {"book_id": "b2", "book_title": "U", "pages": [5]})
    assert len(fact["citations"]) == 2


def test_bootstrap_legacy_facts_returns_existing_facts_unchanged():
    existing = [
        {
            "id": 1,
            "text": "x",
            "citations": [],
            "status": "active",
            "conflict_group": None,
        }
    ]
    assert bootstrap_legacy_facts(existing, "some definition") == existing


def test_bootstrap_legacy_facts_wraps_definition_when_empty():
    result = bootstrap_legacy_facts([], "ياركەند خانلىقىنىڭ خانى.")
    assert len(result) == 1
    assert result[0]["text"] == "ياركەند خانلىقىنىڭ خانى."
    assert result[0]["status"] == "active"


def test_bootstrap_legacy_facts_returns_empty_for_blank_definition():
    assert bootstrap_legacy_facts([], None) == []
    assert bootstrap_legacy_facts([], "  ") == []
