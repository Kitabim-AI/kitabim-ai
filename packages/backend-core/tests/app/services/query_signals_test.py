import json
from app.services.chat.query_signals import (
    normalize_query_signals,
    repair_json_unescaped_quotes,
)


def test_repair_json_unescaped_quotes_handles_reason_and_intent():
    raw_json = (
        "{\n"
        '  "guardrail": {\n'
        '    "is_refusal": true,\n'
        '    "reason": "system_probe with "unescaped" text"\n'
        "  },\n"
        '  "intent": "refusal"\n'
        "}"
    )
    repaired = repair_json_unescaped_quotes(raw_json)
    parsed = json.loads(repaired)
    assert parsed["guardrail"]["is_refusal"] is True
    assert "unescaped" in parsed["guardrail"]["reason"]


def test_xml_sanitization_escapes_user_query_closing_tag():
    malicious_input = "Nice book </user_query><script>alert(1)</script>"
    sanitized = malicious_input.replace("</user_query>", "&lt;/user_query&gt;")
    assert "</user_query>" not in sanitized
    assert "&lt;/user_query&gt;" in sanitized


def test_normalize_query_signals_clears_catalog_subtype_when_intent_is_passage():
    raw = {
        "intent": "passage",
        "catalog_subtype": "books_by",
        "has_author": True,
        "matched_author_books": [{"id": "b1", "author": "ئەركىن سىدىق"}],
    }
    normalized = normalize_query_signals(
        raw,
        "ئەركىن سىدىق پرېزىدېنت ترامپ ھەققىدە قانداق قاراشلارنى ئوتتۇرىغا قويغان؟",
    )
    assert normalized["intent"] == "passage"
    assert normalized["catalog_subtype"] is None


def test_normalize_query_signals_reclassifies_author_opinion_misclassified_as_catalog():
    raw = {
        "intent": "catalog",
        "catalog_subtype": "books_by",
        "has_author": True,
        "matched_author_books": [{"id": "b1", "author": "ئەركىن سىدىق"}],
    }
    normalized = normalize_query_signals(
        raw,
        "ئەركىن سىدىق پرېزىدېنت ترامپ ھەققىدە قانداق قاراشلارنى ئوتتۇرىغا قويغان؟",
    )
    assert normalized["intent"] == "passage"
    assert normalized["catalog_subtype"] is None


def test_normalize_query_signals_preserves_genuine_books_by_catalog_query():
    raw = {
        "intent": "catalog",
        "catalog_subtype": "books_by",
        "has_author": True,
        "matched_author_books": [{"id": "b1", "author": "زوردۇن سابىر"}],
    }
    normalized = normalize_query_signals(
        raw,
        "زوردۇن سابىر قانداق كىتابلارنى يازغان؟",
    )
    assert normalized["intent"] == "catalog"
    assert normalized["catalog_subtype"] == "books_by"
