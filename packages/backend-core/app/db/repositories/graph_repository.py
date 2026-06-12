"""Repository for interacting with Memgraph using the async Neo4j driver."""
from __future__ import annotations

import logging
import unicodedata
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from neo4j import AsyncGraphDatabase

from app.core.config import settings
from app.utils.observability import log_json

logger = logging.getLogger("app.db.repositories.graph")


class GraphRepository:
    """Repository for interacting with Memgraph using the async Neo4j driver.

    Allows mapping and querying entity-relationship networks of books.
    """
    _driver = None

    def __init__(self, uri: Optional[str] = None) -> None:
        self._uri = uri or settings.memgraph_url
        if GraphRepository._driver is None:
            # Parse credentials from the URI if present, as the Neo4j driver does not support
            # credentials embedded directly in the URI scheme.
            parsed = urlparse(self._uri)
            if parsed.username and parsed.password:
                auth = (parsed.username, parsed.password)
                # Reconstruct clean URI without credentials
                clean_uri = f"{parsed.scheme}://{parsed.hostname}"
                if parsed.port:
                    clean_uri += f":{parsed.port}"
                if parsed.path:
                    clean_uri += parsed.path
            else:
                auth = None
                clean_uri = self._uri

            # liveness_check_timeout=0: verify each pooled connection is alive before
            #   returning it to the caller — prevents "defunct connection" errors that occur
            #   when Memgraph closes an idle connection server-side while it is still in the pool.
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

    @property
    def _driver_instance(self):
        return GraphRepository._driver

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
        """Initialize uniqueness constraints and indexes in Memgraph.

        Ensures MERGE commands perform efficiently without duplicate nodes.
        """
        # Memgraph supports standard Neo4j 3.x constraint syntax
        constraints = [
            "CREATE CONSTRAINT ON (e:Entity) ASSERT e.name IS UNIQUE;",
        ]
        async with self._driver.session() as session:
            for constraint in constraints:
                try:
                    await session.run(constraint)
                except Exception as exc:
                    # Memgraph might raise warnings if index/constraint already exists
                    log_json(logger, logging.DEBUG, "constraint already exists or warning", detail=str(exc))

    async def upsert_entities_bulk(self, entities: List[Dict[str, Any]]) -> None:
        """Create or update Entity nodes in bulk."""
        if not entities:
            return
        normalized = [
            {**e, "name": unicodedata.normalize("NFC", e["name"])} if e.get("name") else e
            for e in entities
        ]
        query = """
        UNWIND $entities_data AS e_data
        MERGE (e:Entity {name: e_data.name})
        SET e.type = e_data.type,
            e.subtype = e_data.subtype
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
        query = """
        UNWIND $relations_data AS rel
        MATCH (s:Entity {name: rel.source_name})
        MATCH (t:Entity {name: rel.target_name})
        MERGE (s)-[r:RELATED_TO {book_id: rel.book_id}]->(t)
        SET r.type = rel.rel_type
        """
        async with self._driver.session() as session:
            await session.run(query, relations_data=relations)

    async def query_subgraph(self, entity_names: List[str], book_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Query 1-hop relationships for a list of entity names to construct context.

        When book_id is provided (single-book mode), only relationships extracted from
        that book are returned, preventing cross-book entity noise.
        """
        normalized = [unicodedata.normalize("NFC", n) for n in entity_names if n]
        query = """
        MATCH (e:Entity)-[r:RELATED_TO]->(n:Entity)
        WHERE (e.name IN $entity_names OR n.name IN $entity_names)
          AND ($book_id IS NULL OR r.book_id = $book_id)
        RETURN e.name AS source, e.type AS source_type, r.type AS rel, n.name AS target, n.type AS target_type
        LIMIT 30
        """
        async with self._driver.session() as session:
            result = await session.run(query, entity_names=normalized, book_id=book_id)
            records = await result.data()
            return records


