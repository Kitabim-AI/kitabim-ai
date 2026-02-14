"""PostgreSQL database adapter with pgvector support"""
from __future__ import annotations

import logging
from typing import Any
import asyncpg
from asyncpg.pool import Pool

from app.core.config import settings
from app.utils.observability import log_json


class PostgresDB:
    """PostgreSQL database manager with connection pooling"""

    pool: Pool | None = None

    async def connect_to_storage(self) -> None:
        """Initialize PostgreSQL connection pool"""
        logger = logging.getLogger("app.db")

        try:
            # Parse DATABASE_URL from env
            database_url = getattr(settings, 'database_url', None) or settings.mongodb_url.replace('mongodb://', 'postgresql://')

            # Parse URL to extract connection parameters
            # asyncpg has issues with connection pooling on some systems when using DSN
            # So we parse the URL and pass parameters explicitly
            from urllib.parse import urlparse
            parsed = urlparse(database_url)

            conn_params = {
                'host': parsed.hostname or 'localhost',
                'port': parsed.port or 5432,
                'user': parsed.username,
                'database': parsed.path.lstrip('/') if parsed.path else 'kitabim_ai',
                'min_size': 1,  # Reduce min_size to avoid connection issues on local dev
                'max_size': 10,
                'timeout': 30,  # Connection timeout
                'command_timeout': 60,
                'ssl': False,  # Disable SSL for local development
            }

            # Add password if provided
            if parsed.password:
                conn_params['password'] = parsed.password

            self.pool = await asyncpg.create_pool(**conn_params)

            # Test connection
            async with self.pool.acquire() as conn:
                version = await conn.fetchval('SELECT version()')
                log_json(logger, logging.INFO, "PostgreSQL connected", version=version[:50])

            await self._ensure_schema()

        except Exception as exc:
            log_json(logger, logging.ERROR, "PostgreSQL connection failed", error=str(exc))
            raise

    async def close_storage(self) -> None:
        """Close PostgreSQL connection pool"""
        if self.pool:
            await self.pool.close()

    async def _ensure_schema(self) -> None:
        """Ensure database schema and indexes exist"""
        logger = logging.getLogger("app.db")

        if not self.pool:
            return

        async with self.pool.acquire() as conn:
            # Check if tables exist
            tables_exist = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'books'
                )
            """)

            if not tables_exist:
                log_json(logger, logging.INFO, "Initializing database schema")
                # Schema will be created by init-db.sql on first run
                # This is just a check
                log_json(logger, logging.WARNING, "Database tables not found - run init-db.sql first")

    async def acquire(self):
        """Acquire a connection from the pool (context manager)"""
        if not self.pool:
            raise RuntimeError("Database not connected")
        return self.pool.acquire()

    async def fetch(self, query: str, *args) -> list[asyncpg.Record]:
        """Execute a query and fetch all results"""
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args) -> asyncpg.Record | None:
        """Execute a query and fetch one result"""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args) -> Any:
        """Execute a query and fetch a single value"""
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args)

    async def execute(self, query: str, *args) -> str:
        """Execute a query without returning results"""
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def executemany(self, query: str, args_list: list) -> None:
        """Execute a query multiple times with different arguments"""
        async with self.pool.acquire() as conn:
            await conn.executemany(query, args_list)


db_manager = PostgresDB()


async def get_db():
    """Get database connection - FastAPI dependency"""
    return db_manager


# Repository pattern helpers for common operations

class BooksRepository:
    """Repository for books table operations"""

    def __init__(self, db: PostgresDB):
        self.db = db

    async def find_one(self, book_id: str) -> dict | None:
        """Find a book by ID"""
        row = await self.db.fetchrow(
            "SELECT * FROM books WHERE id = $1",
            book_id
        )
        return dict(row) if row else None

    async def find_by_hash(self, content_hash: str) -> dict | None:
        """Find a book by content hash"""
        row = await self.db.fetchrow(
            "SELECT * FROM books WHERE content_hash = $1",
            content_hash
        )
        return dict(row) if row else None

    async def insert(self, book_data: dict) -> str:
        """Insert a new book and return its ID"""
        row = await self.db.fetchrow("""
            INSERT INTO books (
                id, content_hash, title, author, volume, total_pages,
                status, visibility, created_by, categories, tags
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            RETURNING id
        """,
            book_data['id'], book_data['contentHash'], book_data['title'],
            book_data.get('author'), book_data.get('volume'), book_data.get('totalPages', 0),
            book_data.get('status', 'pending'), book_data.get('visibility', 'private'),
            book_data.get('createdBy'), book_data.get('categories', []),
            book_data.get('tags', [])
        )
        return row['id']

    async def update(self, book_id: str, updates: dict) -> None:
        """Update a book"""
        # Build dynamic UPDATE query
        set_clauses = []
        values = []
        param_idx = 1

        for key, value in updates.items():
            # Convert camelCase to snake_case
            snake_key = ''.join(['_' + c.lower() if c.isupper() else c for c in key]).lstrip('_')
            set_clauses.append(f"{snake_key} = ${param_idx}")
            values.append(value)
            param_idx += 1

        values.append(book_id)
        query = f"UPDATE books SET {', '.join(set_clauses)} WHERE id = ${param_idx}"
        await self.db.execute(query, *values)

    async def delete(self, book_id: str) -> None:
        """Delete a book (cascades to pages and chunks)"""
        await self.db.execute("DELETE FROM books WHERE id = $1", book_id)

    async def find_many(
        self,
        status: str | None = None,
        visibility: str | None = None,
        limit: int = 100,
        offset: int = 0,
        sort_by: str = 'upload_date',
        sort_order: str = 'DESC'
    ) -> list[dict]:
        """Find multiple books with filtering and pagination"""
        conditions = []
        values = []
        param_idx = 1

        if status:
            conditions.append(f"status = ${param_idx}")
            values.append(status)
            param_idx += 1

        if visibility:
            conditions.append(f"visibility = ${param_idx}")
            values.append(visibility)
            param_idx += 1

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        query = f"""
            SELECT * FROM books
            {where_clause}
            ORDER BY {sort_by} {sort_order}
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        values.extend([limit, offset])

        rows = await self.db.fetch(query, *values)
        return [dict(row) for row in rows]


class PagesRepository:
    """Repository for pages table operations"""

    def __init__(self, db: PostgresDB):
        self.db = db

    async def find_one(self, book_id: str, page_number: int) -> dict | None:
        """Find a page by book ID and page number"""
        row = await self.db.fetchrow(
            "SELECT * FROM pages WHERE book_id = $1 AND page_number = $2",
            book_id, page_number
        )
        return dict(row) if row else None

    async def find_by_book(self, book_id: str) -> list[dict]:
        """Find all pages for a book"""
        rows = await self.db.fetch(
            "SELECT * FROM pages WHERE book_id = $1 ORDER BY page_number",
            book_id
        )
        return [dict(row) for row in rows]

    async def upsert(self, page_data: dict) -> None:
        """Insert or update a page"""
        await self.db.execute("""
            INSERT INTO pages (
                book_id, page_number, text, status, embedding,
                is_verified, error, ocr_provider, updated_by
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (book_id, page_number)
            DO UPDATE SET
                text = EXCLUDED.text,
                status = EXCLUDED.status,
                embedding = EXCLUDED.embedding,
                is_verified = EXCLUDED.is_verified,
                error = EXCLUDED.error,
                ocr_provider = EXCLUDED.ocr_provider,
                updated_by = EXCLUDED.updated_by,
                last_updated = NOW()
        """,
            page_data['book_id'], page_data['page_number'],
            page_data.get('text', ''), page_data.get('status', 'pending'),
            page_data.get('embedding'), page_data.get('is_verified', False),
            page_data.get('error'), page_data.get('ocr_provider'),
            page_data.get('updated_by')
        )

    async def update_status(self, book_id: str, page_number: int, status: str) -> None:
        """Update page status"""
        await self.db.execute("""
            UPDATE pages SET status = $3, last_updated = NOW()
            WHERE book_id = $1 AND page_number = $2
        """, book_id, page_number, status)


class ChunksRepository:
    """Repository for chunks table operations (RAG)"""

    def __init__(self, db: PostgresDB):
        self.db = db

    async def insert_many(self, chunks: list[dict]) -> None:
        """Insert multiple chunks"""
        if not chunks:
            return

        await self.db.executemany("""
            INSERT INTO chunks (book_id, page_number, chunk_index, text, embedding)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (book_id, page_number, chunk_index)
            DO UPDATE SET
                text = EXCLUDED.text,
                embedding = EXCLUDED.embedding
        """, [
            (c['book_id'], c['page_number'], c['chunk_index'], c['text'], c['embedding'])
            for c in chunks
        ])

    async def delete_by_book(self, book_id: str) -> None:
        """Delete all chunks for a book"""
        await self.db.execute("DELETE FROM chunks WHERE book_id = $1", book_id)

    async def delete_by_page(self, book_id: str, page_number: int) -> None:
        """Delete chunks for a specific page"""
        await self.db.execute(
            "DELETE FROM chunks WHERE book_id = $1 AND page_number = $2",
            book_id, page_number
        )

    async def find_by_books(self, book_ids: list[str]) -> list[dict]:
        """Find chunks for multiple books"""
        rows = await self.db.fetch("""
            SELECT book_id, page_number, chunk_index, text, embedding
            FROM chunks
            WHERE book_id = ANY($1)
        """, book_ids)
        return [dict(row) for row in rows]

    async def similarity_search(
        self,
        query_embedding: list[float],
        book_ids: list[str] | None = None,
        limit: int = 12,
        threshold: float = 0.35
    ) -> list[dict]:
        """Search for similar chunks using cosine similarity"""
        if book_ids:
            query = """
                SELECT
                    book_id,
                    page_number,
                    text,
                    1 - (embedding <=> $1::vector) AS similarity
                FROM chunks
                WHERE book_id = ANY($2)
                  AND 1 - (embedding <=> $1::vector) > $3
                ORDER BY similarity DESC
                LIMIT $4
            """
            rows = await self.db.fetch(query, query_embedding, book_ids, threshold, limit)
        else:
            query = """
                SELECT
                    book_id,
                    page_number,
                    text,
                    1 - (embedding <=> $1::vector) AS similarity
                FROM chunks
                WHERE 1 - (embedding <=> $1::vector) > $2
                ORDER BY similarity DESC
                LIMIT $3
            """
            rows = await self.db.fetch(query, query_embedding, threshold, limit)

        return [dict(row) for row in rows]


# Export repository factory
def get_books_repo(db: PostgresDB) -> BooksRepository:
    return BooksRepository(db)


def get_pages_repo(db: PostgresDB) -> PagesRepository:
    return PagesRepository(db)


def get_chunks_repo(db: PostgresDB) -> ChunksRepository:
    return ChunksRepository(db)
