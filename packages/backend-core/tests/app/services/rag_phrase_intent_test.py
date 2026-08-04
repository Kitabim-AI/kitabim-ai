import pytest

from app.services.rag.phrase_intent import detect_phrase_intent


def test_plain_question_is_not_exact():
    result = detect_phrase_intent("who is king Babur")
    assert result.is_exact is False
    assert result.phrases == []


def test_straight_double_quotes_trigger_exact():
    result = detect_phrase_intent('what does "king Babur" mean')
    assert result.is_exact is True
    assert result.phrases == ["king Babur"]


def test_guillemets_trigger_exact():
    result = detect_phrase_intent("«king Babur» heqqide nemə deyilgen?")
    assert result.is_exact is True
    assert result.phrases == ["king Babur"]


def test_curly_quotes_trigger_exact():
    result = detect_phrase_intent("what does “king Babur” mean")
    assert result.is_exact is True
    assert result.phrases == ["king Babur"]


def test_multiple_quoted_phrases_are_all_returned():
    result = detect_phrase_intent('find pages with "king Babur" and "Samarkand"')
    assert result.is_exact is True
    assert result.phrases == ["king Babur", "Samarkand"]


def test_explicit_exact_phrase_flag_without_quotes():
    result = detect_phrase_intent("king Babur", exact_phrase_flag=True)
    assert result.is_exact is True
    assert result.phrases == ["king Babur"]


def test_explicit_flag_is_ignored_when_text_is_empty():
    result = detect_phrase_intent("   ", exact_phrase_flag=True)
    assert result.is_exact is False
    assert result.phrases == []


@pytest.mark.parametrize(
    "question",
    [
        'find pages with "king Babur"',
        'which pages mention "king Babur"',
        'show me where "king Babur" appears',
        'Find Pages With "king Babur"',
    ],
)
def test_page_finding_phrasing_is_classified(question):
    result = detect_phrase_intent(question)
    assert result.is_exact is True
    assert result.is_page_finding is True


def test_quoted_phrase_without_page_finding_wording_is_not_page_finding():
    result = detect_phrase_intent('what does "king Babur" mean')
    assert result.is_exact is True
    assert result.is_page_finding is False


def test_no_quotes_and_no_flag_is_not_page_finding():
    result = detect_phrase_intent("who is king Babur")
    assert result.is_page_finding is False
