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
        WHERE (e.name IN $entity_names OR n.name IN $entity_names)
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
