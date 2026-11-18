import pytest
from unittest.mock import AsyncMock, MagicMock
from app.db.repositories.chunks_repository import ChunksRepository
from app.db.models import Chunk


@pytest.mark.asyncio
async def test_upsert_many():
    session = AsyncMock()
    repo = ChunksRepository(session)

    chunks = [
        {
            "book_id": "b1",
            "page_number": 1,
            "chunk_index": 0,
            "text": "test",
            "embedding": [0.1] * 768,
        }
    ]
    await repo.upsert_many(chunks)

    assert session.execute.called
    assert session.flush.called


@pytest.mark.asyncio
async def test_delete_by_book():
    session = AsyncMock()
    repo = ChunksRepository(session)

    mock_res = MagicMock()
    mock_res.rowcount = 10
    session.execute.return_value = mock_res

    count = await repo.delete_by_book("b1")
    assert count == 10
    assert session.flush.called


@pytest.mark.asyncio
async def test_similarity_search():
    session = AsyncMock()
    repo = ChunksRepository(session)

    mock_row = MagicMock()
    mock_row.book_id = "b1"
    mock_row.page_number = 1
    mock_row.text = "result"
    mock_row.similarity = 0.9
    mock_row.title = "Book 1"
    mock_row.volume = 1
    mock_row.author = "Author"

    mock_res = MagicMock()
    mock_res.fetchall.return_value = [mock_row]
    session.execute.return_value = mock_res

    results = await repo.similarity_search([0.1] * 768, limit=1)

    assert len(results) == 1
    assert results[0]["text"] == "result"
    assert results[0]["similarity"] == 0.9


@pytest.mark.asyncio
async def test_upsert_many_empty():
    session = AsyncMock()
    repo = ChunksRepository(session)
    await repo.upsert_many([])
    assert not session.execute.called


@pytest.mark.asyncio
async def test_delete_by_page():
    session = AsyncMock()
    repo = ChunksRepository(session)
    mock_res = MagicMock()
    mock_res.rowcount = 1
    session.execute.return_value = mock_res

    count = await repo.delete_by_page("b1", 1)
    assert count == 1
    assert session.flush.called


@pytest.mark.asyncio
async def test_find_by_book():
    session = AsyncMock()
    repo = ChunksRepository(session)
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [Chunk(id=1)]
    session.execute.return_value = mock_res

    chunks = await repo.find_by_book("b1")
    assert len(chunks) == 1


@pytest.mark.asyncio
async def test_similarity_search_with_book_ids():
    session = AsyncMock()
    repo = ChunksRepository(session)

    mock_row = MagicMock()
    mock_row.book_id = "b1"
    mock_row.page_number = 1
    mock_row.text = "result"
    mock_row.similarity = 0.9
    mock_row.title = "Book 1"
    mock_row.volume = 1
    mock_row.author = "Author"

    mock_res = MagicMock()
    mock_res.fetchall.return_value = [mock_row]
    session.execute.return_value = mock_res

    results = await repo.similarity_search([0.1] * 768, book_ids=["b1"])
    assert len(results) == 1


@pytest.mark.asyncio
async def test_keyword_search_unscoped():
    session = AsyncMock()
    repo = ChunksRepository(session)

    mock_row = MagicMock()
    mock_row.book_id = "b1"
    mock_row.page_number = 1
    mock_row.text = "result"
    mock_row.rank = 0.045
    mock_row.title = "Book 1"
    mock_row.volume = 1
    mock_row.author = "Author"

    mock_res = MagicMock()
    mock_res.fetchall.return_value = [mock_row]
    session.execute.return_value = mock_res

    results = await repo.keyword_search("سوئال", limit=5)

    assert len(results) == 1
    assert results[0]["text"] == "result"
    assert results[0]["rank"] == 0.045
    # book_ids/threshold aren't part of keyword_search's query params
    call_args = session.execute.await_args
    assert call_args.args[1]["phrase"] == "سوئال"
    assert call_args.args[1]["limit"] == 5
    query_sql = str(call_args.args[0])
    assert query_sql.count("phraseto_tsquery(") == 2
    assert "tsquery_expr" not in query_sql


@pytest.mark.asyncio
async def test_keyword_search_with_book_ids():
    session = AsyncMock()
    repo = ChunksRepository(session)

    mock_row = MagicMock()
    mock_row.book_id = "b1"
    mock_row.page_number = 1
    mock_row.text = "result"
    mock_row.rank = 0.02
    mock_row.title = "Book 1"
    mock_row.volume = 1
    mock_row.author = "Author"

    mock_res = MagicMock()
    mock_res.fetchall.return_value = [mock_row]
    session.execute.return_value = mock_res

    results = await repo.keyword_search("سوئال", book_ids=["b1"], limit=5)

    assert len(results) == 1
    call_args = session.execute.await_args
    assert call_args.args[1]["book_ids"] == ["b1"]
    assert call_args.args[1]["phrase"] == "سوئال"
    assert "phraseto_tsquery(" in str(call_args.args[0])


@pytest.mark.asyncio
async def test_keyword_search_empty_book_ids_fast_exit():
    session = AsyncMock()
    repo = ChunksRepository(session)

    results = await repo.keyword_search("سوئال", book_ids=[])

    assert results == []
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_keyword_search_passes_multi_word_phrase_through_unformatted():
    """Phrase mode hands the raw phrase to phraseto_tsquery() and lets
    Postgres build the tsquery — it must not pre-split/OR-format the words
    in Python the way the old prefix-match query did."""
    session = AsyncMock()
    repo = ChunksRepository(session)
    mock_res = MagicMock()
    mock_res.fetchall.return_value = []
    session.execute.return_value = mock_res

    await repo.keyword_search("king Babur")

    call_args = session.execute.await_args
    assert call_args.args[1]["phrase"] == "king Babur"


@pytest.mark.asyncio
async def test_keyword_search_with_categories():
    session = AsyncMock()
    repo = ChunksRepository(session)

    mock_res = MagicMock()
    mock_res.fetchall.return_value = []
    session.execute.return_value = mock_res

    await repo.keyword_search("سوئال", categories=["history"])

    call_args = session.execute.await_args
    assert call_args.args[1]["categories"] == ["history"]


def test_get_chunks_repository():
    from app.db.repositories.chunks_repository import get_chunks_repository

    session = AsyncMock()
    repo = get_chunks_repository(session)
    assert isinstance(repo, ChunksRepository)


@pytest.mark.asyncio
async def test_similarity_search_unscoped_raises_hnsw_ef_search():
    session = AsyncMock()
    repo = ChunksRepository(session)
    mock_res = MagicMock()
    mock_res.fetchall.return_value = []
    session.execute.return_value = mock_res

    await repo.similarity_search([0.1] * 3072, limit=25)

    statements = [str(c.args[0]) for c in session.execute.await_args_list]
    assert any("SET LOCAL hnsw.ef_search = 200" in s for s in statements)
    final_params = session.execute.await_args_list[-1].args[1]
    assert final_params["inner_limit"] == 200


@pytest.mark.asyncio
async def test_similarity_search_scoped_does_not_touch_ef_search():
    session = AsyncMock()
    repo = ChunksRepository(session)
    mock_res = MagicMock()
    mock_res.fetchall.return_value = []
    session.execute.return_value = mock_res

    await repo.similarity_search([0.1] * 3072, book_ids=["b1"], limit=25)

    statements = [str(c.args[0]) for c in session.execute.await_args_list]
    assert not any("ef_search" in s for s in statements)


@pytest.mark.asyncio
async def test_keyword_search_and_phrases_requires_all_phrases_in_sql():
    session = AsyncMock()
    repo = ChunksRepository(session)
    mock_res = MagicMock()
    mock_res.fetchall.return_value = []
    session.execute.return_value = mock_res

    await repo.keyword_search("بابۇر", and_phrases=["ھىندىستان", "سەمەرقەنت"])

    sql = str(session.execute.await_args_list[-1].args[0])
    params = session.execute.await_args_list[-1].args[1]
    assert (
        "phraseto_tsquery('simple', :phrase)"
        " && phraseto_tsquery('simple', :and_phrase_0)"
        " && phraseto_tsquery('simple', :and_phrase_1)"
    ) in sql
    assert params["phrase"] == "بابۇر"
    assert params["and_phrase_0"] == "ھىندىستان"
    assert params["and_phrase_1"] == "سەمەرقەنت"


@pytest.mark.asyncio
async def test_delete_by_page_deletes_cross_page_overlapping_chunks():
    from sqlalchemy.dialects import postgresql

    session = AsyncMock()
    repo = ChunksRepository(session)
    mock_res = MagicMock()
    mock_res.rowcount = 2
    session.execute.return_value = mock_res

    count = await repo.delete_by_page("b1", 5)
    assert count == 2
    stmt = session.execute.call_args.args[0]
    sql = str(
        stmt.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "chunks.page_number <= 5" in sql
    assert "coalesce(chunks.end_page_number, chunks.page_number) >= 5" in sql.lower()


@pytest.mark.asyncio
async def test_similarity_search_section_ids_matches_parent_chapter_id():
    session = AsyncMock()
    repo = ChunksRepository(session)
    mock_res = MagicMock()
    mock_res.fetchall.return_value = []
    session.execute.return_value = mock_res

    await repo.similarity_search([0.1] * 3072, book_ids=["b1"], section_ids=[42])
    sql = str(session.execute.await_args.args[0])
    params = session.execute.await_args.args[1]
    assert "bs_f.parent_id = ANY(:section_ids)" in sql
    assert params["section_ids"] == [42]


@pytest.mark.asyncio
async def test_replace_for_book_uses_contextual_text_hash_sql_carryover():
    session = AsyncMock()
    repo = ChunksRepository(session)

    count_res = MagicMock()
    count_res.scalar.return_value = 1

    def _fake_exec(stmt, *args, **kwargs):
        if "SELECT count(*)" in str(stmt):
            return count_res
        res = MagicMock()
        res.rowcount = 2
        return res

    session.execute.side_effect = _fake_exec

    remaining = await repo.replace_for_book(
        "b1",
        [
            {
                "page_number": 1,
                "end_page_number": 1,
                "chunk_index": 0,
                "section_id": 10,
                "text": "بىرىنچى بۆلەك",
                "text_hash": "v2_hash_1",
            },
            {
                "page_number": 2,
                "end_page_number": 2,
                "chunk_index": 0,
                "section_id": 11,
                "text": "ئىككىنچى بۆلەك",
                "text_hash": "v2_hash_2",
            },
        ],
    )
    assert remaining == 1
    executed_sqls = [str(c.args[0]) for c in session.execute.call_args_list]
    assert any("text_hash VARCHAR(64) PRIMARY KEY" in s for s in executed_sqls)
    assert any("c.text_hash = old.text_hash" in s for s in executed_sqls)
    assert not any("section_norm_title" in s for s in executed_sqls)


@pytest.mark.asyncio
async def test_inspect_for_book_rolls_up_section_counts_and_applies_filters():
    session = AsyncMock()
    repo = ChunksRepository(session)

    stats_row = MagicMock(
        total_chunks=12,
        embedded_chunks=10,
        unembedded_chunks=2,
        cross_page_chunks=3,
        short_chunks=1,
        oversized_chunks=0,
    )
    stats_res = MagicMock()
    stats_res.first.return_value = stats_row

    parent_sec = MagicMock(
        id=1,
        parent_id=None,
        section_index=0,
        level=1,
        section_type="chapter",
        source="toc",
        title="بىرىنچى قىسىم",
        start_page=5,
        end_page=20,
        chunk_count=0,
    )
    child_sec = MagicMock(
        id=2,
        parent_id=1,
        section_index=1,
        level=2,
        section_type="chapter",
        source="toc",
        title="قاراخانىيلار",
        start_page=5,
        end_page=12,
        chunk_count=5,
    )
    sections_res = MagicMock()
    sections_res.fetchall.return_value = [parent_sec, child_sec]

    chunk_row = MagicMock(
        id=101,
        chunk_index=1,
        page_number=8,
        end_page_number=9,
        section_id=2,
        section_title="بىرىنچى قىسىم › قاراخانىيلار",
        text="ئالدىنقى ئابزاس تەكرارى بىلەن باشلانغان تېكىست.\n\nيېڭى مەزمۇن.",
        char_count=62,
        text_hash="abcd1234",
        has_embedding=True,
        prev_text="بۇرۇنقى جۈملە.\n\nئالدىنقى ئابزاس تەكرارى بىلەن باشلانغان تېكىست.",
        similarity=0.78456,
        content_page_number="4",
        end_content_page_number="5",
        total_matching=1,
    )
    chunks_res = MagicMock()
    chunks_res.fetchall.return_value = [chunk_row]

    session.execute.side_effect = [stats_res, sections_res, chunks_res]

    out = await repo.inspect_for_book(
        "b1",
        page=8,
        section_id=1,
        filter_type="cross_page",
        text_query="50%_سۆز",
        query_embedding=[0.1, 0.2, 0.3],
        skip=0,
        limit=50,
    )

    assert out["stats"]["total_chunks"] == 12
    assert out["stats"]["sections_count"] == 2
    # Parent section chunk_count rolled up child_sec's 5 chunks
    assert out["sections"][0]["id"] == 1
    assert out["sections"][0]["chunk_count"] == 5
    assert out["sections"][1]["id"] == 2
    assert out["sections"][1]["chunk_count"] == 5

    assert out["total_matching"] == 1
    assert len(out["chunks"]) == 1
    c = out["chunks"][0]
    assert c["id"] == 101
    assert c["page_number"] == 8
    assert c["end_page_number"] == 9
    assert c["content_page_number"] == "4"
    assert c["end_content_page_number"] == "5"
    assert c["similarity"] == 0.7846

    chunk_query_call = session.execute.call_args_list[2]
    chunk_sql = str(chunk_query_call.args[0])
    chunk_params = chunk_query_call.args[1]
    assert "bc.end_page_number > bc.page_number" in chunk_sql
    assert "bc.similarity DESC NULLS LAST" in chunk_sql
    assert chunk_params["ilike_q"] == "%50\\%\\_سۆز%"
