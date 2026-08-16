import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from app.db.repositories.graph_repository import GraphRepository


@pytest_asyncio.fixture(autouse=True)
async def cleanup_graph_driver():
    """Ensure class-level graph driver is clean before and after each test."""
    GraphRepository._driver = None
    yield
    await GraphRepository.close_driver()


def _mock_driver_session(mock_session):
    mock_driver = MagicMock()
    mock_driver.close = AsyncMock()
    mock_driver.session.return_value = mock_session
    return mock_driver


@pytest.mark.asyncio
async def test_graph_repository_init_constraints():
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_driver = _mock_driver_session(mock_session)

    with patch(
        "app.db.repositories.graph_repository.AsyncGraphDatabase.driver",
        return_value=mock_driver,
    ):
        repo = GraphRepository()
        await repo.init_constraints()

        # DROP entity_name_unique, CREATE entity_id_unique, 2 entity btree indexes,
        # 1 fulltext index, 4 relationship indexes, 1 vector index
        assert mock_session.run.call_count == 10
        statements = [c[0][0] for c in mock_session.run.call_args_list]
        assert any("DROP CONSTRAINT entity_name_unique" in s for s in statements)
        assert any("CREATE CONSTRAINT entity_id_unique" in s for s in statements)
        assert any("CREATE FULLTEXT INDEX entity_search_idx" in s for s in statements)
        assert any(
            "CREATE VECTOR INDEX entity_profile_embedding_idx" in s for s in statements
        )

        await GraphRepository.close_driver()
        assert mock_driver.close.called


@pytest.mark.asyncio
async def test_graph_repository_query_subgraph():
    mock_result = AsyncMock()
    mock_result.data.return_value = [{"source": "A", "rel": "KNOWS", "target": "B"}]
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.run.return_value = mock_result
    mock_driver = _mock_driver_session(mock_session)

    with patch(
        "app.db.repositories.graph_repository.AsyncGraphDatabase.driver",
        return_value=mock_driver,
    ):
        repo = GraphRepository()
        records = await repo.query_subgraph(["A", "B"])

        assert mock_session.run.called
        call_args = mock_session.run.call_args[0]
        call_kwargs = mock_session.run.call_args[1]
        assert "e.canonical_name IN $entity_names" in call_args[0]
        assert (
            "any(alt IN COALESCE(e.aliases, []) WHERE alt IN $entity_names)"
            in call_args[0]
        )
        assert "r.book_id IN $book_ids" in call_args[0]
        assert call_kwargs["entity_names"] == ["A", "B"]
        assert call_kwargs["book_ids"] is None
        assert records == [{"source": "A", "rel": "KNOWS", "target": "B"}]


@pytest.mark.asyncio
async def test_graph_repository_upsert_entities_bulk():
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_driver = _mock_driver_session(mock_session)

    with patch(
        "app.db.repositories.graph_repository.AsyncGraphDatabase.driver",
        return_value=mock_driver,
    ):
        repo = GraphRepository()
        entities = [
            {
                "id": "uuid-1",
                "canonical_name": "E1",
                "aliases": ["E1"],
                "type": "Person",
                "subtype": None,
                "scope": "nonfiction",
                "book_id": None,
            }
        ]
        await repo.upsert_entities_bulk(entities)

        assert mock_session.run.called
        call_args = mock_session.run.call_args[0]
        call_kwargs = mock_session.run.call_args[1]
        assert "MERGE (e:Entity {id: e_data.id})" in call_args[0]
        assert call_kwargs["entities_data"][0]["id"] == "uuid-1"
        assert call_kwargs["entities_data"][0]["canonical_name"] == "E1"
        assert call_kwargs["entities_data"][0]["resolution_status"] == "unresolved"


@pytest.mark.asyncio
async def test_graph_repository_connect_entities_bulk_unions_chunk_refs():
    """A re-run must union chunk_refs with what's already on the edge, not overwrite it."""
    mock_read_result = AsyncMock()
    mock_read_result.data.return_value = [
        {
            "source_id": "s1",
            "rel_type": "SON_OF",
            "target_id": "t1",
            "book_id": "book-1",
            "chunk_refs": ["book-1:1:0"],
        }
    ]
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.run.side_effect = [mock_read_result, AsyncMock()]
    mock_driver = _mock_driver_session(mock_session)

    with patch(
        "app.db.repositories.graph_repository.AsyncGraphDatabase.driver",
        return_value=mock_driver,
    ):
        repo = GraphRepository()
        relations = [
            {
                "source_id": "s1",
                "rel_type": "SON_OF",
                "target_id": "t1",
                "book_id": "book-1",
                "chunk_refs": ["book-1:2:0"],
            }
        ]
        await repo.connect_entities_bulk(relations)

        assert mock_session.run.call_count == 2
        write_kwargs = mock_session.run.call_args_list[1][1]
        normalized = write_kwargs["relations_data"][0]
        assert normalized["chunk_refs"] == ["book-1:2:0"]
        assert set(normalized["merged_chunk_refs"]) == {"book-1:1:0", "book-1:2:0"}


@pytest.mark.asyncio
async def test_graph_repository_connect_entities_bulk_no_existing_edge():
    mock_read_result = AsyncMock()
    mock_read_result.data.return_value = []
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.run.side_effect = [mock_read_result, AsyncMock()]
    mock_driver = _mock_driver_session(mock_session)

    with patch(
        "app.db.repositories.graph_repository.AsyncGraphDatabase.driver",
        return_value=mock_driver,
    ):
        repo = GraphRepository()
        relations = [
            {
                "source_id": "s1",
                "rel_type": "SON_OF",
                "target_id": "t1",
                "book_id": "book-1",
                "chunk_refs": ["book-1:1:0"],
            }
        ]
        await repo.connect_entities_bulk(relations)

        write_kwargs = mock_session.run.call_args_list[1][1]
        normalized = write_kwargs["relations_data"][0]
        assert normalized["merged_chunk_refs"] == ["book-1:1:0"]
        assert normalized["edge_id"]  # a fresh edge id was generated


@pytest.mark.asyncio
async def test_graph_repository_connect_entities_bulk_carries_evidence():
    """evidence must survive into the write payload — it's dropped before this fix,
    silently discarding the figurative-kinship audit trail (item 4)."""
    mock_read_result = AsyncMock()
    mock_read_result.data.return_value = []
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.run.side_effect = [mock_read_result, AsyncMock()]
    mock_driver = _mock_driver_session(mock_session)

    with patch(
        "app.db.repositories.graph_repository.AsyncGraphDatabase.driver",
        return_value=mock_driver,
    ):
        repo = GraphRepository()
        relations = [
            {
                "source_id": "s1",
                "rel_type": "SON_OF",
                "target_id": "t1",
                "book_id": "book-1",
                "chunk_refs": ["book-1:1:0"],
                "evidence": "he was the son of Ibrahim",
            }
        ]
        await repo.connect_entities_bulk(relations)

        write_kwargs = mock_session.run.call_args_list[1][1]
        normalized = write_kwargs["relations_data"][0]
        assert normalized["evidence"] == "he was the son of Ibrahim"


@pytest.mark.asyncio
async def test_graph_repository_merge_entities_by_id_redirects_edges_and_deletes():
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_driver = _mock_driver_session(mock_session)

    with patch(
        "app.db.repositories.graph_repository.AsyncGraphDatabase.driver",
        return_value=mock_driver,
    ):
        repo = GraphRepository()
        with patch.object(
            repo, "connect_entities_bulk", new=AsyncMock()
        ) as mock_connect:
            edges = [
                {
                    "id": "edge-1",
                    "rel_type": "SON_OF",
                    "direction": "out",
                    "other_endpoint_id": "other-1",
                    "book_id": "book-1",
                    "chunk_refs": ["book-1:1:0"],
                },
                {
                    "id": "edge-2",
                    "rel_type": "RULED",
                    "direction": "in",
                    "other_endpoint_id": "other-2",
                    "book_id": "book-1",
                    "chunk_refs": [],
                },
            ]
            await repo.merge_entities_by_id("keep-1", "remove-1", ["Alias1"], edges)

            redirected = mock_connect.call_args[0][0]
            assert {
                "source_id": "keep-1",
                "target_id": "other-1",
                "rel_type": "SON_OF",
                "book_id": "book-1",
                "edge_id": "edge-1",
                "chunk_refs": ["book-1:1:0"],
                "year_hijri": None,
                "year_gregorian": None,
                "century_gregorian": None,
            } in redirected
            assert {
                "source_id": "other-2",
                "target_id": "keep-1",
                "rel_type": "RULED",
                "book_id": "book-1",
                "edge_id": "edge-2",
                "chunk_refs": [],
                "year_hijri": None,
                "year_gregorian": None,
                "century_gregorian": None,
            } in redirected

            # aliases SET + DETACH DELETE on the removed node
            assert mock_session.run.call_count == 2
            alias_call = mock_session.run.call_args_list[0]
            assert alias_call[1]["aliases"] == ["Alias1"]
            delete_call = mock_session.run.call_args_list[1]
            assert "DETACH DELETE remove" in delete_call[0][0]
            assert delete_call[1]["remove_id"] == "remove-1"


@pytest.mark.asyncio
async def test_graph_repository_rename_entity_folds_old_name_into_aliases():
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_driver = _mock_driver_session(mock_session)

    with patch(
        "app.db.repositories.graph_repository.AsyncGraphDatabase.driver",
        return_value=mock_driver,
    ):
        repo = GraphRepository()
        with patch.object(
            repo,
            "get_entity_by_id",
            new=AsyncMock(
                return_value={"id": "e1", "canonical_name": "OldName", "aliases": []}
            ),
        ):
            success = await repo.rename_entity("e1", "NewName")
            assert success is True

            call_kwargs = mock_session.run.call_args[1]
            assert call_kwargs["id"] == "e1"
            assert call_kwargs["new_name"] == "NewName"
            assert "OldName" in call_kwargs["aliases"]


@pytest.mark.asyncio
async def test_graph_repository_rename_entity_missing_raises():
    mock_driver = MagicMock()
    with patch(
        "app.db.repositories.graph_repository.AsyncGraphDatabase.driver",
        return_value=mock_driver,
    ):
        repo = GraphRepository()
        with patch.object(repo, "get_entity_by_id", new=AsyncMock(return_value=None)):
            with pytest.raises(ValueError):
                await repo.rename_entity("missing-id", "NewName")


@pytest.mark.asyncio
async def test_graph_repository_delete_relationship_by_id_success():
    mock_result = AsyncMock()
    mock_result.data.return_value = [{"deleted": 1}]
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.run.return_value = mock_result
    mock_driver = _mock_driver_session(mock_session)

    with patch(
        "app.db.repositories.graph_repository.AsyncGraphDatabase.driver",
        return_value=mock_driver,
    ):
        repo = GraphRepository()
        success = await repo.delete_relationship_by_id("edge-1")
        assert success is True
        assert mock_session.run.call_args[1]["id"] == "edge-1"


@pytest.mark.asyncio
async def test_graph_repository_delete_relationship_by_id_not_found():
    mock_result = AsyncMock()
    mock_result.data.return_value = [{"deleted": 0}]
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.run.return_value = mock_result
    mock_driver = _mock_driver_session(mock_session)

    with patch(
        "app.db.repositories.graph_repository.AsyncGraphDatabase.driver",
        return_value=mock_driver,
    ):
        repo = GraphRepository()
        with pytest.raises(ValueError):
            await repo.delete_relationship_by_id("missing-edge")


def test_graph_repository_connected_components_groups_by_shared_book_and_endpoint():
    edges = [
        {"id": "e1", "book_id": "book-a", "other_endpoint_id": "p1"},
        {"id": "e2", "book_id": "book-a", "other_endpoint_id": "p2"},
        {"id": "e3", "book_id": "book-b", "other_endpoint_id": "p3"},
    ]
    components = GraphRepository._connected_components(edges)
    # e1/e2 share book-a -> same component; e3 is isolated
    assert components["e1"] == components["e2"]
    assert components["e3"] != components["e1"]


@pytest.mark.asyncio
async def test_graph_repository_split_entities_partitions_and_flags_unclustered():
    mock_driver = MagicMock()
    with patch(
        "app.db.repositories.graph_repository.AsyncGraphDatabase.driver",
        return_value=mock_driver,
    ):
        repo = GraphRepository()

        original = {
            "id": "orig-1",
            "canonical_name": "Ambiguous",
            "type": "Person",
            "scope": "nonfiction",
            "book_id": None,
        }
        all_edges = [
            {
                "id": "split-edge",
                "rel_type": "CHILD_OF",
                "direction": "out",
                "other_endpoint_id": "father-a",
                "book_id": "book-1",
                "chunk_refs": [],
            },
            {
                "id": "conflict-edge",
                "rel_type": "CHILD_OF",
                "direction": "out",
                "other_endpoint_id": "father-b",
                "book_id": "book-2",
                "chunk_refs": [],
            },
            {
                "id": "isolated-edge",
                "rel_type": "RULED",
                "direction": "out",
                "other_endpoint_id": "somewhere",
                "book_id": "book-3",
                "chunk_refs": [],
            },
        ]
        with (
            patch.object(
                repo, "get_entity_by_id", new=AsyncMock(return_value=original)
            ),
            patch.object(
                repo, "get_entity_edges_snapshot", new=AsyncMock(return_value=all_edges)
            ),
            patch.object(repo, "upsert_entities_bulk", new=AsyncMock()) as mock_upsert,
            patch.object(
                repo, "connect_entities_bulk", new=AsyncMock()
            ) as mock_connect,
            patch.object(
                repo, "delete_relationships_by_ids", new=AsyncMock()
            ) as mock_delete_edges,
        ):
            result = await repo.split_entities("orig-1", "split-edge")

            # The new node gets only its own canonical_name as an alias (not the original's full list)
            new_entity = mock_upsert.call_args[0][0][0]
            assert new_entity["aliases"] == ["Ambiguous"]

            # The conflicting edge moved to the new entity; the isolated edge is flagged, not moved.
            assert result["moved_edge_ids"] == ["conflict-edge"]
            assert result["unclustered_edge_ids"] == ["isolated-edge"]
            assert result["new_entity_id"] == new_entity["id"]
            mock_delete_edges.assert_called_once_with(["conflict-edge"])
            mock_connect.assert_called_once()


@pytest.mark.asyncio
async def test_graph_repository_split_entities_missing_edge_raises():
    mock_driver = MagicMock()
    with patch(
        "app.db.repositories.graph_repository.AsyncGraphDatabase.driver",
        return_value=mock_driver,
    ):
        repo = GraphRepository()
        with (
            patch.object(
                repo,
                "get_entity_by_id",
                new=AsyncMock(return_value={"id": "e1", "canonical_name": "X"}),
            ),
            patch.object(
                repo, "get_entity_edges_snapshot", new=AsyncMock(return_value=[])
            ),
        ):
            with pytest.raises(ValueError):
                await repo.split_entities("e1", "nonexistent-edge")


@pytest.mark.asyncio
async def test_graph_repository_restore_entity_from_snapshot_repoints_matching_edges():
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    # find_result for edge-1 (found) then no more find calls for edge-2 (missing)
    found_result = AsyncMock()
    found_result.single.return_value = {"chunk_refs": []}
    missing_result = AsyncMock()
    missing_result.single.return_value = None

    mock_session.run.side_effect = [
        None,  # CREATE (e:Entity)
        found_result,  # find edge-1
        None,  # delete edge-1
        None,  # recreate edge-1
    ]
    mock_driver = _mock_driver_session(mock_session)

    with patch(
        "app.db.repositories.graph_repository.AsyncGraphDatabase.driver",
        return_value=mock_driver,
    ):
        repo = GraphRepository()
        snapshot = {"id": "restored-1", "canonical_name": "Restored"}
        edges = [
            {
                "id": "edge-1",
                "rel_type": "SON_OF",
                "direction": "out",
                "other_endpoint_id": "p1",
                "book_id": "b1",
                "chunk_refs": [],
            },
        ]
        unrecoverable = await repo.restore_entity_from_snapshot(snapshot, edges)
        assert unrecoverable == []
        assert mock_session.run.call_count == 4


@pytest.mark.asyncio
async def test_graph_repository_restore_entity_from_snapshot_reports_unrecoverable():
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    missing_result = AsyncMock()
    missing_result.single.return_value = None
    mock_session.run.side_effect = [None, missing_result]
    mock_driver = _mock_driver_session(mock_session)

    with patch(
        "app.db.repositories.graph_repository.AsyncGraphDatabase.driver",
        return_value=mock_driver,
    ):
        repo = GraphRepository()
        snapshot = {"id": "restored-1", "canonical_name": "Restored"}
        edges = [
            {
                "id": "collided-edge",
                "rel_type": "SON_OF",
                "direction": "out",
                "other_endpoint_id": "p1",
                "book_id": "b1",
                "chunk_refs": [],
            },
        ]
        unrecoverable = await repo.restore_entity_from_snapshot(snapshot, edges)
        assert unrecoverable == ["collided-edge"]


@pytest.mark.asyncio
async def test_graph_repository_find_resolution_candidates_queries_fulltext_index():
    mock_result = AsyncMock()
    mock_result.data.return_value = [{"id": "cand-1", "canonical_name": "Similar Name"}]
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.run.return_value = mock_result
    mock_driver = _mock_driver_session(mock_session)

    with patch(
        "app.db.repositories.graph_repository.AsyncGraphDatabase.driver",
        return_value=mock_driver,
    ):
        repo = GraphRepository()
        candidates = await repo.find_resolution_candidates(
            entity_id="e1",
            canonical_name="Some Name",
            aliases=["Alt Name"],
            scope="nonfiction",
        )
        assert candidates == [{"id": "cand-1", "canonical_name": "Similar Name"}]
        call_kwargs = mock_session.run.call_args[1]
        assert set(call_kwargs["terms"]) == {"Some Name", "Alt Name"}
        assert call_kwargs["entity_id"] == "e1"


@pytest.mark.asyncio
async def test_graph_repository_find_resolution_candidates_no_terms_returns_empty():
    mock_driver = MagicMock()
    with patch(
        "app.db.repositories.graph_repository.AsyncGraphDatabase.driver",
        return_value=mock_driver,
    ):
        repo = GraphRepository()
        candidates = await repo.find_resolution_candidates(
            entity_id="e1", canonical_name="", aliases=None, scope="nonfiction"
        )
        assert candidates == []
        assert not mock_driver.session.called


@pytest.mark.asyncio
async def test_graph_repository_find_semantic_candidates():
    mock_result = AsyncMock()
    mock_result.data.return_value = [
        {"id": "cand-1", "canonical_name": "Temur Barlas", "score": 0.91}
    ]
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.run.return_value = mock_result
    mock_driver = _mock_driver_session(mock_session)

    with patch(
        "app.db.repositories.graph_repository.AsyncGraphDatabase.driver",
        return_value=mock_driver,
    ):
        repo = GraphRepository()
        records = await repo.find_semantic_candidates(
            entity_id="e1",
            embedding=[0.1, 0.2, 0.3],
            scope="nonfiction",
            book_id=None,
            limit=5,
        )

        assert records == [
            {"id": "cand-1", "canonical_name": "Temur Barlas", "score": 0.91}
        ]
        assert mock_session.run.called
        call_args = mock_session.run.call_args[0]
        call_kwargs = mock_session.run.call_args[1]
        assert "db.index.vector.queryNodes" in call_args[0]
        assert "entity_profile_embedding_idx" in call_args[0]
        assert call_kwargs["embedding"] == [0.1, 0.2, 0.3]
        assert call_kwargs["entity_id"] == "e1"
        assert call_kwargs["scope"] == "nonfiction"
        assert call_kwargs["book_id"] is None
        # Over-fetch substantially (limit * 10, floored at 50) so the scope/book_id
        # filter in WHERE — which runs *after* the vector index picks its top-k, per
        # Cypher's evaluation order — has enough candidates left to find same-scope
        # matches, rather than being globally starved down to nothing.
        assert call_kwargs["k"] == 50
        assert call_kwargs["limit"] == 5


@pytest.mark.asyncio
async def test_graph_repository_find_semantic_candidates_overfetches_proportionally_to_limit():
    mock_result = AsyncMock()
    mock_result.data.return_value = []
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.run.return_value = mock_result
    mock_driver = _mock_driver_session(mock_session)

    with patch(
        "app.db.repositories.graph_repository.AsyncGraphDatabase.driver",
        return_value=mock_driver,
    ):
        repo = GraphRepository()
        await repo.find_semantic_candidates(
            entity_id="e1",
            embedding=[0.1, 0.2, 0.3],
            scope="nonfiction",
            book_id=None,
            limit=20,
        )

        call_kwargs = mock_session.run.call_args[1]
        # limit * 10 dominates the floor once limit is large enough.
        assert call_kwargs["k"] == 200
