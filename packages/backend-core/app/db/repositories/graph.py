"""Repository for interacting with Memgraph using the async Neo4j driver."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from neo4j import AsyncGraphDatabase

from app.core.config import settings
from app.utils.observability import log_json

logger = logging.getLogger("app.db.repositories.graph")


class GraphRepository:
    """Repository for interacting with Memgraph using the async Neo4j driver.

    Allows mapping and querying entity-relationship networks of books.
    """

    def __init__(self, uri: Optional[str] = None) -> None:
        self._uri = uri or settings.memgraph_url
        # Memgraph runs locally without authentication by default
        self._driver = AsyncGraphDatabase.driver(self._uri, auth=None)

    async def close(self) -> None:
        """Close driver session connection pool."""
        await self._driver.close()

    async def init_constraints(self) -> None:
        """Initialize uniqueness constraints and indexes in Memgraph.

        Ensures MERGE commands perform efficiently without duplicate nodes.
        """
        # Memgraph supports standard Neo4j 3.x constraint syntax
        constraints = [
            "CREATE CONSTRAINT ON (b:Book) ASSERT b.id IS UNIQUE;",
            "CREATE CONSTRAINT ON (c:Chunk) ASSERT c.id IS UNIQUE;",
            "CREATE CONSTRAINT ON (e:Entity) ASSERT e.name IS UNIQUE;",
            "CREATE CONSTRAINT ON (a:Author) ASSERT a.name IS UNIQUE;"
        ]
        async with self._driver.session() as session:
            for constraint in constraints:
                try:
                    await session.run(constraint)
                except Exception as exc:
                    # Memgraph might raise warnings if index/constraint already exists
                    log_json(logger, logging.DEBUG, "constraint already exists or warning", detail=str(exc))

    async def upsert_book(
        self,
        book_id: str,
        title: str,
        author: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> None:
        """Create or update a Book node."""
        query = """
        MERGE (b:Book {id: $book_id})
        SET b.title = $title,
            b.author = $author,
            b.summary = $summary
        """
        async with self._driver.session() as session:
            await session.run(
                query,
                book_id=str(book_id),
                title=title,
                author=author,
                summary=summary,
            )

    async def upsert_author(self, name: str, bio: Optional[str] = None) -> None:
        """Create or update an Author node."""
        query = """
        MERGE (a:Author {name: $name})
        SET a.bio = $bio
        """
        async with self._driver.session() as session:
            await session.run(query, name=name, bio=bio)

    async def upsert_chunk(
        self,
        chunk_id: int,
        book_id: str,
        page_number: int,
        text_preview: str,
    ) -> None:
        """Create or update a Chunk node."""
        query = """
        MERGE (c:Chunk {id: $chunk_id})
        SET c.book_id = $book_id,
            c.page_number = $page_number,
            c.text_preview = $text_preview
        """
        async with self._driver.session() as session:
            await session.run(
                query,
                chunk_id=chunk_id,
                book_id=str(book_id),
                page_number=page_number,
                text_preview=text_preview,
            )

    async def upsert_entity(
        self,
        name: str,
        entity_type: str,
        subtype: Optional[str] = None,
    ) -> None:
        """Create or update an Entity node."""
        query = """
        MERGE (e:Entity {name: $name})
        SET e.type = $type,
            e.subtype = $subtype
        """
        async with self._driver.session() as session:
            await session.run(query, name=name, type=entity_type, subtype=subtype)

    async def connect_author_book(self, author_name: str, book_id: str) -> None:
        """Create a WROTE relationship from Author to Book."""
        query = """
        MATCH (a:Author {name: $author_name})
        MATCH (b:Book {id: $book_id})
        MERGE (a)-[:WROTE]->(b)
        """
        async with self._driver.session() as session:
            await session.run(query, author_name=author_name, book_id=str(book_id))

    async def connect_book_chunk(self, book_id: str, chunk_id: int) -> None:
        """Create a HAS_CHUNK relationship from Book to Chunk."""
        query = """
        MATCH (b:Book {id: $book_id})
        MATCH (c:Chunk {id: $chunk_id})
        MERGE (b)-[:HAS_CHUNK]->(c)
        """
        async with self._driver.session() as session:
            await session.run(query, book_id=str(book_id), chunk_id=chunk_id)

    async def connect_chunk_entity(self, chunk_id: int, entity_name: str) -> None:
        """Create a MENTIONS relationship from Chunk to Entity."""
        query = """
        MATCH (c:Chunk {id: $chunk_id})
        MATCH (e:Entity {name: $entity_name})
        MERGE (c)-[:MENTIONS]->(e)
        """
        async with self._driver.session() as session:
            await session.run(query, chunk_id=chunk_id, entity_name=entity_name)

    async def connect_entities(
        self,
        source_name: str,
        rel_type: str,
        target_name: str,
    ) -> None:
        """Create a generic RELATED_TO directed relationship between two Entities.

        The specific semantic relation is stored in the relationship property.
        """
        query = """
        MATCH (s:Entity {name: $source_name})
        MATCH (t:Entity {name: $target_name})
        MERGE (s)-[r:RELATED_TO]->(t)
        SET r.type = $rel_type
        """
        async with self._driver.session() as session:
            await session.run(
                query,
                source_name=source_name,
                target_name=target_name,
                rel_type=rel_type,
            )

    async def query_subgraph(self, entity_names: List[str]) -> List[Dict[str, Any]]:
        """Query 1-hop relationships for a list of entity names to construct context."""
        query = """
        MATCH (e:Entity)-[r:RELATED_TO]->(n:Entity)
        WHERE e.name IN $entity_names OR n.name IN $entity_names
        RETURN e.name AS source, e.type AS source_type, r.type AS rel, n.name AS target, n.type AS target_type
        LIMIT 30
        """
        async with self._driver.session() as session:
            result = await session.run(query, entity_names=entity_names)
            records = await result.data()
            return records

    async def clear_book_graph(self, book_id: str) -> None:
        """Delete all chunk nodes and their associated relationships for a book.

        This leaves Entity nodes intact (as they can be shared globally),
        but deletes the book's specific chunk nodes, HAS_CHUNK, and MENTIONS relationships.
        """
        query = """
        MATCH (b:Book {id: $book_id})
        OPTIONAL MATCH (b)-[r:HAS_CHUNK]->(c:Chunk)
        DETACH DELETE c
        """
        async with self._driver.session() as session:
            await session.run(query, book_id=str(book_id))

    async def connect_book_to_entity(
        self,
        book_id: str,
        entity_name: str,
        rel_type: str,
    ) -> None:
        """Create a directed relationship from a Book node to an Entity node.

        The relationship type is represented dynamically.
        """
        query = """
        MATCH (b:Book {id: $book_id})
        MATCH (e:Entity {name: $entity_name})
        MERGE (b)-[r:RELATED_TO]->(e)
        SET r.type = $rel_type
        """
        async with self._driver.session() as session:
            await session.run(
                query,
                book_id=str(book_id),
                entity_name=entity_name,
                rel_type=rel_type,
            )

    async def check_book_exists(self, book_id: str) -> bool:
        """Check if a Book node exists in Memgraph."""
        query = "MATCH (b:Book {id: $book_id}) RETURN count(b) > 0 AS exists"
        try:
            async with self._driver.session() as session:
                result = await session.run(query, book_id=str(book_id))
                record = await result.single()
                return record["exists"] if record else False
        except Exception as exc:
            log_json(logger, logging.WARNING, "failed to check book existence in Memgraph", error=str(exc))
            return False

    async def check_books_exist(self, book_ids: List[str]) -> set[str]:
        """Check which of the given Book IDs exist in Memgraph."""
        if not book_ids:
            return set()
        query = "MATCH (b:Book) WHERE b.id IN $book_ids RETURN b.id AS id"
        try:
            async with self._driver.session() as session:
                result = await session.run(query, book_ids=[str(bid) for bid in book_ids])
                records = await result.data()
                return {str(record["id"]) for record in records}
        except Exception as exc:
            log_json(logger, logging.WARNING, "failed to check batch book existence in Memgraph", error=str(exc))
            return set()

