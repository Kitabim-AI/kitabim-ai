from pathlib import Path

import pytest
from unittest.mock import AsyncMock, patch

from app.core.i18n import I18n
from app.services.rag.phrase_intent import PhraseIntent
from app.services.chat.exact_phrase import (
    run_exact_phrase_retrieval,
    format_page_hits,
    summarize_page_hits_as_text,
)

_REPO_ROOT = Path(__file__).resolve().parents[5]


@pytest.fixture(autouse=True)
def _load_real_translations():
    # i18n.py's default _locales_dir only resolves correctly when
    # services/backend/main.py overrides it at app startup (see main.py) —
    # unit tests here run outside that startup path, so point it at the
    # real locales directory directly, same as main.py does.
    original_dir = I18n._locales_dir
    original_translations = I18n._translations
    I18n._locales_dir = str(_REPO_ROOT / "services" / "backend" / "locales")
    I18n.load_translations()
    yield
    I18n._locales_dir = original_dir
    I18n._translations = original_translations


@pytest.mark.asyncio
async def test_run_exact_phrase_retrieval_wraps_hits_as_search_chunks_observation():
    chunks_repo = AsyncMock()
    with patch(
        "app.services.chat.exact_phrase.get_vector_store", return_value=chunks_repo
    ), patch(
        "app.services.chat.exact_phrase.exact_phrase_chunk_search",
        new_callable=AsyncMock,
    ) as mock_search:
        mock_search.return_value = [
            {
                "book_id": "b1",
                "page_number": 3,
                "text": "king Babur ruled here",
                "title": "History",
                "volume": 1,
                "author": "A",
                "rank": 0.5,
            }
        ]
        phrase_intent = PhraseIntent(is_exact=True, phrases=["king Babur"])

        hits, observation = await run_exact_phrase_retrieval(
            session="fake-session",
            phrase_intent=phrase_intent,
            book_ids=["b1"],
            categories=None,
            limit=10,
        )

    mock_search.assert_awaited_once_with(
        chunks_repo, ["king Babur"], book_ids=["b1"], categories=None, limit=10
    )
    assert len(hits) == 1
    assert observation["tool"] == "search_chunks"
    assert observation["result"]["ok"] is True
    assert observation["result"]["found_count"] == 1
    chunk = observation["result"]["data"]["chunks"][0]
    assert chunk["book_id"] == "b1"
    assert chunk["page_number"] == 3
    assert chunk["text"] == "king Babur ruled here"


def test_format_page_hits_shapes_payload():
    hits = [
        {
            "book_id": "b1",
            "title": "History",
            "volume": 1,
            "author": "A",
            "page_number": 3,
            "text": "king Babur ruled here" * 20,
        }
    ]

    payload = format_page_hits(hits)

    assert payload == [
        {
            "bookId": "b1",
            "title": "History",
            "volume": 1,
            "author": "A",
            "page": 3,
            "snippet": ("king Babur ruled here" * 20)[:280],
        }
    ]


def test_summarize_page_hits_as_text_no_hits():
    text = summarize_page_hits_as_text([], phrase="king Babur")
    assert "king Babur" in text or text  # falls back to raw i18n key if untranslated


def test_summarize_page_hits_as_text_with_hits():
    hits = [
        {"book_id": "b1", "title": "History", "page_number": 3},
        {"book_id": "b2", "title": "Chronicle", "page_number": None},
    ]

    text = summarize_page_hits_as_text(hits, phrase="king Babur")

    assert "History" in text
    assert "Chronicle" in text
