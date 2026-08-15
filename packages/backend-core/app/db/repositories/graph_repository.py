"""Repository for interacting with Neo4j using the async Neo4j driver."""

from __future__ import annotations

import logging
import unicodedata
import uuid
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from neo4j import AsyncGraphDatabase
from neo4j.exceptions import ClientError

from app.core.config import settings
from app.utils.observability import log_json

logger = logging.getLogger("app.db.repositories.graph")
logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)


class GraphRepository:
    """Repository for interacting with Neo4j using the async Neo4j driver.

    Entities are keyed by a stable ``id`` (uuid) assigned once at extraction —
    never by name, since two distinct real-world entities can share a name
    (see knowledge-graph-entity-resolution-design-v2.md). ``canonical_name``/
    ``aliases`` are display-only; dedup across duplicate names is entirely the
    job of the global resolution pass (`entity_resolution_service`), not of
    any MERGE performed here.
    """

    _driver = None

    def __init__(self, uri: Optional[str] = None) -> None:
        self._uri = uri or settings.neo4j_url
        if GraphRepository._driver is None:
            # Parse credentials from the URI if present, as the Neo4j driver does not support
            # credentials embedded directly in the URI scheme.
            parsed = urlparse(self._uri)
            if parsed.username and parsed.password:
                auth = (parsed.username, parsed.password)
                # Reconstruct clean URI without credentials, preserving path and query
                clean_uri = f"{parsed.scheme}://{parsed.hostname}"
                if parsed.port:
                    clean_uri += f":{parsed.port}"
                if parsed.path:
                    clean_uri += parsed.path
                if parsed.query:
                    clean_uri += f"?{parsed.query}"
            else:
                auth = None
                clean_uri = self._uri

            # liveness_check_timeout=0: verify each pooled connection is alive before
            #   returning it to the caller — prevents "defunct connection" errors that occur
            #   when Neo4j closes an idle connection server-side while it is still in the pool.
            # max_connection_lifetime=300: recycle connections after 5 minutes so they are
            #   never older than the server-side idle timeout.
            # max_connection_pool_size=20: explicit cap; one worker job with max_parallel=5
            #   batches at 2 graph calls each fits comfortably within this limit.
            # connection_timeout=30: fail fast rather than waiting indefinitely on a dead host.
            GraphRepository._driver = AsyncGraphDatabase.driver(
                clean_uri,
                auth=auth,
                max_connection_pool_size=20,
                max_connection_lifetime=300,
                connection_timeout=30,
                liveness_check_timeout=0,
                keep_alive=True,
            )
        self._driver = GraphRepository._driver

    async def close(self) -> None:
        """No-op when driver is shared. Driver cleanup is handled at app shutdown."""
        pass

    @classmethod
    async def close_driver(cls) -> None:
        """Close driver session connection pool."""
        if cls._driver is not None:
            try:
                await cls._driver.close()
            except TypeError:
                if hasattr(cls._driver, "close") and callable(cls._driver.close):
                    cls._driver.close()
            cls._driver = None

    async def init_constraints(self) -> None:
        """Initialize uniqueness constraints and indexes in Neo4j.

        `entity_name_unique` is dropped (two entities can now legitimately share a
        name) in favor of `entity_id_unique` on the stable `id` assigned at
        extraction. `entity_search_idx` is a native full-text index (no APOC
        plugin is installed in either compose file) used by the resolution
        pass's fuzzy candidate lookup; the plain B-tree indexes remain for
        exact-match reads elsewhere (e.g. the admin search in GraphView.tsx).
        `entity_profile_embedding_idx` is a vector index on entity profile embeddings
        for semantic similarity search in entity resolution.
        """
        statements = [
            "DROP CONSTRAINT entity_name_unique IF EXISTS;",
            "CREATE CONSTRAINT entity_id_unique IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE;",
            "CREATE INDEX entity_canonical_name_idx IF NOT EXISTS FOR (e:Entity) ON (e.canonical_name);",
            "CREATE INDEX entity_aliases_idx IF NOT EXISTS FOR (e:Entity) ON (e.aliases);",
            "CREATE FULLTEXT INDEX entity_search_idx IF NOT EXISTS FOR (e:Entity) ON EACH [e.canonical_name, e.aliases];",
            "CREATE INDEX rel_book_id_idx IF NOT EXISTS FOR ()-[r:RELATED_TO]-() ON (r.book_id);",
            "CREATE INDEX rel_rel_type_idx IF NOT EXISTS FOR ()-[r:RELATED_TO]-() ON (r.rel_type);",
            "CREATE INDEX rel_id_idx IF NOT EXISTS FOR ()-[r:RELATED_TO]-() ON (r.id);",
            "CREATE INDEX rel_chunk_refs_idx IF NOT EXISTS FOR ()-[r:RELATED_TO]-() ON (r.chunk_refs);",
            """
            CREATE VECTOR INDEX entity_profile_embedding_idx IF NOT EXISTS
            FOR (e:Entity) ON (e.profile_embedding)
            OPTIONS { indexConfig: {
                `vector.dimensions`: 3072,
                `vector.similarity_function`: 'cosine'
            }};
            """,
        ]
        async with self._driver.session() as session:
            for statement in statements:
                try:
                    await session.run(statement)
                except ClientError as exc:
                    # Neo4j raises ClientError when a constraint/index already exists
                    # (IF NOT EXISTS is not always honoured). Let real connection errors
                    # (ServiceUnavailable, AuthError) propagate so the caller knows
                    # the graph DB is unreachable.
                    log_json(
                        logger,
                        logging.DEBUG,
                        "constraint/index already exists or schema warning",
                        detail=str(exc),
                    )

    async def check_books_exist(self, book_ids: List[str]) -> List[str]:
        """Check which book IDs already have relationships/nodes in the graph database."""
        if not book_ids:
            return []
        query = """
        MATCH ()-[r:RELATED_TO]->()
        WHERE r.book_id IN $book_ids
        RETURN DISTINCT r.book_id AS book_id
        """
        async with self._driver.session() as session:
            result = await session.run(query, book_ids=book_ids)
            records = await result.data()
            return [r["book_id"] for r in records]

    async def set_resolution_status(self, entity_id: str, status: str) -> None:
        """Marks an Entity's resolution_status ('unresolved'|'resolving'|'resolved') —
        drives candidate-selection exclusion of in-flight nodes (§4 step 1)."""
        async with self._driver.session() as session:
            await session.run(
                "MATCH (e:Entity {id: $id}) SET e.resolution_status = $status",
                id=entity_id,
                status=status,
            )

    async def get_children_via_child_of(self, entity_id: str) -> List[str]:
        """Returns ids of entities with a kinship edge pointing to `entity_id` as parent —
        the re-propagation candidates after a merge/split touching `entity_id` (§4 step 4)."""
        query = """
        MATCH (child:Entity)
        WHERE (child)-[:RELATED_TO {rel_type: 'CHILD_OF'}]->(:Entity {id: $id})
           OR (child)-[:RELATED_TO {rel_type: 'SON_OF'}]->(:Entity {id: $id})
           OR (child)-[:RELATED_TO {rel_type: 'DAUGHTER_OF'}]->(:Entity {id: $id})
           OR (child)<-[:RELATED_TO {rel_type: 'FATHER_OF'}]-(:Entity {id: $id})
           OR (child)<-[:RELATED_TO {rel_type: 'MOTHER_OF'}]-(:Entity {id: $id})
        RETURN DISTINCT child.id AS id
        """
        async with self._driver.session() as session:
            result = await session.run(query, id=entity_id)
            records = await result.data()
        return [r["id"] for r in records]

    # ------------------------------------------------------------------
    # Bulk write (extraction)
    # ------------------------------------------------------------------

    async def upsert_entities_bulk(self, entities: List[Dict[str, Any]]) -> None:
        """Create Entity nodes in bulk, keyed purely by `id` (never by name).

        Every entity dict must include a fresh `id` (uuid4, assigned by the
        caller at extraction time) — there is no dedup at write time; dedup is
        entirely the global resolution pass's job.
        """
        if not entities:
            return
        normalized = [
            {
                "id": e["id"],
                "canonical_name": unicodedata.normalize("NFC", e["canonical_name"])
                if e.get("canonical_name")
                else None,
                "aliases": [
                    unicodedata.normalize("NFC", a)
                    for a in (e.get("aliases") or [])
                    if a
                ],
                "type": e.get("type"),
                "subtype": e.get("subtype"),
                "context_summary": e.get("context_summary"),
                "scope": e.get("scope"),
                "book_id": e.get("book_id"),
                "year_hijri": e.get("year_hijri"),
                "year_gregorian": e.get("year_gregorian"),
                "century_gregorian": e.get("century_gregorian"),
                "resolution_status": e.get("resolution_status", "unresolved"),
            }
            for e in entities
        ]
        query = """
        UNWIND $entities_data AS e_data
        MERGE (e:Entity {id: e_data.id})
        SET e.canonical_name = e_data.canonical_name,
            e.aliases = e_data.aliases,
            e.type = e_data.type,
            e.subtype = e_data.subtype,
            e.context_summary = e_data.context_summary,
            e.scope = e_data.scope,
            e.book_id = e_data.book_id,
            e.year_hijri = e_data.year_hijri,
            e.year_gregorian = e_data.year_gregorian,
            e.century_gregorian = e_data.century_gregorian,
            e.resolution_status = e_data.resolution_status
        """
        async with self._driver.session() as session:
            await session.run(query, entities_data=normalized)

    async def connect_entities_bulk(self, relations: List[Dict[str, Any]]) -> None:
        """Create/merge RELATED_TO relationships between Entities in bulk, by id.

        MERGE key is `{rel_type, book_id}` between the two endpoint ids (not
        `{book_id}` alone) so two distinct facts about the same pair in the same
        book never collide. `chunk_refs` must accumulate across re-runs rather
        than being overwritten — since no APOC plugin is installed, the union is
        computed in Python via a read-before-write: existing `chunk_refs` for the
        batch's keys are fetched first, unioned with the new batch's refs, then
        sent as the already-merged value in the same UNWIND write. `id`/year
        fields are `ON CREATE`-only so a re-run never regenerates an edge's id or
        clobbers its original year fields.
        """
        if not relations:
            return

        keys = [
            {
                "source_id": r["source_id"],
                "rel_type": r["rel_type"],
                "target_id": r["target_id"],
                "book_id": r.get("book_id"),
            }
            for r in relations
        ]
        read_query = """
        UNWIND $keys AS k
        MATCH (s:Entity {id: k.source_id})-[rel:RELATED_TO {rel_type: k.rel_type, book_id: k.book_id}]->(t:Entity {id: k.target_id})
        RETURN k.source_id AS source_id, k.rel_type AS rel_type, k.target_id AS target_id, k.book_id AS book_id, rel.chunk_refs AS chunk_refs
        """
        async with self._driver.session() as session:
            result = await session.run(read_query, keys=keys)
            existing_records = await result.data()

        existing_refs: Dict[tuple, List[str]] = {}
        for rec in existing_records:
            key = (rec["source_id"], rec["rel_type"], rec["target_id"], rec["book_id"])
            existing_refs[key] = rec.get("chunk_refs") or []

        normalized = []
        for r in relations:
            key = (r["source_id"], r["rel_type"], r["target_id"], r.get("book_id"))
            new_refs = list(r.get("chunk_refs") or [])
            merged_refs = list(dict.fromkeys(existing_refs.get(key, []) + new_refs))
            normalized.append(
                {
                    "source_id": r["source_id"],
                    "rel_type": r["rel_type"],
                    "target_id": r["target_id"],
                    "book_id": r.get("book_id"),
                    "edge_id": r.get("edge_id") or str(uuid.uuid4()),
                    "chunk_refs": new_refs,
                    "merged_chunk_refs": merged_refs,
                    "year_hijri": r.get("year_hijri"),
                    "year_gregorian": r.get("year_gregorian"),
                    "century_gregorian": r.get("century_gregorian"),
                    # CHILD_OF-only; null/ignored for every other rel_type.
                    "parent_role": r.get("parent_role"),
                    "evidence": r.get("evidence"),
                }
            )

        write_query = """
        UNWIND $relations_data AS rel
        MATCH (s:Entity {id: rel.source_id})
        MATCH (t:Entity {id: rel.target_id})
        MERGE (s)-[r:RELATED_TO {rel_type: rel.rel_type, book_id: rel.book_id}]->(t)
        ON CREATE SET r.id = rel.edge_id,
                      r.chunk_refs = rel.chunk_refs,
                      r.year_hijri = rel.year_hijri,
                      r.year_gregorian = rel.year_gregorian,
                      r.century_gregorian = rel.century_gregorian,
                      r.parent_role = rel.parent_role,
                      r.evidence = rel.evidence
        ON MATCH SET r.chunk_refs = rel.merged_chunk_refs
        """
        async with self._driver.session() as session:
            await session.run(write_query, relations_data=normalized)

    async def delete_book_graph(self, book_id: str) -> None:
        """Delete all graph data for a book, then remove any orphaned Entity nodes.

        Edges carry book_id so we can delete only this book's relationships without
        touching shared entities that are still referenced by other books.
        Orphaned entities (no remaining edges in either direction) are removed last.
        """
        async with self._driver.session() as session:
            await session.run(
                "MATCH ()-[r:RELATED_TO {book_id: $book_id}]-() DELETE r",
                book_id=book_id,
            )
            await session.run(
                "MATCH (e:Entity) WHERE NOT (e)-[:RELATED_TO]-() AND NOT ()-[:RELATED_TO]->(e) DELETE e"
            )

    # ------------------------------------------------------------------
    # Reads used by the resolution pass / admin
    # ------------------------------------------------------------------

    async def get_entity_by_id(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Return an Entity node's properties, or None if it no longer exists."""
        query = "MATCH (e:Entity {id: $id}) RETURN e AS entity"
        async with self._driver.session() as session:
            result = await session.run(query, id=entity_id)
            record = await result.single()
        if not record:
            return None
        return dict(record["entity"])

    async def get_entity_names_by_ids(self, entity_ids: List[str]) -> Dict[str, str]:
        """Return a mapping of entity_id -> canonical_name for a list of UUIDs."""
        if not entity_ids:
            return {}
        query = """
        MATCH (e:Entity)
        WHERE e.id IN $ids
        RETURN e.id AS id, coalesce(e.canonical_name, e.name, e.label, head(e.aliases)) AS name
        """
        async with self._driver.session() as session:
            result = await session.run(query, ids=entity_ids)
            records = await result.data()
        return {r["id"]: r["name"] for r in records if r.get("id") and r.get("name")}

    async def get_entity_facts(self, entity_id: str) -> Dict[str, Any]:
        """Return the canonical functional facts (CHILD_OF/SON_OF/DAUGHTER_OF/FATHER_OF/MOTHER_OF/BORN_IN/DIED_IN)
        + a sample of relationship neighbors for `entity_id`, used for hard-constraint checks and
        as gray-zone LLM judge input (design v2 §4 step 2, §4.1)."""
        query = """
        MATCH (e:Entity {id: $id})
        OPTIONAL MATCH (e)-[co:RELATED_TO]->(parent:Entity)
          WHERE co.rel_type IN ['CHILD_OF', 'SON_OF', 'DAUGHTER_OF']
        OPTIONAL MATCH (e)<-[co_rev:RELATED_TO]-(parent_rev:Entity)
          WHERE co_rev.rel_type IN ['FATHER_OF', 'MOTHER_OF']
        OPTIONAL MATCH (e)-[bi:RELATED_TO]->(loc:Entity)
          WHERE bi.rel_type = 'BORN_IN'
        OPTIONAL MATCH (e)-[di:RELATED_TO]->(era:Entity)
          WHERE di.rel_type = 'DIED_IN'
        OPTIONAL MATCH (e)-[nb:RELATED_TO]-(neighbor:Entity)
        RETURN
            [p IN collect(DISTINCT {parent_id: parent.id, parent_name: parent.canonical_name, parent_role: co.parent_role}) WHERE p.parent_id IS NOT NULL] +
            [p IN collect(DISTINCT {parent_id: parent_rev.id, parent_name: parent_rev.canonical_name, parent_role: CASE WHEN co_rev.rel_type = 'FATHER_OF' THEN 'father' ELSE 'mother' END}) WHERE p.parent_id IS NOT NULL] AS child_of,
            [b IN collect(DISTINCT {location_id: loc.id, location_name: loc.canonical_name}) WHERE b.location_id IS NOT NULL] AS born_in,
            [d IN collect(DISTINCT {era_id: era.id, era_name: era.canonical_name, year_hijri: di.year_hijri, year_gregorian: di.year_gregorian}) WHERE d.era_id IS NOT NULL] AS died_in,
            [n IN collect(DISTINCT {neighbor_id: neighbor.id, neighbor_name: neighbor.canonical_name, rel_type: nb.rel_type}) WHERE n.neighbor_id IS NOT NULL] AS neighbors
        """
        async with self._driver.session() as session:
            result = await session.run(query, id=entity_id)
            record = await result.single()
        if not record:
            return {"child_of": [], "born_in": [], "died_in": [], "neighbors": []}
        return {
            "child_of": [c for c in record["child_of"] if c is not None],
            "born_in": [b for b in record["born_in"] if b is not None],
            "died_in": [d for d in record["died_in"] if d is not None],
            "neighbors": [n for n in record["neighbors"] if n is not None][:20],
        }

    async def get_entities_facts_for_citation_bulk(
        self, entity_ids: List[str]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Returns facts for multiple entity IDs in a single bulk Cypher query (design v2 §6)."""
        if not entity_ids:
            return {}
        query = """
        MATCH (e:Entity) WHERE e.id IN $ids
        OPTIONAL MATCH (e)-[r:RELATED_TO]-(other:Entity)
        RETURN e.id AS entity_id, e.canonical_name AS entity_name, e.type AS entity_type,
               collect(CASE WHEN r IS NULL THEN NULL ELSE {
                   rel_type: r.rel_type, book_id: r.book_id, chunk_refs: r.chunk_refs,
                   other_name: other.canonical_name, is_outgoing: startNode(r).id = e.id
               } END) AS facts
        """
        async with self._driver.session() as session:
            result = await session.run(query, ids=entity_ids)
            records = await result.data()

        facts_by_entity: Dict[str, List[Dict[str, Any]]] = {}
        for record in records:
            entity_id = record["entity_id"]
            entity_name = record["entity_name"]
            rows: List[Dict[str, Any]] = []
            for f in record["facts"]:
                if f is None:
                    continue
                chunk_refs = f.get("chunk_refs") or []
                book_id = f.get("book_id")
                page = None
                if chunk_refs:
                    parts = str(chunk_refs[0]).split(":")
                    if len(parts) == 3:
                        book_id = book_id or parts[0]
                        try:
                            page = int(parts[1])
                        except ValueError:
                            page = None
                other_name = f.get("other_name") or ""
                if f.get("is_outgoing"):
                    text = f"{entity_name} {f['rel_type']} {other_name}".strip()
                else:
                    text = f"{other_name} {f['rel_type']} {entity_name}".strip()
                rows.append({"text": text, "book_id": book_id, "page": page})

            if not rows:
                rows.append(
                    {
                        "text": f"{entity_name} ({record['entity_type']})",
                        "book_id": None,
                        "page": None,
                    }
                )
            facts_by_entity[entity_id] = rows
        return facts_by_entity

    async def get_entity_facts_for_citation(
        self, entity_id: str
    ) -> List[Dict[str, Any]]:
        """Returns this entity's facts as flat, citable rows for query-time RAG use."""
        facts_map = await self.get_entities_facts_for_citation_bulk([entity_id])
        return facts_map.get(entity_id, [])

    async def find_resolution_candidates(
        self,
        entity_id: str,
        canonical_name: str,
        aliases: Optional[List[str]],
        scope: str,
        book_id: Optional[str] = None,
        edit_distance: int = 2,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Fuzzy-match other Entity nodes whose canonical_name/aliases resemble this
        entity's — the candidate-selection step of the global resolution pass (§4
        step 1). Uses the native full-text index (Lucene fuzzy operator) since Cypher
        has no trigram operator and no APOC plugin is installed. Restricted to the
        same `scope`, and additionally to the same `book_id` for fiction.
        """
        terms = list(
            dict.fromkeys([t for t in [canonical_name, *(aliases or [])] if t])
        )
        if not terms:
            return []
        query = """
        UNWIND $terms AS term
        CALL db.index.fulltext.queryNodes("entity_search_idx", term + "~" + $edit_distance) YIELD node, score
        WHERE node.id <> $entity_id
          AND node.scope = $scope
          AND coalesce(node.resolution_status, 'unresolved') <> 'resolving'
          AND ($book_id IS NULL OR node.book_id = $book_id)
        WITH node, max(score) AS best_score
        RETURN node.id AS id, node.canonical_name AS canonical_name, node.aliases AS aliases,
               node.type AS type, node.subtype AS subtype, node.scope AS scope, node.book_id AS book_id,
               node.year_hijri AS year_hijri, node.year_gregorian AS year_gregorian,
               node.century_gregorian AS century_gregorian, best_score AS score
        ORDER BY best_score DESC
        LIMIT $limit
        """
        async with self._driver.session() as session:
            result = await session.run(
                query,
                terms=terms,
                entity_id=entity_id,
                scope=scope,
                book_id=book_id,
                edit_distance=str(edit_distance),
                limit=limit,
            )
            return await result.data()

    async def find_semantic_candidates(
        self,
        entity_id: str,
        embedding: List[float],
        scope: str,
        book_id: Optional[str] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Live per-entity semantic candidate lookup via the native Neo4j vector index
        (`entity_profile_embedding_idx`, Task 2). Unlike the GDS `kNN` methods below
        (Items 6-9), this needs no graph projection/refresh lifecycle — the index
        updates incrementally as `profile_embedding` is written, so a query always
        sees current data.

        Returns candidates shaped like `find_resolution_candidates`'s output so both
        candidate sources merge into one list in `resolve_entity` without reshaping.
        Requests one extra result (`k = limit + 1`) since the entity's own node is
        always the top hit against its own embedding and is filtered out below.
        """
        query = """
        CALL db.index.vector.queryNodes('entity_profile_embedding_idx', $k, $embedding)
        YIELD node, score
        WHERE node.id <> $entity_id
          AND node.scope = $scope
          AND coalesce(node.resolution_status, 'unresolved') <> 'resolving'
          AND ($book_id IS NULL OR node.book_id = $book_id)
        RETURN node.id AS id, node.canonical_name AS canonical_name, node.aliases AS aliases,
               node.type AS type, node.subtype AS subtype, node.scope AS scope, node.book_id AS book_id,
               node.year_hijri AS year_hijri, node.year_gregorian AS year_gregorian,
               node.century_gregorian AS century_gregorian, score
        ORDER BY score DESC
        LIMIT $limit
        """
        async with self._driver.session() as session:
            result = await session.run(
                query,
                embedding=embedding,
                entity_id=entity_id,
                scope=scope,
                book_id=book_id,
                k=limit + 1,
                limit=limit,
            )
            return await result.data()

    async def search_entities_fulltext(
        self, query_terms: List[str], edit_distance: int = 1, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Invoked as miss-only fallback when exact/prefix alias lookup in Redis yields 0 hits."""
        terms = list(
            dict.fromkeys([t.strip() for t in query_terms if t and len(t.strip()) >= 3])
        )
        if not terms:
            return []
        query = """
        UNWIND $terms AS term
        CALL db.index.fulltext.queryNodes("entity_search_idx", term + "~" + $edit_distance) YIELD node, score
        WHERE coalesce(node.resolution_status, 'unresolved') <> 'resolving'
        WITH node, max(score) AS best_score
        RETURN node.id AS id, node.canonical_name AS canonical_name, node.aliases AS aliases,
               node.type AS type, node.subtype AS subtype, best_score AS score
        ORDER BY best_score DESC
        LIMIT $limit
        """
        async with self._driver.session() as session:
            result = await session.run(
                query,
                terms=terms,
                edit_distance=str(edit_distance),
                limit=limit,
            )
            return await result.data()

    async def get_entity_edges_snapshot(self, entity_id: str) -> List[Dict[str, Any]]:
        """Return every RELATED_TO edge touching `entity_id`, in either direction,
        each tagged with its `direction` ('out'|'in') and the other endpoint's id —
        used both for merge-log snapshots and for split's connected-component input.
        """
        query = """
        MATCH (e:Entity {id: $id})
        OPTIONAL MATCH (e)-[r_out:RELATED_TO]->(other_out:Entity)
        WITH e, [item IN collect({
            id: r_out.id, rel_type: r_out.rel_type, direction: 'out',
            other_endpoint_id: other_out.id, book_id: r_out.book_id,
            chunk_refs: r_out.chunk_refs, year_hijri: r_out.year_hijri,
            year_gregorian: r_out.year_gregorian, century_gregorian: r_out.century_gregorian
        }) WHERE item.id IS NOT NULL] AS out_edges
        OPTIONAL MATCH (other_in:Entity)-[r_in:RELATED_TO]->(e)
        RETURN out_edges, [item IN collect({
            id: r_in.id, rel_type: r_in.rel_type, direction: 'in',
            other_endpoint_id: other_in.id, book_id: r_in.book_id,
            chunk_refs: r_in.chunk_refs, year_hijri: r_in.year_hijri,
            year_gregorian: r_in.year_gregorian, century_gregorian: r_in.century_gregorian
        }) WHERE item.id IS NOT NULL] AS in_edges
        """
        async with self._driver.session() as session:
            result = await session.run(query, id=entity_id)
            record = await result.single()
        if not record:
            return []
        edges = [e for e in record["out_edges"] if e is not None]
        edges += [e for e in record["in_edges"] if e is not None]
        return edges

    async def delete_relationships_by_ids(self, edge_ids: List[str]) -> None:
        if not edge_ids:
            return
        query = "MATCH ()-[r:RELATED_TO]->() WHERE r.id IN $ids DELETE r"
        async with self._driver.session() as session:
            await session.run(query, ids=edge_ids)

    # ------------------------------------------------------------------
    # Manual / automated control: merge / split / unmerge (id-keyed, §5)
    # ------------------------------------------------------------------

    async def merge_entities_by_id(
        self,
        keep_id: str,
        remove_id: str,
        combined_aliases: List[str],
        edges_to_redirect: List[Dict[str, Any]],
    ) -> None:
        """Pure Neo4j merge — the caller (entity_resolution_service) is responsible
        for snapshotting `remove_id`'s node + edges to `graph_merge_log` in Postgres
        BEFORE calling this, since the snapshot must reflect state immediately prior
        to deletion.

        Redirected edges are re-created from `keep_id`'s perspective and written via
        `connect_entities_bulk`, reusing its existing chunk_refs-union semantics so a
        pre-existing edge on `keep` with the same (rel_type, other_endpoint) absorbs
        the redirected edge's chunk_refs instead of creating a duplicate.
        """
        redirected = []
        for e in edges_to_redirect:
            other_id = e.get("other_endpoint_id")
            if not other_id:
                continue
            if e["direction"] == "out":
                source_id, target_id = keep_id, other_id
            else:
                source_id, target_id = other_id, keep_id
            redirected.append(
                {
                    "source_id": source_id,
                    "target_id": target_id,
                    "rel_type": e["rel_type"],
                    "book_id": e.get("book_id"),
                    "edge_id": e.get("id"),
                    "chunk_refs": e.get("chunk_refs") or [],
                    "year_hijri": e.get("year_hijri"),
                    "year_gregorian": e.get("year_gregorian"),
                    "century_gregorian": e.get("century_gregorian"),
                }
            )
        if redirected:
            await self.connect_entities_bulk(redirected)

        async with self._driver.session() as session:
            await session.run(
                "MATCH (keep:Entity {id: $keep_id}) SET keep.aliases = $aliases",
                keep_id=keep_id,
                aliases=combined_aliases,
            )
            await session.run(
                "MATCH (remove:Entity {id: $remove_id}) DETACH DELETE remove",
                remove_id=remove_id,
            )

    @staticmethod
    def _connected_components(edges: List[Dict[str, Any]]) -> Dict[str, str]:
        """Union-Find over edges, grouping two edges together when they share a
        `book_id` (same provenance) or the same `other_endpoint_id`. Returns
        edge_id -> component root id."""
        parent: Dict[str, str] = {e["id"]: e["id"] for e in edges if e.get("id")}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        group_of_book: Dict[tuple, str] = {}
        group_of_endpoint: Dict[tuple, str] = {}
        for e in edges:
            eid = e.get("id")
            if not eid:
                continue
            if e.get("book_id"):
                key = ("book", e["book_id"])
                if key in group_of_book:
                    union(eid, group_of_book[key])
                else:
                    group_of_book[key] = eid
            if e.get("other_endpoint_id"):
                key = ("endpoint", e["other_endpoint_id"])
                if key in group_of_endpoint:
                    union(eid, group_of_endpoint[key])
                else:
                    group_of_endpoint[key] = eid
        return {eid: find(eid) for eid in parent}

    async def split_entities(
        self, entity_id: str, split_point_edge_id: str
    ) -> Dict[str, Any]:
        """Partitions `entity_id`'s edges into two clusters via connected-component
        analysis (design v2 §5). The split-point edge's cluster stays on the
        original node; the cluster containing the conflicting evidence (same
        rel_type as the split-point edge, different endpoint) is redirected to a
        newly created node. Edges that don't cluster cleanly with either anchor are
        left on the original node and returned as `unclustered_edge_ids` for manual
        admin reassignment — never silently dropped or guessed.

        The new node starts with `aliases: [canonical_name]` only (not the original
        node's full alias list) — otherwise it looks identical by name/alias to the
        very candidate-selection query that would immediately re-flag it as a merge
        candidate, undoing the split on the next resolution pass.
        """
        original = await self.get_entity_by_id(entity_id)
        if not original:
            raise ValueError(f"Entity '{entity_id}' does not exist.")

        all_edges = await self.get_entity_edges_snapshot(entity_id)
        split_edge = next(
            (e for e in all_edges if e.get("id") == split_point_edge_id), None
        )
        if not split_edge:
            raise ValueError(
                f"Edge '{split_point_edge_id}' not found on entity '{entity_id}'."
            )
        remaining = [e for e in all_edges if e.get("id") != split_point_edge_id]

        components = self._connected_components(remaining)

        cluster_a_root = None
        for e in remaining:
            if e.get("id") and (
                e.get("book_id") == split_edge.get("book_id")
                or e.get("other_endpoint_id") == split_edge.get("other_endpoint_id")
            ):
                cluster_a_root = components.get(e["id"])
                break

        # The contradicting cluster: same rel_type as the split edge, different endpoint.
        conflicting_roots = {
            components[e["id"]]
            for e in remaining
            if e.get("id")
            and e.get("rel_type") == split_edge.get("rel_type")
            and e.get("other_endpoint_id") != split_edge.get("other_endpoint_id")
            and components.get(e["id"]) != cluster_a_root
        }
        cluster_b_root = None
        if conflicting_roots:
            counts = {
                root: sum(1 for v in components.values() if v == root)
                for root in conflicting_roots
            }
            cluster_b_root = max(counts, key=counts.get)

        cluster_b_edges = (
            [
                e
                for e in remaining
                if e.get("id") and components[e["id"]] == cluster_b_root
            ]
            if cluster_b_root
            else []
        )
        unclustered_edges = [
            e
            for e in remaining
            if e.get("id")
            and components[e["id"]] not in (cluster_a_root, cluster_b_root)
        ]

        new_entity_id = str(uuid.uuid4())
        new_entity = {
            "id": new_entity_id,
            "canonical_name": original.get("canonical_name"),
            "aliases": [original.get("canonical_name")]
            if original.get("canonical_name")
            else [],
            "type": original.get("type"),
            "subtype": original.get("subtype"),
            "scope": original.get("scope"),
            "book_id": original.get("book_id"),
            "resolution_status": "unresolved",
        }
        await self.upsert_entities_bulk([new_entity])

        redirected = []
        for e in cluster_b_edges:
            other_id = e.get("other_endpoint_id")
            if not other_id:
                continue
            if e["direction"] == "out":
                source_id, target_id = new_entity_id, other_id
            else:
                source_id, target_id = other_id, new_entity_id
            redirected.append(
                {
                    "source_id": source_id,
                    "target_id": target_id,
                    "rel_type": e["rel_type"],
                    "book_id": e.get("book_id"),
                    "chunk_refs": e.get("chunk_refs") or [],
                    "year_hijri": e.get("year_hijri"),
                    "year_gregorian": e.get("year_gregorian"),
                    "century_gregorian": e.get("century_gregorian"),
                }
            )
        if redirected:
            await self.connect_entities_bulk(redirected)
            await self.delete_relationships_by_ids(
                [e["id"] for e in cluster_b_edges if e.get("id")]
            )

        return {
            "new_entity_id": new_entity_id if cluster_b_edges else None,
            "moved_edge_ids": [e["id"] for e in cluster_b_edges if e.get("id")],
            "unclustered_edge_ids": [e["id"] for e in unclustered_edges if e.get("id")],
        }

    async def restore_entity_from_snapshot(
        self, snapshot: Dict[str, Any], edges: List[Dict[str, Any]]
    ) -> List[str]:
        """Recreates a merged-away entity node from `graph_merge_log` and re-points
        its original edges (matched by their stable edge `id`) back onto it.

        Edges whose id no longer exists as a distinct edge (absorbed into a
        pre-existing edge on the surviving node during the merge, per the chunk_refs
        collision case) cannot be re-pointed — their ids are returned so the caller
        can record which citations weren't recoverable (design v2 §5 unmerge review
        note: a known, accepted gap, not a bug to silently paper over).
        """
        async with self._driver.session() as session:
            await session.run("CREATE (e:Entity) SET e = $props", props=snapshot)

        unrecoverable: List[str] = []
        for e in edges:
            edge_id = e.get("id")
            other_id = e.get("other_endpoint_id")
            if not edge_id or not other_id:
                if edge_id:
                    unrecoverable.append(edge_id)
                continue

            async with self._driver.session() as session:
                find_result = await session.run(
                    "MATCH ()-[r:RELATED_TO {id: $id}]-() RETURN r.chunk_refs AS chunk_refs",
                    id=edge_id,
                )
                found = await find_result.single()
            if not found:
                unrecoverable.append(edge_id)
                continue

            async with self._driver.session() as session:
                await session.run(
                    "MATCH ()-[r:RELATED_TO {id: $id}]-() DELETE r", id=edge_id
                )

            if e["direction"] == "out":
                source_id, target_id = snapshot["id"], other_id
            else:
                source_id, target_id = other_id, snapshot["id"]

            async with self._driver.session() as session:
                await session.run(
                    """
                    MATCH (s:Entity {id: $source_id}), (t:Entity {id: $target_id})
                    CREATE (s)-[r:RELATED_TO {
                        id: $edge_id, rel_type: $rel_type, book_id: $book_id,
                        chunk_refs: $chunk_refs, year_hijri: $year_hijri,
                        year_gregorian: $year_gregorian, century_gregorian: $century_gregorian
                    }]->(t)
                    """,
                    source_id=source_id,
                    target_id=target_id,
                    edge_id=edge_id,
                    rel_type=e.get("rel_type"),
                    book_id=e.get("book_id"),
                    chunk_refs=e.get("chunk_refs") or [],
                    year_hijri=e.get("year_hijri"),
                    year_gregorian=e.get("year_gregorian"),
                    century_gregorian=e.get("century_gregorian"),
                )
        return unrecoverable

    async def rename_entity(self, entity_id: str, new_name: str) -> bool:
        """Rename an entity by id (canonical_name is display-only; ids never change).

        The old canonical_name is folded into aliases so existing citations/lookups
        by the previous spelling keep resolving.
        """
        new_norm = unicodedata.normalize("NFC", new_name)
        entity = await self.get_entity_by_id(entity_id)
        if not entity:
            raise ValueError(f"Entity '{entity_id}' does not exist.")

        old_name = entity.get("canonical_name")
        aliases = list(entity.get("aliases") or [])
        if old_name and old_name not in aliases:
            aliases.append(old_name)
        aliases = [a for a in dict.fromkeys(aliases) if a != new_norm]

        query = "MATCH (e:Entity {id: $id}) SET e.canonical_name = $new_name, e.aliases = $aliases"
        async with self._driver.session() as session:
            await session.run(query, id=entity_id, new_name=new_norm, aliases=aliases)
        return True

    async def delete_relationship_by_id(self, edge_id: str) -> bool:
        """Delete a single RELATED_TO edge by its stable id. Raises ValueError if missing."""
        query = """
        MATCH ()-[r:RELATED_TO {id: $id}]-()
        DELETE r
        RETURN count(r) AS deleted
        """
        async with self._driver.session() as session:
            result = await session.run(query, id=edge_id)
            records = await result.data()
        deleted = records[0]["deleted"] if records else 0
        if deleted == 0:
            raise ValueError(f"No relationship found with id '{edge_id}'.")
        return True

    # ------------------------------------------------------------------
    # Reads used by RAG / public visualization
    # ------------------------------------------------------------------

    async def query_subgraph(
        self, entity_names: List[str], book_ids: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Query 1-hop relationships for a list of entity names to construct context.

        When book_ids is provided (local mode), only relationships extracted from
        those books are returned, preventing cross-book entity noise.
        """
        normalized = [unicodedata.normalize("NFC", n) for n in entity_names if n]
        query = """
        MATCH (e:Entity)-[r:RELATED_TO]->(n:Entity)
        WHERE (
            e.canonical_name IN $entity_names
            OR n.canonical_name IN $entity_names
            OR any(alt IN COALESCE(e.aliases, []) WHERE alt IN $entity_names)
            OR any(alt IN COALESCE(n.aliases, []) WHERE alt IN $entity_names)
        )
          AND ($book_ids IS NULL OR r.book_id IN $book_ids)
        RETURN e.id AS source_id, e.canonical_name AS source, e.type AS source_type,
               r.rel_type AS rel, n.id AS target_id, n.canonical_name AS target, n.type AS target_type
        LIMIT 30
        """
        async with self._driver.session() as session:
            result = await session.run(
                query, entity_names=normalized, book_ids=book_ids
            )
            records = await result.data()
            return records

    async def query_paths(
        self,
        entity_names: List[str],
        book_ids: Optional[List[str]] = None,
        familial_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """Find relationship paths of length 1-4 connecting any pair of search entities.

        When book_ids is provided, only paths consisting entirely of relationships
        extracted from those books are returned.
        """
        if len(entity_names) < 2:
            return []

        normalized = [unicodedata.normalize("NFC", n) for n in entity_names if n]

        familial_rels = [
            "SON_OF",
            "FATHER_OF",
            "DAUGHTER_OF",
            "MOTHER_OF",
            "PARENT_OF",
            "CHILD_OF",
            "GRANDSON_OF",
            "GRANDFATHER_OF",
            "GRANDMOTHER_OF",
            "GRANDDAUGHTER_OF",
            "SPOUSE_OF",
            "WIFE_OF",
            "HUSBAND_OF",
            "BROTHER_OF",
            "SISTER_OF",
            "SIBLING_OF",
        ]

        rel_filter = (
            "all(rel in relationships(p) WHERE rel.rel_type IN $familial_rels)"
            if familial_only
            else "true"
        )

        query = f"""
        MATCH p = (a:Entity)-[r:RELATED_TO*1..4]-(b:Entity)
        WHERE (a.canonical_name IN $entity_names OR any(alt IN COALESCE(a.aliases, []) WHERE alt IN $entity_names))
          AND (b.canonical_name IN $entity_names OR any(alt IN COALESCE(b.aliases, []) WHERE alt IN $entity_names))
          AND a.id < b.id
          AND {rel_filter}
          AND ($book_ids IS NULL OR all(rel in relationships(p) WHERE rel.book_id IN $book_ids))
        UNWIND relationships(p) AS rel
        WITH startNode(rel) AS s, endNode(rel) AS t, rel
        RETURN DISTINCT s.canonical_name AS source, s.type AS source_type, rel.rel_type AS rel,
               t.canonical_name AS target, t.type AS target_type
        LIMIT 40
        """

        async with self._driver.session() as session:
            result = await session.run(
                query,
                entity_names=normalized,
                familial_rels=familial_rels,
                book_ids=book_ids,
            )
            records = await result.data()
            return records

    # ------------------------------------------------------------------
    # Neo4j Graph Data Science (GDS) Integration (Items 5–9)
    # ------------------------------------------------------------------

    async def project_gds_graph(
        self, graph_name: str = "entity_resolution_graph"
    ) -> bool:
        """Projects an in-memory graph using Neo4j GDS procedure `gds.graph.project` (Item 5)."""
        drop_query = "CALL gds.graph.drop($graph_name, false) YIELD graphName"
        project_query = """
        CALL gds.graph.project(
            $graph_name,
            'Entity',
            {
                RELATED_TO: {
                    type: 'RELATED_TO',
                    orientation: 'UNDIRECTED'
                }
            }
        )
        YIELD graphName, nodeCount, relationshipCount
        """
        async with self._driver.session() as session:
            try:
                await session.run(drop_query, graph_name=graph_name)
            except Exception:
                pass
            res = await session.run(project_query, graph_name=graph_name)
            record = await res.single()
            return record is not None

    async def run_gds_node_similarity(
        self,
        graph_name: str = "entity_resolution_graph",
        similarity_cutoff: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """Computes Jaccard neighbor similarity using `gds.nodeSimilarity.stream` (Item 6)."""
        query = """
        CALL gds.nodeSimilarity.stream($graph_name, {similarityCutoff: $cutoff})
        YIELD node1, node2, similarity
        RETURN gds.util.asNode(node1).id AS node1_id,
               gds.util.asNode(node2).id AS node2_id,
               similarity
        """
        async with self._driver.session() as session:
            res = await session.run(
                query, graph_name=graph_name, cutoff=similarity_cutoff
            )
            records = await res.data()
            return records

    async def run_gds_fastrp(
        self,
        graph_name: str = "entity_resolution_graph",
        embedding_dimension: int = 128,
    ) -> None:
        """Computes structural embeddings using `gds.fastRP.mutate` (Item 7)."""
        query = """
        CALL gds.fastRP.mutate($graph_name, {
            mutateProperty: 'fastrp_embedding',
            embeddingDimension: $dim,
            iterationWeights: [0.0, 1.0, 0.7]
        })
        YIELD nodePropertiesWritten
        """
        async with self._driver.session() as session:
            await session.run(query, graph_name=graph_name, dim=embedding_dimension)

    async def store_profile_embeddings_bulk(
        self, profile_data: List[Dict[str, Any]]
    ) -> None:
        """Stores vector profile embeddings on Entity nodes for semantic matching (Item 8)."""
        query = """
        UNWIND $data AS row
        MATCH (e:Entity {id: row.id})
        SET e.profile_embedding = row.embedding
        """
        async with self._driver.session() as session:
            await session.run(query, data=profile_data)

    async def run_gds_knn_similarity(
        self,
        graph_name: str = "entity_resolution_graph",
        top_k: int = 10,
        similarity_cutoff: float = 0.75,
    ) -> List[Dict[str, Any]]:
        """Computes semantic profile vector similarity using `gds.knn.stream` (Item 8)."""
        query = """
        CALL gds.knn.stream($graph_name, {
            nodeProperties: ['profile_embedding'],
            topK: $top_k,
            sampleRate: 1.0,
            similarityCutoff: $cutoff
        })
        YIELD node1, node2, similarity
        RETURN gds.util.asNode(node1).id AS node1_id,
               gds.util.asNode(node2).id AS node2_id,
               similarity
        """
        async with self._driver.session() as session:
            res = await session.run(
                query, graph_name=graph_name, top_k=top_k, cutoff=similarity_cutoff
            )
            records = await res.data()
            return records

    async def run_gds_wcc_clustering(
        self, graph_name: str = "entity_resolution_graph"
    ) -> List[Dict[str, Any]]:
        """Computes Weakly Connected Components using `gds.wcc.stream` (Item 9)."""
        query = """
        CALL gds.wcc.stream($graph_name)
        YIELD nodeId, componentId
        RETURN gds.util.asNode(nodeId).id AS entity_id, componentId AS cluster_id
        """
        async with self._driver.session() as session:
            res = await session.run(query, graph_name=graph_name)
            records = await res.data()
            return records
