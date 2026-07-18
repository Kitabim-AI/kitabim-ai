"""Repository for interacting with Neo4j using the async Neo4j driver."""

from __future__ import annotations

import logging
import unicodedata
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from neo4j import AsyncGraphDatabase
from neo4j.exceptions import ClientError

from app.core.config import settings
from app.utils.observability import log_json

logger = logging.getLogger("app.db.repositories.graph")


class GraphRepository:
    """Repository for interacting with Neo4j using the async Neo4j driver.

    Allows mapping and querying entity-relationship networks of books.
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

        Ensures MERGE commands perform efficiently without duplicate nodes.
        """
        # Neo4j 5 uses FOR ... REQUIRE ... IS UNIQUE syntax
        constraints = [
            "CREATE CONSTRAINT entity_name_unique IF NOT EXISTS FOR (e:Entity) REQUIRE e.name IS UNIQUE;",
        ]
        async with self._driver.session() as session:
            for constraint in constraints:
                try:
                    await session.run(constraint)
                except ClientError as exc:
                    # Neo4j raises ClientError when a constraint already exists
                    # (IF NOT EXISTS is not always honoured). Let real connection errors
                    # (ServiceUnavailable, AuthError) propagate so the caller knows
                    # the graph DB is unreachable.
                    log_json(
                        logger,
                        logging.DEBUG,
                        "constraint already exists or schema warning",
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

    async def upsert_entities_bulk(self, entities: List[Dict[str, Any]]) -> None:
        """Create or update Entity nodes in bulk."""
        if not entities:
            return
        normalized = [
            {
                "name": unicodedata.normalize("NFC", e["name"])
                if e.get("name")
                else None,
                "type": e.get("type"),
                "subtype": e.get("subtype"),
                "year_hijri": e.get("year_hijri"),
                "year_gregorian": e.get("year_gregorian"),
                "century_gregorian": e.get("century_gregorian"),
            }
            for e in entities
        ]
        query = """
        UNWIND $entities_data AS e_data
        MERGE (e:Entity {name: e_data.name})
        SET e.type = e_data.type,
            e.subtype = e_data.subtype,
            e.year_hijri = COALESCE(e_data.year_hijri, e.year_hijri),
            e.year_gregorian = COALESCE(e_data.year_gregorian, e.year_gregorian),
            e.century_gregorian = COALESCE(e_data.century_gregorian, e.century_gregorian)
        """
        async with self._driver.session() as session:
            await session.run(query, entities_data=normalized)

    async def connect_entities_bulk(self, relations: List[Dict[str, Any]]) -> None:
        """Create RELATED_TO relationships between Entities in bulk.

        Each relation dict must include book_id so edges from different books
        are stored as separate edges and never overwrite each other.
        """
        if not relations:
            return
        normalized = [
            {
                "source_name": r.get("source_name"),
                "rel_type": r.get("rel_type"),
                "target_name": r.get("target_name"),
                "book_id": r.get("book_id"),
                "year_hijri": r.get("year_hijri"),
                "year_gregorian": r.get("year_gregorian"),
                "century_gregorian": r.get("century_gregorian"),
            }
            for r in relations
        ]
        query = """
        UNWIND $relations_data AS rel
        MATCH (s:Entity {name: rel.source_name})
        MATCH (t:Entity {name: rel.target_name})
        MERGE (s)-[r:RELATED_TO {book_id: rel.book_id}]->(t)
        SET r.type = rel.rel_type,
            r.year_hijri = rel.year_hijri,
            r.year_gregorian = rel.year_gregorian,
            r.century_gregorian = rel.century_gregorian
        """
        async with self._driver.session() as session:
            await session.run(query, relations_data=normalized)

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

    async def delete_relationship(
        self, source_name: str, target_name: str, rel_type: str
    ) -> bool:
        """Delete every RELATED_TO edge of a given type between two entities.

        Matches on (source_name, target_name, rel_type) and removes all matching
        edges, including duplicates from different books (book_id is not part of
        the match). Raises ValueError if no matching edge exists.
        """
        source_norm = unicodedata.normalize("NFC", source_name)
        target_norm = unicodedata.normalize("NFC", target_name)

        query = """
        MATCH (a:Entity {name: $source_name})-[r:RELATED_TO {type: $rel_type}]->(b:Entity {name: $target_name})
        DELETE r
        RETURN count(r) AS deleted
        """
        async with self._driver.session() as session:
            result = await session.run(
                query,
                source_name=source_norm,
                target_name=target_norm,
                rel_type=rel_type,
            )
            records = await result.data()

        deleted = records[0]["deleted"] if records else 0
        if deleted == 0:
            raise ValueError(
                f"No '{rel_type}' relationship found between '{source_name}' and '{target_name}'."
            )
        return True

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
            e.name IN $entity_names 
            OR n.name IN $entity_names
            OR any(alt IN COALESCE(e.aliases, []) WHERE alt IN $entity_names)
            OR any(alt IN COALESCE(n.aliases, []) WHERE alt IN $entity_names)
        )
          AND ($book_ids IS NULL OR r.book_id IN $book_ids)
        RETURN e.name AS source, e.type AS source_type, r.type AS rel, n.name AS target, n.type AS target_type
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
            "all(rel in relationships(p) WHERE rel.type IN $familial_rels)"
            if familial_only
            else "true"
        )

        query = f"""
        MATCH p = (a:Entity)-[r:RELATED_TO*1..4]-(b:Entity)
        WHERE (a.name IN $entity_names OR any(alt IN COALESCE(a.aliases, []) WHERE alt IN $entity_names))
          AND (b.name IN $entity_names OR any(alt IN COALESCE(b.aliases, []) WHERE alt IN $entity_names))
          AND a.name < b.name
          AND {rel_filter}
          AND ($book_ids IS NULL OR all(rel in relationships(p) WHERE rel.book_id IN $book_ids))
        UNWIND relationships(p) AS rel
        WITH startNode(rel) AS s, endNode(rel) AS t, rel
        RETURN DISTINCT s.name AS source, s.type AS source_type, rel.type AS rel, t.name AS target, t.type AS target_type
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

    async def merge_entities(self, keep_name: str, remove_name: str) -> bool:
        """Merge a duplicate entity node into a target entity node in Neo4j.

        Normalizes properties, moves all relationships, and deletes the duplicate.
        Returns True if successful, raises ValueError if keep_name or remove_name is not found.
        """
        keep_norm = unicodedata.normalize("NFC", keep_name)
        remove_norm = unicodedata.normalize("NFC", remove_name)

        # First, check if both entities exist
        check_query = """
        MATCH (e:Entity)
        WHERE e.name IN [$keep, $remove]
        RETURN e.name AS name, e.aliases AS aliases
        """
        async with self._driver.session() as session:
            result = await session.run(check_query, keep=keep_norm, remove=remove_norm)
            records = await result.data()

        found = {r["name"] for r in records}
        if keep_norm not in found:
            raise ValueError(f"Target entity to keep '{keep_name}' does not exist.")
        if remove_norm not in found:
            raise ValueError(
                f"Duplicate entity to remove '{remove_name}' does not exist."
            )

        # Extract current aliases and combine/deduplicate them in Python
        keep_aliases = []
        remove_aliases = []
        for r in records:
            if r["name"] == keep_norm:
                keep_aliases = r.get("aliases") or []
            elif r["name"] == remove_norm:
                remove_aliases = r.get("aliases") or []

        combined_aliases = list(
            dict.fromkeys(
                [
                    a
                    for a in keep_aliases + [remove_norm] + remove_aliases
                    if a and a != keep_norm
                ]
            )
        )

        # Perform the merge Cypher statement in a session transaction
        merge_query = """
        MATCH (keep:Entity {name: $keep})
        MATCH (remove:Entity {name: $remove})

        // Copy properties to keep node if not already present
        SET keep.type = COALESCE(keep.type, remove.type),
            keep.subtype = COALESCE(keep.subtype, remove.subtype),
            keep.year_hijri = COALESCE(keep.year_hijri, remove.year_hijri),
            keep.year_gregorian = COALESCE(keep.year_gregorian, remove.year_gregorian),
            keep.century_gregorian = COALESCE(keep.century_gregorian, remove.century_gregorian),
            keep.aliases = $combined_aliases

        WITH keep, remove
 
        // Migrate outgoing relationships
        OPTIONAL MATCH (remove)-[r_out:RELATED_TO]->(target:Entity)
        FOREACH (ignored IN case when r_out is not null then [1] else [] end |
            MERGE (keep)-[new_out:RELATED_TO {book_id: r_out.book_id}]->(target)
            SET new_out.type = COALESCE(new_out.type, r_out.type),
                new_out.year_hijri = COALESCE(new_out.year_hijri, r_out.year_hijri),
                new_out.year_gregorian = COALESCE(new_out.year_gregorian, r_out.year_gregorian),
                new_out.century_gregorian = COALESCE(new_out.century_gregorian, r_out.century_gregorian)
        )
        WITH keep, remove, r_out
        DELETE r_out
 
        WITH keep, remove
 
        // Migrate incoming relationships
        OPTIONAL MATCH (source:Entity)-[r_inc:RELATED_TO]->(remove)
        FOREACH (ignored IN case when r_inc is not null then [1] else [] end |
            MERGE (source)-[new_inc:RELATED_TO {book_id: r_inc.book_id}]->(keep)
            SET new_inc.type = COALESCE(new_inc.type, r_inc.type),
                new_inc.year_hijri = COALESCE(new_inc.year_hijri, r_inc.year_hijri),
                new_inc.year_gregorian = COALESCE(new_inc.year_gregorian, r_inc.year_gregorian),
                new_inc.century_gregorian = COALESCE(new_inc.century_gregorian, r_inc.century_gregorian)
        )
        WITH keep, remove, r_inc
        DELETE r_inc
 
        WITH remove
        DELETE remove
        """
        async with self._driver.session() as session:
            await session.run(
                merge_query,
                keep=keep_norm,
                remove=remove_norm,
                combined_aliases=combined_aliases,
            )
        return True
