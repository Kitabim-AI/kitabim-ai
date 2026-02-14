"""
PostgreSQL adapter with MongoDB-compatible interface for easier migration
"""
from __future__ import annotations
from typing import Any, Optional
from datetime import datetime
import json

from app.db.postgres import db_manager, get_books_repo, get_pages_repo, get_chunks_repo


class PostgreSQLCollection:
    """MongoDB-compatible collection interface for PostgreSQL"""

    def __init__(self, table_name: str):
        self.table_name = table_name
        self._repo = None

    def _get_repo(self):
        """Get the appropriate repository for this collection"""
        if self.table_name == "books":
            return get_books_repo(db_manager)
        elif self.table_name == "pages":
            return get_pages_repo(db_manager)
        elif self.table_name == "chunks":
            return get_chunks_repo(db_manager)
        return None

    async def find_one(self, filter_dict: dict) -> dict | None:
        """Find one document matching the filter"""
        if self.table_name == "books":
            if "id" in filter_dict or "_id" in filter_dict:
                book_id = filter_dict.get("id") or str(filter_dict.get("_id"))
                repo = get_books_repo(db_manager)
                return await repo.find_one(book_id)
            elif "contentHash" in filter_dict:
                repo = get_books_repo(db_manager)
                return await repo.find_by_hash(filter_dict["contentHash"])

        elif self.table_name == "pages":
            if "bookId" in filter_dict and "pageNumber" in filter_dict:
                repo = get_pages_repo(db_manager)
                return await repo.find_one(
                    filter_dict["bookId"],
                    filter_dict["pageNumber"]
                )

        # Fallback: construct SQL query (basic support)
        where_clauses, params = self._build_where(filter_dict)
        query = f"SELECT * FROM {self.table_name} WHERE {where_clauses} LIMIT 1"
        row = await db_manager.fetchrow(query, *params)
        return dict(row) if row else None

    async def find(self, filter_dict: dict | None = None, sort: list | None = None, skip: int = 0, limit: int = 0) -> AsyncCursor:
        """Find documents matching the filter - returns async cursor"""
        return AsyncCursor(self.table_name, filter_dict or {}, sort, skip, limit)

    async def count_documents(self, filter_dict: dict) -> int:
        """Count documents matching the filter"""
        where_clauses, params = self._build_where(filter_dict)
        query = f"SELECT COUNT(*) FROM {self.table_name}"
        if where_clauses:
            query += f" WHERE {where_clauses}"
        return await db_manager.fetchval(query, *params)

    async def insert_one(self, document: dict) -> Any:
        """Insert a single document"""
        # This needs to be implemented per collection type
        # For now, return a stub
        raise NotImplementedError(f"insert_one not yet implemented for {self.table_name}")

    async def update_one(self, filter_dict: dict, update_dict: dict) -> Any:
        """Update a single document"""
        # Extract the $set operator
        updates = update_dict.get("$set", {})

        # Build SET clause
        set_clauses = []
        params = []
        param_idx = 1

        for key, value in updates.items():
            # Convert camelCase to snake_case
            snake_key = ''.join(['_' + c.lower() if c.isupper() else c for c in key]).lstrip('_')
            set_clauses.append(f"{snake_key} = ${param_idx}")
            params.append(value)
            param_idx += 1

        # Build WHERE clause
        where_clauses, where_params = self._build_where(filter_dict, start_idx=param_idx)
        params.extend(where_params)

        query = f"UPDATE {self.table_name} SET {', '.join(set_clauses)} WHERE {where_clauses}"
        return await db_manager.execute(query, *params)

    async def update_many(self, filter_dict: dict, update_dict: dict) -> Any:
        """Update multiple documents"""
        return await self.update_one(filter_dict, update_dict)  # Same implementation for now

    async def delete_one(self, filter_dict: dict) -> Any:
        """Delete a single document"""
        where_clauses, params = self._build_where(filter_dict)
        query = f"DELETE FROM {self.table_name} WHERE {where_clauses}"
        return await db_manager.execute(query, *params)

    async def delete_many(self, filter_dict: dict) -> Any:
        """Delete multiple documents"""
        return await self.delete_one(filter_dict)

    def _build_where(self, filter_dict: dict, start_idx: int = 1) -> tuple[str, list]:
        """Build WHERE clause from MongoDB-style filter"""
        clauses = []
        params = []
        idx = start_idx

        for key, value in filter_dict.items():
            # Convert camelCase to snake_case
            snake_key = ''.join(['_' + c.lower() if c.isupper() else c for c in key]).lstrip('_')

            if isinstance(value, dict):
                # Handle operators like $exists, $ne, $gt, etc.
                for op, op_value in value.items():
                    if op == "$exists":
                        if op_value:
                            clauses.append(f"{snake_key} IS NOT NULL")
                        else:
                            clauses.append(f"{snake_key} IS NULL")
                    elif op == "$ne":
                        clauses.append(f"{snake_key} != ${idx}")
                        params.append(op_value)
                        idx += 1
                    elif op == "$gt":
                        clauses.append(f"{snake_key} > ${idx}")
                        params.append(op_value)
                        idx += 1
                    elif op == "$gte":
                        clauses.append(f"{snake_key} >= ${idx}")
                        params.append(op_value)
                        idx += 1
                    elif op == "$lt":
                        clauses.append(f"{snake_key} < ${idx}")
                        params.append(op_value)
                        idx += 1
                    elif op == "$lte":
                        clauses.append(f"{snake_key} <= ${idx}")
                        params.append(op_value)
                        idx += 1
                    elif op == "$in":
                        clauses.append(f"{snake_key} = ANY(${idx})")
                        params.append(op_value)
                        idx += 1
            else:
                # Simple equality
                clauses.append(f"{snake_key} = ${idx}")
                params.append(value)
                idx += 1

        return " AND ".join(clauses) if clauses else "1=1", params


class AsyncCursor:
    """MongoDB-compatible async cursor for PostgreSQL"""

    def __init__(self, table_name: str, filter_dict: dict, sort: list | None, skip: int, limit: int):
        self.table_name = table_name
        self.filter_dict = filter_dict
        self.sort = sort
        self.skip = skip
        self.limit = limit
        self._results = None

    async def to_list(self, length: int | None = None) -> list[dict]:
        """Fetch all results as a list"""
        if self._results is None:
            await self._execute()

        if length is not None:
            return self._results[:length]
        return self._results

    async def _execute(self):
        """Execute the query and cache results"""
        collection = PostgreSQLCollection(self.table_name)
        where_clauses, params = collection._build_where(self.filter_dict)

        query = f"SELECT * FROM {self.table_name}"
        if where_clauses and where_clauses != "1=1":
            query += f" WHERE {where_clauses}"

        # Add sorting
        if self.sort:
            order_clauses = []
            for field, direction in self.sort:
                snake_field = ''.join(['_' + c.lower() if c.isupper() else c for c in field]).lstrip('_')
                order_clauses.append(f"{snake_field} {'ASC' if direction == 1 else 'DESC'}")
            query += f" ORDER BY {', '.join(order_clauses)}"

        # Add pagination
        param_idx = len(params) + 1
        if self.limit > 0:
            query += f" LIMIT ${param_idx}"
            params.append(self.limit)
            param_idx += 1

        if self.skip > 0:
            query += f" OFFSET ${param_idx}"
            params.append(self.skip)

        rows = await db_manager.fetch(query, *params)
        self._results = [dict(row) for row in rows]

    def sort(self, field: str, direction: int = 1):
        """Add sorting"""
        if self.sort is None:
            self.sort = []
        self.sort.append((field, direction))
        return self

    def skip(self, count: int):
        """Skip documents"""
        self.skip = count
        return self

    def limit(self, count: int):
        """Limit results"""
        self.limit = count
        return self


class PostgreSQLDatabase:
    """MongoDB-compatible database interface for PostgreSQL"""

    def __init__(self):
        self.books = PostgreSQLCollection("books")
        self.pages = PostgreSQLCollection("pages")
        self.chunks = PostgreSQLCollection("chunks")
        self.users = PostgreSQLCollection("users")
        self.refresh_tokens = PostgreSQLCollection("refresh_tokens")
        self.jobs = PostgreSQLCollection("jobs")


# Create a compatible db_manager
class CompatibilityDBManager:
    """Database manager with MongoDB-compatible interface"""

    def __init__(self):
        self._pg_manager = db_manager
        self.db = None

    async def connect_to_storage(self):
        """Connect to PostgreSQL"""
        await self._pg_manager.connect_to_storage()
        self.db = PostgreSQLDatabase()

    async def close_storage(self):
        """Close PostgreSQL connection"""
        await self._pg_manager.close_storage()

    @property
    def pool(self):
        """Get the connection pool"""
        return self._pg_manager.pool

    @property
    def client(self):
        """Compatibility property - returns pool"""
        return self._pg_manager.pool


# Export the compatibility manager
compat_db_manager = CompatibilityDBManager()
