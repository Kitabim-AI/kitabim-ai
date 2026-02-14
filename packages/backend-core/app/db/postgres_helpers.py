"""
Helper functions for PostgreSQL database operations
Provides MongoDB-like interface for easier migration
"""
from typing import Any, Optional, List, Dict
from datetime import datetime
import json
from app.db.postgres import db_manager


class PGQueryBuilder:
    """Helper to build PostgreSQL queries from MongoDB-like filters"""

    @staticmethod
    def build_filter_clause(filters: dict, table_name: str, start_param: int = 1) -> tuple[str, list, int]:
        """
        Convert MongoDB-style filter to PostgreSQL WHERE clause

        Returns: (where_clause, params, next_param_num)
        """
        if not filters:
            return "TRUE", [], start_param

        clauses = []
        params = []
        param_num = start_param

        for key, value in filters.items():
            # Handle special operators
            if key == "$and":
                and_clauses = []
                for subfilter in value:
                    clause, subparams, param_num = PGQueryBuilder.build_filter_clause(
                        subfilter, table_name, param_num
                    )
                    and_clauses.append(f"({clause})")
                    params.extend(subparams)
                clauses.append(f"({' AND '.join(and_clauses)})")
                continue

            if key == "$or":
                or_clauses = []
                for subfilter in value:
                    clause, subparams, param_num = PGQueryBuilder.build_filter_clause(
                        subfilter, table_name, param_num
                    )
                    or_clauses.append(f"({clause})")
                    params.extend(subparams)
                clauses.append(f"({' OR '.join(or_clauses)})")
                continue

            # Convert field name from camelCase to snake_case
            field = PGQueryBuilder.camel_to_snake(key)

            # Handle operators in value
            if isinstance(value, dict):
                for op, op_value in value.items():
                    if op == "$exists":
                        clauses.append(f"{field} IS {'NOT ' if not op_value else ''}NULL")
                    elif op == "$ne":
                        clauses.append(f"({field} IS NULL OR {field} != ${param_num})")
                        params.append(op_value)
                        param_num += 1
                    elif op == "$in":
                        if field in ('categories', 'tags'):
                            clauses.append(f"{field} && ${param_num}")
                        else:
                            clauses.append(f"{field} = ANY(${param_num})")
                        params.append(list(op_value))
                        param_num += 1
                    elif op == "$nin":
                        clauses.append(f"({field} IS NULL OR {field} != ALL(${param_num}))")
                        params.append(list(op_value))
                        param_num += 1
                    elif op == "$gt":
                        clauses.append(f"{field} > ${param_num}")
                        params.append(op_value)
                        param_num += 1
                    elif op == "$gte":
                        clauses.append(f"{field} >= ${param_num}")
                        params.append(op_value)
                        param_num += 1
                    elif op == "$lt":
                        clauses.append(f"{field} < ${param_num}")
                        params.append(op_value)
                        param_num += 1
                    elif op == "$lte":
                        clauses.append(f"{field} <= ${param_num}")
                        params.append(op_value)
                        param_num += 1
                    elif op == "$regex":
                        # MongoDB regex to PostgreSQL
                        options = value.get("$options", "")
                        case_insensitive = "i" in options if isinstance(options, str) else False
                        clauses.append(f"{field} ~{'*' if case_insensitive else ''} ${param_num}")
                        params.append(op_value)
                        param_num += 1
            else:
                # Simple equality
                clauses.append(f"{field} = ${param_num}")
                params.append(value)
                param_num += 1

        where_clause = " AND ".join(clauses) if clauses else "TRUE"
        return where_clause, params, param_num

    @staticmethod
    def snake_to_camel(name: str) -> str:
        """Convert snake_case to camelCase"""
        if name == "id" or name == "_id":
            return "id"

        # Special case mappings (reverse of camel_to_snake)
        special_cases = {
            "book_id": "bookId",
            "page_number": "pageNumber",
            "content_hash": "contentHash",
            "total_pages": "totalPages",
            "upload_date": "uploadDate",
            "last_updated": "lastUpdated",
            "updated_by": "updatedBy",
            "created_by": "createdBy",
            "cover_url": "coverUrl",
            "processing_step": "processingStep",
            "last_error": "lastError",
            "completed_count": "completedCount",
            "error_count": "errorCount",
            "processing_lock_expires_at": "processingLockExpiresAt",
            "job_key": "jobKey",
            "created_at": "createdAt",
            "updated_at": "updatedAt",
            "chunk_index": "chunkIndex",
        }

        if name in special_cases:
            return special_cases[name]

        # Generic conversion: snake_case -> camelCase
        components = name.split('_')
        return components[0] + ''.join(x.title() for x in components[1:])

    @staticmethod
    def camel_to_snake(name: str) -> str:
        """Convert camelCase to snake_case"""
        import re
        # Handle special cases
        if name == "id" or name == "_id":
            return "id"
        if name == "bookId":
            return "book_id"
        if name == "pageNumber":
            return "page_number"
        if name == "contentHash":
            return "content_hash"

        # General conversion
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

    @staticmethod
    def dict_to_snake_case(d: dict) -> dict:
        """Convert all keys in dict from camelCase to snake_case"""
        return {PGQueryBuilder.camel_to_snake(k): v for k, v in d.items()}


def convert_row_to_camel(row: dict, table_name: str = None) -> dict:
    """Convert all keys in a row from snake_case to camelCase and parse JSON fields"""
    if not row:
        return row

    # Skip conversion for system tables that use snake_case in their models
    if table_name in ('users', 'refresh_tokens'):
        return row

    # Fields that should be parsed from JSON strings
    json_fields = {'errors', 'last_error', 'metadata'}

    result = {}
    for k, v in row.items():
        camel_key = PGQueryBuilder.snake_to_camel(k)

        # Parse JSON string fields
        if k in json_fields and isinstance(v, str) and v:
            try:
                result[camel_key] = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                result[camel_key] = v
        else:
            result[camel_key] = v

    return result


async def pg_find_one(table: str, filter_dict: dict) -> Optional[dict]:
    """Find one record - MongoDB compatible"""
    where_clause, params, _ = PGQueryBuilder.build_filter_clause(filter_dict, table)
    query = f"SELECT * FROM {table} WHERE {where_clause} LIMIT 1"
    row = await db_manager.fetchrow(query, *params)
    return convert_row_to_camel(dict(row), table) if row else None


async def pg_find(
    table: str,
    filter_dict: dict = None,
    projection: dict = None,
    sort: List[tuple] = None,
    skip: int = 0,
    limit: int = 0
) -> List[dict]:
    """Find multiple records - MongoDB compatible"""
    filter_dict = filter_dict or {}

    # Build SELECT clause
    if projection:
        # Exclude fields with 0, include fields with 1
        excluded = [PGQueryBuilder.camel_to_snake(k) for k, v in projection.items() if v == 0]
        if excluded:
            # Get all columns first (would need schema info, so just select *)
            select_clause = "*"  # TODO: Implement column exclusion
        else:
            included = [PGQueryBuilder.camel_to_snake(k) for k, v in projection.items() if v == 1]
            select_clause = ", ".join(included) if included else "*"
    else:
        select_clause = "*"

    where_clause, params, param_num = PGQueryBuilder.build_filter_clause(filter_dict, table)
    query = f"SELECT {select_clause} FROM {table} WHERE {where_clause}"

    # Add ORDER BY
    if sort:
        order_parts = []
        for field, direction in sort:
            snake_field = PGQueryBuilder.camel_to_snake(field)
            order_parts.append(f"{snake_field} {'DESC' if direction == -1 else 'ASC'}")
        query += f" ORDER BY {', '.join(order_parts)}"

    # Add LIMIT/OFFSET
    if limit > 0:
        query += f" LIMIT ${param_num}"
        params.append(limit)
        param_num += 1

    if skip > 0:
        query += f" OFFSET ${param_num}"
        params.append(skip)
        param_num += 1

    rows = await db_manager.fetch(query, *params)
    return [convert_row_to_camel(dict(row), table) for row in rows]


async def pg_count(table: str, filter_dict: dict = None) -> int:
    """Count records - MongoDB compatible"""
    filter_dict = filter_dict or {}
    where_clause, params, _ = PGQueryBuilder.build_filter_clause(filter_dict, table)
    query = f"SELECT COUNT(*) FROM {table} WHERE {where_clause}"
    return await db_manager.fetchval(query, *params)


async def pg_update_one(table: str, filter_dict: dict, update_dict: dict) -> int:
    """Update one record - MongoDB compatible"""
    set_dict = update_dict.get("$set", {})
    unset_dict = update_dict.get("$unset", {})

    set_clauses = []
    params = []
    param_num = 1

    # Handle $set
    for key, value in set_dict.items():
        field = PGQueryBuilder.camel_to_snake(key)
        set_clauses.append(f"{field} = ${param_num}")
        params.append(value)
        param_num += 1

    # Handle $unset (set to NULL)
    for key in unset_dict.keys():
        field = PGQueryBuilder.camel_to_snake(key)
        set_clauses.append(f"{field} = NULL")

    if not set_clauses:
        return 0

    # Build WHERE clause
    where_clause, where_params, _ = PGQueryBuilder.build_filter_clause(filter_dict, table, param_num)
    params.extend(where_params)

    query = f"UPDATE {table} SET {', '.join(set_clauses)} WHERE {where_clause}"
    result = await db_manager.execute(query, *params)

    # Parse result like "UPDATE 1"
    return int(result.split()[-1]) if result else 0


async def pg_update_many(table: str, filter_dict: dict, update_dict: dict) -> int:
    """Update multiple records - same as update_one for PostgreSQL"""
    return await pg_update_one(table, filter_dict, update_dict)


async def pg_delete_one(table: str, filter_dict: dict) -> int:
    """Delete one record - MongoDB compatible"""
    where_clause, params, _ = PGQueryBuilder.build_filter_clause(filter_dict, table)
    query = f"DELETE FROM {table} WHERE {where_clause}"
    result = await db_manager.execute(query, *params)
    return int(result.split()[-1]) if result else 0


async def pg_delete_many(table: str, filter_dict: dict) -> int:
    """Delete multiple records - MongoDB compatible"""
    return await pg_delete_one(table, filter_dict)


async def pg_insert_one(table: str, document: dict) -> Any:
    """Insert one record - MongoDB compatible"""
    # Convert keys to snake_case
    doc_snake = PGQueryBuilder.dict_to_snake_case(document)

    columns = list(doc_snake.keys())
    placeholders = [f"${i+1}" for i in range(len(columns))]
    values = [doc_snake[col] for col in columns]

    # Handle different primary key names
    pk_map = {
        "refresh_tokens": "jti",
        "jobs": "job_key",
    }
    pk_col = pk_map.get(table, "id")

    query = f"""
        INSERT INTO {table} ({', '.join(columns)})
        VALUES ({', '.join(placeholders)})
        RETURNING {pk_col}
    """

    return await db_manager.fetchval(query, *values)


# Compatibility wrapper classes
class PGCollection:
    """PostgreSQL collection with MongoDB-like interface"""

    def __init__(self, table_name: str):
        self.table_name = table_name

    async def find_one(self, filter_dict: dict = None, projection: dict = None) -> Optional[dict]:
        """Find one document"""
        filter_dict = filter_dict or {}
        if projection:
            # For now, ignore projection (would need schema info)
            pass
        return await pg_find_one(self.table_name, filter_dict)

    def find(self, filter_dict: dict = None, projection: dict = None):
        """Find multiple documents - returns cursor"""
        return PGCursor(self.table_name, filter_dict or {}, projection)

    async def count_documents(self, filter_dict: dict = None) -> int:
        """Count documents"""
        return await pg_count(self.table_name, filter_dict or {})

    async def update_one(self, filter_dict: dict, update_dict: dict, upsert: bool = False):
        """Update one document"""
        count = await pg_update_one(self.table_name, filter_dict, update_dict)

        if count == 0 and upsert:
            # Implement upsert logic
            set_dict = update_dict.get("$set", {})
            set_on_insert = update_dict.get("$setOnInsert", {})
            insert_doc = {**filter_dict, **set_dict, **set_on_insert}
            await pg_insert_one(self.table_name, insert_doc)

        return type('UpdateResult', (), {'matched_count': count, 'modified_count': count})()

    async def update_many(self, filter_dict: dict, update_dict: dict):
        """Update multiple documents"""
        count = await pg_update_many(self.table_name, filter_dict, update_dict)
        return type('UpdateResult', (), {'matched_count': count, 'modified_count': count})()

    async def delete_one(self, filter_dict: dict):
        """Delete one document"""
        count = await pg_delete_one(self.table_name, filter_dict)
        return type('DeleteResult', (), {'deleted_count': count})()

    async def delete_many(self, filter_dict: dict):
        """Delete multiple documents"""
        count = await pg_delete_many(self.table_name, filter_dict)
        return type('DeleteResult', (), {'deleted_count': count})()

    async def insert_one(self, document: dict):
        """Insert one document"""
        inserted_id = await pg_insert_one(self.table_name, document)
        return type('InsertResult', (), {'inserted_id': inserted_id})()

    def aggregate(self, pipeline: List[dict]):
        """Aggregation pipeline - returns cursor"""
        # For now, raise NotImplementedError for complex aggregations
        # They need to be converted to SQL JOINs manually
        raise NotImplementedError("Aggregation pipelines must be converted to SQL manually")


class PGCursor:
    """PostgreSQL cursor with MongoDB-like interface"""

    def __init__(self, table_name: str, filter_dict: dict, projection: dict = None):
        self.table_name = table_name
        self.filter_dict = filter_dict
        self.projection = projection
        self._sort = None
        self._skip = 0
        self._limit = 0

    def sort(self, field: str, direction: int = 1):
        """Add sorting"""
        self._sort = [(field, direction)]
        return self

    def skip(self, count: int):
        """Skip documents"""
        self._skip = count
        return self

    def limit(self, count: int):
        """Limit results"""
        self._limit = count
        return self

    async def to_list(self, length: int = None):
        """Fetch all results"""
        limit = length if length is not None else self._limit
        results = await pg_find(
            self.table_name,
            self.filter_dict,
            self.projection,
            self._sort,
            self._skip,
            limit
        )
        return results


# Create a database object with collection properties
class PostgreSQLDatabase:
    """PostgreSQL database with MongoDB-like collection interface"""

    def __init__(self):
        self.books = PGCollection("books")
        self.pages = PGCollection("pages")
        self.chunks = PGCollection("chunks")
        self.users = PGCollection("users")
        self.refresh_tokens = PGCollection("refresh_tokens")
        self.jobs = PGCollection("jobs")
        self.proverbs = PGCollection("proverbs")  # If you have this table
        self.rag_evaluations = PGCollection("rag_evaluations")


# Global database instance
pg_db = PostgreSQLDatabase()


# FastAPI dependency for getting database
async def get_pg_db():
    """Get PostgreSQL database instance - FastAPI dependency"""
    return pg_db
