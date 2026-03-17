from __future__ import annotations

import asyncio
import hashlib
import uuid
import os
import io
import re
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy import text, and_, or_, case, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
import random
from app.core.config import settings
from app.db.session import get_session
from app.db.repositories.books import BooksRepository
from app.db.repositories.pages import PagesRepository
from app.db.repositories.system_configs import SystemConfigsRepository
from app.db.models import Book as BookDB, Page, Chunk, BookSummary
from app.models.schemas import Book, PaginatedBooks, ExtractionResult
from app.models.user import User
from app.services.storage_service import storage
from app.services.chunking_service import chunking_service
from app.utils.markdown import normalize_markdown, strip_markdown
from app.langchain.models import GeminiEmbeddings
from auth.dependencies import (
    get_current_user_optional,
    require_admin,
    require_editor,
    require_reader,
)
import logging
from app.utils.text import generate_uyghur_regex, normalize_uyghur_chars
from app.core.i18n import t
from app.services.pdf_service import read_pdf_page_count, extract_pdf_cover, create_page_stubs
from app.services.docx_service import extract_docx_pages, extract_docx_cover
from app.services.cache_service import cache_service
from app.core import cache_config
import json


logger = logging.getLogger(__name__)


def camel_to_snake(name: str) -> str:
    """Convert camelCase to snake_case"""
    # Insert underscore before uppercase letters and convert to lowercase
    name = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', name).lower()


def convert_dict_keys_to_snake(d: dict) -> dict:
    """Recursively convert all dict keys from camelCase to snake_case"""
    result = {}
    for key, value in d.items():
        snake_key = camel_to_snake(key)
        if isinstance(value, dict):
            result[snake_key] = convert_dict_keys_to_snake(value)
        elif isinstance(value, list):
            result[snake_key] = [
                convert_dict_keys_to_snake(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[snake_key] = value
    return result

def _normalize_categories(categories: Optional[List[str]]) -> List[str]:
    """Strip quotes and whitespace from category strings."""
    if not categories:
        return []
    return [
        c.strip().strip('"').strip() 
        for c in categories 
        if isinstance(c, str) and c.strip()
    ]


router = APIRouter()


async def _increment_read_count(book_id: str) -> None:
    """Background task: atomically increment read_count with its own DB session."""
    from app.db.session import async_session_factory
    from app.db.models import Book as BookDB
    if async_session_factory is None:
        return
    async with async_session_factory() as session:
        await session.execute(
            update(BookDB)
            .where(BookDB.id == book_id)
            .values(read_count=BookDB.read_count + 1)
        )
        await session.commit()


async def check_book_access_for_guest(book: dict, user: Optional[User]) -> bool:
    """
    Check if a guest (unauthenticated user) can access a book.
    
    Guests can only access books that are:
    1. status = 'ready' AND
    2. visibility = 'public' (defaults to 'public' for legacy books without visibility field)
    
    Args:
        book: The book document from the database.
        user: The current user (None for guests).
        
    Returns:
        True if access is allowed, False otherwise.
    """
    # Authenticated users can access all books
    if user is not None:
        return True
    
    # Guests: check status and visibility
    status = book.get("status")
    visibility = book.get("visibility", "public")  # Default to public for legacy books
    
    return status == "ready" and visibility == "public"




@router.get("/", response_model=PaginatedBooks)
async def get_books(
    page: int = 1,
    pageSize: int = 10,
    q: Optional[str] = None,
    category: Optional[str] = None,
    sortBy: str = "title",
    order: int = 1,
    groupByWork: bool = False,
    includeStats: bool = False,
    current_user: Optional[User] = Depends(get_current_user_optional),
    session: AsyncSession = Depends(get_session),
):
    """Get paginated books list with SQLAlchemy"""
    from sqlalchemy import or_, and_, any_
    from app.db.models import Book as BookDB
    from app.db.models import Page as PageDB
    from app.models.schemas import Book as BookSchema

    # Cap pageSize to prevent extreme batch operations and connection pool exhaustion
    pageSize = min(max(1, pageSize), 50)
    
    skip = (page - 1) * pageSize
    repo = BooksRepository(session)
    # --- PART 0: Cache Lookup ---
    # Dual-track caching: Separate metadata cache from real-time stats
    # When includeStats=true (admin page), we need fresh stats but can cache book metadata
    cache_params_base = {
        "page": page,
        "pageSize": pageSize,
        "q": q,
        "category": category,
        "sortBy": sortBy,
        "order": order,
        "groupByWork": groupByWork,
        "user_role": current_user.role if current_user else "guest"
    }

    # Create separate cache keys for requests with/without stats
    # This allows caching metadata while keeping stats fresh
    cache_params_with_stats = {**cache_params_base, "includeStats": True}
    cache_params_no_stats = {**cache_params_base, "includeStats": False}

    param_hash = hashlib.md5(json.dumps(cache_params_with_stats if includeStats else cache_params_no_stats, sort_keys=True).encode()).hexdigest()
    cache_key = cache_config.KEY_BOOKS_LIST.format(hash=param_hash)

    skip_cache = (
        settings.cache_skip_for_admins and
        current_user and
        current_user.role == "admin"
    )

    # For admin page with stats, try to load cached metadata (without stats)
    # Then append fresh stats afterwards to avoid stale pipeline progress
    cached_metadata = None
    if not skip_cache and includeStats and current_user and current_user.role in ['admin', 'editor']:
        # Try loading from metadata-only cache (excludeStats version)
        metadata_hash = hashlib.md5(json.dumps(cache_params_no_stats, sort_keys=True).encode()).hexdigest()
        metadata_cache_key = cache_config.KEY_BOOKS_LIST.format(hash=metadata_hash)
        cached_metadata = await cache_service.get(metadata_cache_key)

    if not skip_cache and not includeStats:
        # For non-stats requests, use normal caching
        cached_result = await cache_service.get(cache_key)
        if cached_result:
            return PaginatedBooks.model_validate(cached_result)


    # If we have cached metadata for admin stats request, use it and only fetch fresh stats
    if cached_metadata and includeStats:
        # Reuse cached book list, counts, etc.
        cached_books = [Book.model_validate(b) for b in cached_metadata.get("books", [])]

        # Fetch ONLY fresh stats for the cached books
        if cached_books:
            book_ids = [str(b.id) for b in cached_books]
            batch_stats = await repo.get_batch_stats(book_ids)
            for book in cached_books:
                stats = batch_stats.get(str(book.id), {})
                book.pipeline_stats = stats.get("pipeline_stats", {})
                book.has_summary = stats.get("has_summary", False)

        # Return immediately with cached metadata + fresh stats
        return PaginatedBooks.model_validate({
            "books": cached_books,
            "total": cached_metadata.get("total", 0),
            "total_ready": cached_metadata.get("total_ready", 0),
            "page": page,
            "page_size": pageSize,
        })

    # --- PART 1: Define Filters ---
    # conditions: for the main list (total)
    # ready_conditions: for the 'ready' list (total_ready) - only relevant for admins/editors
    conditions = []
    if current_user is None:
        conditions.append(BookDB.status == "ready")
        conditions.append(or_(BookDB.visibility == "public", BookDB.visibility is None))
    
    if category:
        conditions.append(category == any_(BookDB.categories))

    if q:
        q_alt = q.replace('\u0626', '\u064A\u0654') if '\u0626' in q else (q.replace('\u064A\u0654', '\u0626') if '\u064A\u0654' in q else q)
        search_filter = or_(
            BookDB.title.ilike(f"%{q}%"),
            BookDB.author.ilike(f"%{q}%"),
            BookDB.title.ilike(f"%{q_alt}%"),
            BookDB.author.ilike(f"%{q_alt}%"),
            q == any_(BookDB.categories),
            q_alt == any_(BookDB.categories)
        )
        conditions.append(search_filter)

    # --- PART 2: Optimized Counting ---
    # Merge total and total_ready counts into a single query for better performance
    can_see_all = current_user and current_user.role in ['admin', 'editor']
    
    if groupByWork:
        # Count unique works (title, author)
        count_stmt = select(
            func.count().label("total"),
            func.count(case((
                and_(
                    BookDB.status == "ready", 
                    or_(BookDB.visibility == "public", BookDB.visibility == None)
                ), 1
            ))).label("total_ready")
        ).select_from(
            select(BookDB.title, BookDB.author, BookDB.status, BookDB.visibility)
            .where(and_(*conditions))
            .distinct()
            .subquery()
        )
    else:
        # Standard flat count
        count_stmt = select(
            func.count(BookDB.id).label("total"),
            func.count(case((
                and_(
                    BookDB.status == "ready", 
                    or_(BookDB.visibility == "public", BookDB.visibility == None)
                ), 1
            ))).label("total_ready")
        ).where(and_(*conditions))
    
    count_res = await session.execute(count_stmt)
    row = count_res.fetchone()
    total = row.total if row else 0
    total_ready = row.total_ready if row else 0
    
    if not can_see_all:
        total_ready = total

    # --- PART 3: Main Data Fetching ---
    if groupByWork:
        # Optimized grouping: Pick the LATEST volume per (title, author)
        # and attach the series arrival date for sorting.
        from sqlalchemy.orm import aliased
        
        inner_stmt = (
            select(
                BookDB,
                func.max(BookDB.upload_date).over(partition_by=[BookDB.title, BookDB.author]).label("series_latest")
            )
            .where(and_(*conditions))
            .distinct(BookDB.title, BookDB.author) # Truly group works
            .order_by(BookDB.title, BookDB.author, BookDB.upload_date.desc())
        ).subquery()
        
        book_alias = aliased(BookDB, inner_stmt)
        main_stmt = select(book_alias)
        
        if order == -1:
            main_stmt = main_stmt.order_by(inner_stmt.c.series_latest.desc(), inner_stmt.c.title.asc())
        else:
            main_stmt = main_stmt.order_by(inner_stmt.c.series_latest.asc(), inner_stmt.c.title.asc())
        
        main_stmt = main_stmt.offset(skip).limit(pageSize)
        result = await session.execute(main_stmt)
        books_objs = result.scalars().all()
    else:
        # Standard flat list fetch
        stmt = select(BookDB).where(and_(*conditions))
        
        if sortBy == "uploadDate":
            series_latest = func.max(BookDB.upload_date).over(partition_by=[BookDB.title, BookDB.author])
            if order == -1:
                stmt = stmt.order_by(series_latest.desc(), BookDB.title.asc(), BookDB.volume.asc().nulls_first())
            else:
                stmt = stmt.order_by(series_latest.asc(), BookDB.title.asc(), BookDB.volume.asc().nulls_first())
        else:
            sort_map = {"title": BookDB.title, "author": BookDB.author, "lastUpdated": BookDB.last_updated}
            sort_col = sort_map.get(sortBy, BookDB.upload_date)
            stmt = stmt.order_by(sort_col.desc() if order == -1 else sort_col.asc())

        stmt = stmt.offset(skip).limit(pageSize)
        result = await session.execute(stmt)
        books_objs = result.scalars().all()

    # --- PART 4: Asset Serialization (Optimized for List View) ---
    books_data = []

    # Only include expensive pipeline stats when explicitly requested via includeStats=true
    # This is needed only on the admin book management page, not on library/home views
    # Huge performance gain: Avoids expensive JOIN + GROUP BY on pages table for every book
    should_include_stats = (
        includeStats and
        current_user and
        current_user.role in ['admin', 'editor']
    )

    for b in books_objs:
        last_error_obj = None
        if b.last_error:
            if isinstance(b.last_error, str):
                try: last_error_obj = json.loads(b.last_error)
                except Exception: last_error_obj = None
            else: last_error_obj = b.last_error

        b_dict = {
            "id": b.id, "content_hash": b.content_hash, "title": b.title, "author": b.author or "",
            "volume": b.volume, "total_pages": b.total_pages or 0, "pages": [], "status": b.status,
            "pipeline_step": b.pipeline_step, "upload_date": b.upload_date, "last_updated": b.last_updated,
            "updated_by": b.updated_by, "created_by": b.created_by,
            "cover_url": f"{storage.get_public_url(b.cover_url)}?v={int(b.last_updated.timestamp())}" if b.cover_url and b.last_updated else (storage.get_public_url(b.cover_url) if b.cover_url else None),
            "visibility": b.visibility, "categories": _normalize_categories(b.categories),
            "last_error": last_error_obj, "read_count": b.read_count or 0, "file_name": b.file_name,
            "file_type": b.file_type, "source": b.source, "pipeline_stats": {}, "has_summary": False,
            # Book-level milestones for accurate icon colors
            "ocr_milestone": b.ocr_milestone,
            "chunking_milestone": b.chunking_milestone,
            "embedding_milestone": b.embedding_milestone,
            "spell_check_milestone": b.spell_check_milestone
        }
        books_data.append(BookSchema.model_validate(b_dict))

    # Batch-fetch summary status for all books in the list (very cheap)
    summary_ids = set()
    if books_data:
        bid_list = [str(b.id) for b in books_objs]
        s_stmt = select(BookSummary.book_id).where(BookSummary.book_id.in_(bid_list))
        s_res = await session.execute(s_stmt)
        summary_ids = {str(row[0]) for row in s_res.fetchall()}
        for pydantic_book in books_data:
            if str(pydantic_book.id) in summary_ids:
                pydantic_book.has_summary = True

    # Only fetch expensive pipeline stats if explicitly requested (non-lite)
    if should_include_stats and books_data:
        book_ids = [str(b.id) for b in books_data]
        batch_stats = await repo.get_batch_stats(book_ids)
        for pydantic_book in books_data:
            stats = batch_stats.get(str(pydantic_book.id), {})
            pydantic_book.pipeline_stats = stats.get("pipeline_stats", {})
            # has_summary is already set above, but stats might have a more recent view
            if stats.get("has_summary"):
                pydantic_book.has_summary = True

    result = {
        "books": books_data,
        "total": total,
        "total_ready": total_ready,
        "page": page,
        "page_size": pageSize,
    }

    if not skip_cache:
        # Dual-track caching strategy:
        # 1. Always cache the full result (with or without stats) for normal requests
        # 2. For admin stats requests, ALSO cache a metadata-only version (no stats)
        #    This allows future requests to reuse book list + counts and only fetch fresh stats

        cache_ttl = 1800 if current_user is None else 600

        if includeStats and current_user and current_user.role in ['admin', 'editor']:
            # Create metadata-only version (strip out stats)
            metadata_result = {
                "books": [
                    {**book.model_dump(), "pipeline_stats": {}, "has_summary": False}
                    for book in books_data
                ],
                "total": total,
                "total_ready": total_ready,
                "page": page,
                "page_size": pageSize,
            }

            # Cache metadata version (longer TTL since metadata is stable)
            metadata_hash = hashlib.md5(json.dumps(cache_params_no_stats, sort_keys=True).encode()).hexdigest()
            metadata_cache_key = cache_config.KEY_BOOKS_LIST.format(hash=metadata_hash)
            await cache_service.set(metadata_cache_key, metadata_result, ttl=cache_ttl * 2)  # 20 min for metadata

            # Note: We do NOT cache the full stats result to ensure stats are always fresh
        else:
            # For non-stats requests, cache normally
            await cache_service.set(cache_key, result, ttl=cache_ttl)

    return result




@router.get("/random-proverb")
async def get_random_proverb(
    response: Response,
    keyword: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    """Fetch a random proverb with SQLAlchemy"""
    from app.db.repositories.proverbs import ProverbsRepository

    proverbs_repo = ProverbsRepository(session)

    # Disable browser caching for proverbs to ensure fresh selection from server
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"

    # Cache Lookup for the LIST of proverbs for this keyword
    keyword_hash = hashlib.md5((keyword or "default").encode()).hexdigest()[:8]
    list_cache_key = f"proverbs:list:{keyword_hash}"
    
    proverbs_list = await cache_service.get(list_cache_key)
    
    if proverbs_list is None:
        if keyword:
            keywords = [k.strip() for k in keyword.split(",") if k.strip()]
            patterns = [generate_uyghur_regex(k) for k in keywords]
        else:
            keywords = ["كىتاب", "بىلىم", "ئەقىل", "پاراسەت"]
            patterns = [generate_uyghur_regex(k) for k in keywords]

        if patterns:
            combined_pattern = "(" + "|".join(patterns) + ")"
        else:
            combined_pattern = ".*"

        # Fetch matching proverbs (list)
        results = await proverbs_repo.find_by_text_pattern(combined_pattern)
        
        if results:
            proverbs_list = [
                {"text": p.text, "volume": p.volume, "pageNumber": p.page_number}
                for p in results
            ]
        else:
            proverbs_list = [{
                "text": "كىتاب — بىلىم بۇلىقى.",
                "volume": 1,
                "pageNumber": 1
            }]
            
        # Cache the list (longer TTL as proverbs change infrequently)
        await cache_service.set(list_cache_key, proverbs_list, ttl=settings.cache_ttl_proverbs)

    # Randomly select one from the cached list (Dynamic on every refresh)
    return random.choice(proverbs_list)



@router.get("/top-categories")
async def get_top_categories(
    response: Response,
    limit: int = 100,
    sort: str = "count",  # "count" or "alphabetical"
    current_user: Optional[User] = Depends(get_current_user_optional),
    session: AsyncSession = Depends(get_session),
):
    """Get categories with optional sorting and limit"""
    # Add HTTP cache headers for browser caching (15 minutes = 900 seconds)
    # Set this early so it applies to both cached and fresh responses
    # public = cacheable by browsers and CDNs (categories change infrequently)
    # max-age = browser caches for 15 minutes
    # stale-while-revalidate = browser can use stale cache for 120s while fetching new data in background
    response.headers["Cache-Control"] = f"public, max-age={settings.cache_ttl_categories}, stale-while-revalidate=120"

    # Cache Lookup
    cache_params = {
        "limit": limit,
        "sort": sort,
        "is_guest": current_user is None
    }
    param_hash = hashlib.md5(json.dumps(cache_params, sort_keys=True).encode()).hexdigest()[:8]
    cache_key = cache_config.KEY_CATEGORY.format(type="top", params=param_hash)

    cached_result = await cache_service.get(cache_key)
    if cached_result:
        return cached_result

    where_conditions = []
    params = {"limit": limit}

    if current_user is None:
        # Guests can only see public ready books
        where_conditions.append("status = 'ready'")
        where_conditions.append("(visibility = 'public' OR visibility IS NULL)")

    where_clause = " AND ".join(where_conditions) if where_conditions else "TRUE"

    order_by = "count DESC"
    if sort == "alphabetical":
        order_by = "category ASC"

    # SQL to unnest categories and count while stripping quotes and whitespace
    sql = text(f"""
        SELECT TRIM(BOTH ' "' FROM category) as clean_category, COUNT(*) as count
        FROM books,
        UNNEST(categories) AS category
        WHERE {where_clause}
        GROUP BY clean_category
        ORDER BY {order_by.replace('category', 'clean_category')}
        LIMIT :limit
    """)

    result = await session.execute(sql, params)
    rows = result.fetchall()
    categories = [row.clean_category for row in rows]
    
    result = {"categories": categories}

    # Store in cache
    await cache_service.set(cache_key, result, ttl=settings.cache_ttl_categories)

    return result



@router.get("/suggest")
async def suggest_books(
    q: str = "",
    current_user: Optional[User] = Depends(get_current_user_optional),
    session: AsyncSession = Depends(get_session),
):
    """Provide autocomplete suggestions with SQLAlchemy"""
    from sqlalchemy import or_, and_
    from app.db.models import Book

    if not q or len(q) < 2:
        return {"suggestions": []}

    # Cache Lookup
    # Limit to first 10 chars to increase hit rate, hash to prevent key injection 
    q_prefix = hashlib.md5(q[:10].encode()).hexdigest()[:8]
    user_role = current_user.role if current_user else "guest"
    cache_key = f"suggestions:{q_prefix}:{user_role}"

    cached_result = await cache_service.get(cache_key)
    if cached_result:
        return cached_result

    # Build base query for guest access

    conditions = []
    if current_user is None:
        # Guests can only see public ready books
        conditions.extend([
            Book.status == "ready",
            or_(
                Book.visibility == "public",
                Book.visibility.is_(None)  # Legacy books default to public
            )
        ])

    # Define search filter using ILIKE for case-insensitive search
    normalized_q = generate_uyghur_regex(q)

    search_conditions = or_(
        Book.title.op("~*")(normalized_q),  # PostgreSQL regex, case-insensitive
        Book.author.op("~*")(normalized_q),
        # For array search, we need to use raw SQL or array_to_string
        func.array_to_string(Book.categories, ',').op("~*")(normalized_q)
    )
    conditions.append(search_conditions)

    # Build final query
    stmt = select(Book.title, Book.author, Book.categories)
    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.limit(10)

    result = await session.execute(stmt)
    books = result.fetchall()

    suggestions = []
    seen = set()

    # Use regex for matching because Uyghur characters have multiple encodings
    search_re = re.compile(normalized_q, re.IGNORECASE)

    for row in books:
        title, author, categories = row

        if title and search_re.search(title) and title not in seen:
            suggestions.append({"text": title, "type": "title"})
            seen.add(title)

        if author and search_re.search(author) and author not in seen:
            suggestions.append({"text": author, "type": "author"})
            seen.add(author)

        normalized_cats = _normalize_categories(categories)
        for cat in normalized_cats:
            if cat and search_re.search(cat) and cat not in seen:
                suggestions.append({"text": cat, "type": "category"})
                seen.add(cat)

    # Sort suggestions: titles first, then authors, then categories
    type_priority = {"title": 0, "author": 1, "category": 2}
    suggestions.sort(key=lambda x: type_priority.get(x["type"], 3))

    result = {"suggestions": suggestions[:10]}
    # Cache for 30 seconds (autocomplete changes fast)
    await cache_service.set(cache_key, result, ttl=30)

    return result



@router.get("/{book_id}", response_model=Book)
async def get_book(
    book_id: str,
    background_tasks: BackgroundTasks,
    current_user: Optional[User] = Depends(get_current_user_optional),
    session: AsyncSession = Depends(get_session),
):
    """Get a single book by ID with SQLAlchemy - returns metadata only, no pages"""
    from app.db.models import Page as PageDB
    repo = BooksRepository(session)

    # --- PART 0: Cache Lookup ---
    skip_cache = (
        settings.cache_skip_for_admins and 
        current_user and 
        current_user.role == "admin"
    )

    if not skip_cache:
        cache_key = cache_config.KEY_BOOK.format(book_id=book_id)
        cached_book = await cache_service.get(cache_key)
        if cached_book:
            # Increment read counter asynchronously even on cache hit
            background_tasks.add_task(_increment_read_count, book_id)
            return Book.model_validate(cached_book)

    # Get book from SQLAlchemy with stats
    stats = await repo.get_with_page_stats(book_id)

    if not stats:
        raise HTTPException(status_code=404, detail=t("errors.book_not_found"))
    
    book_model = stats["book"]

    # Convert to dict for access check (legacy function expects dict)
    book_dict = {
        "id": str(book_model.id),
        "status": book_model.status,
        "visibility": book_model.visibility,
    }

    # Check guest access
    if not await check_book_access_for_guest(book_dict, current_user):
        raise HTTPException(status_code=403, detail=t("errors.unauthorized_access"))

    # Increment read counter asynchronously (non-blocking)
    background_tasks.add_task(_increment_read_count, book_id)

    # No longer fetch pages here - frontend fetches them via /pages endpoint
    # This saves a wasteful DB query for up to 10,000 rows we were discarding

    # Parse last_error from JSON string if needed
    last_error_obj = None
    if book_model.last_error:
        if isinstance(book_model.last_error, str):
            try:
                last_error_obj = json.loads(book_model.last_error)
            except Exception:
                last_error_obj = None
        else:
            last_error_obj = book_model.last_error

    # Reuse previously fetched stats for the book metadata
    pipeline_stats = stats.get("pipeline_stats", {})
    has_summary = stats.get("has_summary", False)

    # Create a dict with only metadata
    book_dict = {
        "id": book_model.id,
        "content_hash": book_model.content_hash,
        "title": book_model.title,
        "author": book_model.author or "",
        "volume": book_model.volume,
        "total_pages": book_model.total_pages or 0,
        "pages": [],  # Empty list as we don't load pages here anymore
        "status": book_model.status,
        "pipeline_step": book_model.pipeline_step,
        "upload_date": book_model.upload_date,
        "last_updated": book_model.last_updated,
        "updated_by": book_model.updated_by,
        "created_by": book_model.created_by,
        "cover_url": f"{storage.get_public_url(book_model.cover_url)}?v={int(book_model.last_updated.timestamp())}" if book_model.cover_url and book_model.last_updated else (storage.get_public_url(book_model.cover_url) if book_model.cover_url else None),
        "visibility": book_model.visibility,
        "categories": _normalize_categories(book_model.categories),
        "last_error": last_error_obj,
        "read_count": book_model.read_count or 0,
        "file_name": book_model.file_name,
        "file_type": book_model.file_type,
        "source": book_model.source,
        "pipeline_stats": pipeline_stats,
        "has_summary": has_summary
    }

    # Convert SQLAlchemy models to Pydantic (automatic camelCase conversion)
    book_response = Book.model_validate(book_dict)

    # We intentionally return empty pages here. The frontend should fetch content 
    # via the /content endpoint or paginated API.
    book_response.pages = []

    # Cache only if status is 'ready'
    if book_model.status == "ready" and not skip_cache:
        await cache_service.set(
            cache_config.KEY_BOOK.format(book_id=book_id), 
            book_dict, 
            ttl=settings.cache_ttl_books
        )

    return book_response


@router.get("/{book_id}/pipeline-stats")
async def get_book_pipeline_stats(
    book_id: str,
    step: Optional[str] = None,  # Optional: ocr, chunking, embedding, spell_check, summary
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Fetch detailed page-level pipeline statistics for a single book (for UI hover)

    If step is provided, only fetches stats for that specific pipeline step for performance.
    """
    repo = BooksRepository(session)
    # Using existing repo method that returns {book, page_stats, pipeline_stats, has_summary}
    stats = await repo.get_with_page_stats(book_id, step=step)
    if not stats:
        raise HTTPException(status_code=404, detail="Book not found")

    return {
        "pipeline_stats": stats.get("pipeline_stats", {}),
        "has_summary": stats.get("has_summary", False),
        "total_pages": stats["book"].total_pages
    }



@router.get("/stats")
async def get_book_stats(
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Get book statistics for admin dashboard"""
    repo = BooksRepository(session)
    
    # Count by status
    pending = await repo.count_by_status("pending")
    processing = await repo.count_by_status("ocr_processing")
    completed = await repo.count_by_status("ready")
    error = await repo.count_by_status("error")
    
    # Count total
    total = pending + processing + completed + error
    
    return {
      "total": total,
      "pending": pending,
      "processing": processing,
      "completed": completed,
      "error": error
    }


@router.get("/{book_id}/content")
async def get_book_content(
    book_id: str,
    current_user: User = Depends(require_reader),
    session: AsyncSession = Depends(get_session),
):
    """Get full book content with SQLAlchemy"""
    books_repo = BooksRepository(session)
    pages_repo = PagesRepository(session)

    # Verify book exists
    book_model = await books_repo.get(book_id)
    if not book_model:
        raise HTTPException(status_code=404, detail=t("errors.book_not_found"))

    # Get all pages using repository
    pages = await pages_repo.find_by_book(book_id, limit=10000)
    logger.info(f"DEBUG: Found {len(pages)} pages for book {book_id}")

    content_blocks = []
    for p in pages:
        content_blocks.append(f"[[PAGE {p.page_number}]]\n{p.text or ''}")

    full_text = "\n\n".join(content_blocks)
    logger.info(f"DEBUG: Returning full content for book {book_id}, length={len(full_text)}")

    return {"content": full_text.strip()}


@router.get("/{book_id}/pages/{page_num}", response_model=ExtractionResult)
async def get_book_page(
    book_id: str,
    page_num: int,
    current_user: Optional[User] = Depends(get_current_user_optional),
    session: AsyncSession = Depends(get_session),
):
    """Get a specific book page by page number with SQLAlchemy"""
    books_repo = BooksRepository(session)
    pages_repo = PagesRepository(session)

    # Verify book exists and check access
    book_model = await books_repo.get(book_id)
    if not book_model:
        raise HTTPException(status_code=404, detail=t("errors.book_not_found"))

    # Convert to dict for access check
    book_dict = {
        "id": str(book_model.id),
        "status": book_model.status,
        "visibility": book_model.visibility,
    }

    if not await check_book_access_for_guest(book_dict, current_user):
        raise HTTPException(status_code=403, detail=t("errors.unauthorized_access"))

    # Get page by number
    page = await pages_repo.find_one(book_id, page_num)
    if not page:
        raise HTTPException(status_code=404, detail=t("errors.page_not_found"))

    # Convert to Pydantic with automatic camelCase
    return ExtractionResult.model_validate(page)


@router.get("/{book_id}/pages", response_model=List[ExtractionResult])
async def get_book_pages(
    book_id: str,
    skip: int = 0,
    limit: int = 20,
    current_user: Optional[User] = Depends(get_current_user_optional),
    session: AsyncSession = Depends(get_session),
):
    """Get paginated book pages with SQLAlchemy"""
    books_repo = BooksRepository(session)
    pages_repo = PagesRepository(session)

    # Verify book exists and check access
    book_model = await books_repo.get(book_id)
    if not book_model:
        raise HTTPException(status_code=404, detail=t("errors.book_not_found"))

    # Convert to dict for access check
    book_dict = {
        "id": str(book_model.id),
        "status": book_model.status,
        "visibility": book_model.visibility,
    }

    if not await check_book_access_for_guest(book_dict, current_user):
        raise HTTPException(status_code=403, detail=t("errors.unauthorized_access"))

    # Get pages with pagination
    pages = await pages_repo.find_by_book(book_id, skip=skip, limit=limit)

    # Convert to Pydantic with automatic camelCase
    return [ExtractionResult.model_validate(p) for p in pages]



@router.get("/hash/{content_hash}", response_model=Book)
async def get_book_by_hash(
    content_hash: str,
    current_user: Optional[User] = Depends(get_current_user_optional),
    session: AsyncSession = Depends(get_session),
):
    """Get book by content hash with SQLAlchemy"""
    books_repo = BooksRepository(session)

    # Use repository method to find by hash
    book_model = await books_repo.find_by_hash(content_hash)
    if not book_model:
        raise HTTPException(status_code=404, detail=t("errors.book_not_found"))

    # Convert to dict for access check (legacy function expects dict)
    book_dict = {
        "id": str(book_model.id),
        "status": book_model.status,
        "visibility": book_model.visibility,
    }

    # Check guest access
    if not await check_book_access_for_guest(book_dict, current_user):
        raise HTTPException(status_code=403, detail=t("errors.unauthorized_access"))

    # Convert to Pydantic with automatic camelCase
    return Book.model_validate(book_model)


@router.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Upload a PDF or DOCX book file."""
    books_repo = BooksRepository(session)

    fname_lower = file.filename.lower()
    if fname_lower.endswith(".pdf"):
        file_type = "pdf"
    elif fname_lower.endswith(".docx"):
        file_type = "docx"
    else:
        raise HTTPException(status_code=400, detail=t("errors.invalid_file_type", allowed=".pdf, .docx"))

    ext = "." + file_type
    temp_path = settings.uploads_dir / f".upload_{uuid.uuid4().hex}{ext}"
    hasher = hashlib.sha256()

    try:
        with open(temp_path, "wb") as handle:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                hasher.update(chunk)
                handle.write(chunk)

        content_hash = hasher.hexdigest()

        # Check for existing book by hash
        existing = await books_repo.find_by_hash(content_hash)
        if existing:
            temp_path.unlink(missing_ok=True)
            return {"bookId": str(existing.id), "status": "existing"}

        book_id = hashlib.md5(f"{file.filename}{datetime.now(timezone.utc)}".encode()).hexdigest()[:12]
        remote_path = f"uploads/{book_id}{ext}"
        cover_url = None
        cover_temp_path = settings.uploads_dir / f".cover_{book_id}.jpg"

        if file_type == "pdf":
            page_count = read_pdf_page_count(temp_path)
            if extract_pdf_cover(temp_path, cover_temp_path):
                try:
                    remote_cover_path = f"covers/{book_id}.jpg"
                    await storage.upload_file(cover_temp_path, remote_cover_path)
                    cover_url = remote_cover_path
                finally:
                    cover_temp_path.unlink(missing_ok=True)
            await storage.upload_file(temp_path, remote_path)
            temp_path.unlink(missing_ok=True)
        else:
            # DOCX: extract pages immediately, skip OCR
            docx_pages = extract_docx_pages(temp_path)
            page_count = len(docx_pages)
            if extract_docx_cover(temp_path, cover_temp_path):
                try:
                    remote_cover_path = f"covers/{book_id}.jpg"
                    await storage.upload_file(cover_temp_path, remote_cover_path)
                    cover_url = remote_cover_path
                finally:
                    cover_temp_path.unlink(missing_ok=True)
            await storage.upload_file(temp_path, remote_path)
            temp_path.unlink(missing_ok=True)

    except Exception:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise

    now = datetime.now(timezone.utc)
    title_raw = file.filename[: file.filename.lower().rfind(ext)]

    await books_repo.create(
        id=book_id,
        content_hash=content_hash,
        title=normalize_uyghur_chars(title_raw),
        file_name=file.filename,
        file_type=file_type,
        author="",
        volume=None,
        total_pages=page_count,
        cover_url=cover_url,
        status="pending",
        upload_date=now,
        last_updated=now,
        created_by=current_user.email,
        updated_by=current_user.email,
        categories=[],
        visibility="private",
        source="upload",
    )

    if file_type == "pdf":
        create_page_stubs(session, book_id, page_count)
    else:
        # Pre-populate page text; start pipeline at chunking (skip OCR)
        session.add_all([
            Page(
                book_id=book_id,
                page_number=i + 1,
                text=text,
                pipeline_step="chunking",
                milestone="idle",
                status="ocr_done",
            )
            for i, text in enumerate(docx_pages)
        ])

    await session.commit()

    # Invalidate lists
    await cache_service.delete_pattern("books:list:*")
    await cache_service.delete_pattern("category:*")

    return {"bookId": book_id, "status": "uploaded"}



@router.post("/{book_id}/reprocess/ocr")
async def reprocess_ocr(
    book_id: str,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Reprocess OCR by resetting milestones. Text will be overwritten by OCR scanner.

    This is a non-destructive operation that:
    - Resets OCR and downstream milestones to 'idle'
    - Preserves existing text until OCR scanner overwrites it
    - Preserves chunks until chunking scanner processes the new text
    - Allows scanners to handle data updates atomically
    """
    books_repo = BooksRepository(session)
    book = await books_repo.get(book_id)
    if not book:
        raise HTTPException(status_code=404, detail=t("errors.book_not_found"))

    # Reset milestones - scanners will handle data updates
    await session.execute(
        update(Page)
        .where(Page.book_id == book_id)
        .values(
            ocr_milestone="idle",
            chunking_milestone="idle",
            embedding_milestone="idle",
            spell_check_milestone="idle",
            retry_count=0,
            is_indexed=False,
            last_updated=datetime.now(timezone.utc),
            updated_by=current_user.email,
        )
    )

    # Update book-level milestones
    await books_repo.update_one(
        book_id,
        ocr_milestone="idle",
        chunking_milestone="idle",
        embedding_milestone="idle",
        spell_check_milestone="idle",
        status="pending",
        pipeline_step="ocr",
        last_updated=datetime.now(timezone.utc),
        updated_by=current_user.email,
    )
    await session.commit()

    # Invalidate cache - fresh data will be cached after reprocessing
    await cache_service.delete(f"book:{book_id}")
    await cache_service.delete_pattern(f"rag:search:{book_id}:*")
    await cache_service.delete_pattern("rag:summary_search:*")

    return {"status": "ocr_reprocess_started", "message": "OCR milestones reset. Scanner will reprocess pages."}



@router.post("/{book_id}/reprocess/chunking")
async def reprocess_chunking(
    book_id: str,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Reprocess chunking by resetting milestones. Chunks will be recreated by chunking scanner.

    This is a non-destructive operation that:
    - Resets chunking and downstream milestones to 'idle'
    - Preserves OCR text (not re-OCR'd)
    - Preserves chunks until chunking scanner deletes and recreates them atomically
    - Allows chunking scanner to handle chunk updates per-page
    """
    books_repo = BooksRepository(session)
    book = await books_repo.get(book_id)
    if not book:
        raise HTTPException(status_code=404, detail=t("errors.book_not_found"))

    # Reset milestones - chunking scanner will handle chunk recreation
    await session.execute(
        update(Page)
        .where(Page.book_id == book_id)
        .values(
            chunking_milestone="idle",
            embedding_milestone="idle",
            spell_check_milestone="idle",
            retry_count=0,
            is_indexed=False,
            last_updated=datetime.now(timezone.utc),
            updated_by=current_user.email,
        )
    )

    # Update book-level milestones
    await books_repo.update_one(
        book_id,
        chunking_milestone="idle",
        embedding_milestone="idle",
        spell_check_milestone="idle",
        status="pending",
        pipeline_step="chunking",
        last_updated=datetime.now(timezone.utc),
        updated_by=current_user.email,
    )
    await session.commit()

    # Invalidate cache - fresh data will be cached after reprocessing
    await cache_service.delete(f"book:{book_id}")
    await cache_service.delete_pattern(f"rag:search:{book_id}:*")
    await cache_service.delete_pattern("rag:summary_search:*")

    return {"status": "chunking_reprocess_started", "message": "Chunking milestones reset. Scanner will recreate chunks."}



@router.post("/{book_id}/reprocess/embedding")
async def reprocess_embedding(
    book_id: str,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Reprocess embeddings by resetting milestones. Preserves text and chunks.

    This is a non-destructive operation that:
    - Resets embedding and downstream milestones to 'idle'
    - Clears chunk embeddings (vectors) to trigger regeneration
    - Preserves chunk text and all other data
    - Allows embedding scanner to regenerate vectors in place
    """
    books_repo = BooksRepository(session)
    book = await books_repo.get(book_id)
    if not book:
        raise HTTPException(status_code=404, detail=t("errors.book_not_found"))

    # Reset page milestones
    await session.execute(
        update(Page)
        .where(Page.book_id == book_id)
        .values(
            embedding_milestone="idle",
            spell_check_milestone="idle",
            retry_count=0,
            is_indexed=False,
            last_updated=datetime.now(timezone.utc),
            updated_by=current_user.email,
        )
    )

    # Clear embeddings to trigger regeneration (preserves chunk text)
    await session.execute(
        update(Chunk).where(Chunk.book_id == book_id).values(embedding=None)
    )

    # Update book-level milestones
    await books_repo.update_one(
        book_id,
        embedding_milestone="idle",
        spell_check_milestone="idle",
        status="pending",
        pipeline_step="embedding",
        last_updated=datetime.now(timezone.utc),
        updated_by=current_user.email,
    )
    await session.commit()

    # Invalidate RAG cache (vectors will change)
    await cache_service.delete_pattern(f"rag:search:{book_id}:*")
    await cache_service.delete_pattern("rag:summary_search:*")

    return {"status": "embedding_reprocess_started", "message": "Embedding milestones reset. Scanner will regenerate vectors."}





@router.post("/{book_id}/reprocess/spell-check")
async def reprocess_spell_check(
    book_id: str,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Reprocess spell check by resetting milestones. Preserves all existing data.

    This operation:
    - Resets spell-check milestone to 'idle'
    - Preserves all text, chunks, embeddings, and word index
    - Allows spell-check scanner to reprocess pages
    """
    books_repo = BooksRepository(session)
    book = await books_repo.get(book_id)
    if not book:
        raise HTTPException(status_code=404, detail=t("errors.book_not_found"))

    # Reset page milestones
    await session.execute(
        update(Page)
        .where(Page.book_id == book_id)
        .values(
            spell_check_milestone="idle",
            retry_count=0,
            last_updated=datetime.now(timezone.utc),
            updated_by=current_user.email,
        )
    )

    # Update book-level milestone
    await books_repo.update_one(
        book_id,
        spell_check_milestone="idle",
        pipeline_step="spell_check",
        last_updated=datetime.now(timezone.utc),
        updated_by=current_user.email,
    )
    await session.commit()

    return {"status": "spell_check_reprocess_started", "message": "Spell check milestone reset. Scanner will reprocess."}


@router.post("/{book_id}/retry-failed")
async def retry_failed_pages(
    book_id: str,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Smart Retry: Reset failed milestones to 'idle' at their current step."""
    books_repo = BooksRepository(session)
    book = await books_repo.get(book_id)
    if not book:
        raise HTTPException(status_code=404, detail=t("errors.book_not_found"))

    # Reset any milestone that is in 'failed' state back to 'idle'
    # This allows the scanners to pick up where they left off.
    result = await session.execute(
        update(Page)
        .where(
            Page.book_id == book_id,
            or_(
                Page.ocr_milestone.in_(["failed", "error"]),
                Page.chunking_milestone.in_(["failed", "error"]),
                Page.embedding_milestone.in_(["failed", "error"]),
                Page.spell_check_milestone.in_(["failed", "error"]),
            )
        )
        .values(
            ocr_milestone=case(
                (Page.ocr_milestone.in_(["failed", "error"]), text("'idle'")), else_=Page.ocr_milestone
            ),
            chunking_milestone=case(
                (Page.chunking_milestone.in_(["failed", "error"]), text("'idle'")), else_=Page.chunking_milestone
            ),
            embedding_milestone=case(
                (Page.embedding_milestone.in_(["failed", "error"]), text("'idle'")), else_=Page.embedding_milestone
            ),
            spell_check_milestone=case(
                (Page.spell_check_milestone.in_(["failed", "error"]), text("'idle'")), else_=Page.spell_check_milestone
            ),
            retry_count=0, # Reset retries for manual intervention
            last_updated=datetime.now(timezone.utc),
            updated_by=current_user.email,
        )
        .returning(Page.id)
    )
    reset_count = len(result.fetchall())

    if reset_count > 0:
        await books_repo.update_one(
            book_id,
            status="pending",
            last_updated=datetime.now(timezone.utc),
            updated_by=current_user.email,
        )
        await session.commit()
        return {"status": "retry_started", "count": reset_count}

    return {"status": "no_failed_pages", "count": 0}


@router.post("/{book_id}/pages/{page_num}/reset")
async def reset_page(
    book_id: str,
    page_num: int,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Reset a single page to ocr/idle so the v2 OCR scanner re-processes it."""
    books_repo = BooksRepository(session)

    await session.execute(
        text("""
            UPDATE pages
            SET status = 'pending',
                text = NULL,
                is_verified = FALSE,
                is_indexed = FALSE,
                pipeline_step = 'ocr',
                milestone = 'idle',
                retry_count = 0,
                last_updated = NOW(),
                updated_by = :updated_by
            WHERE book_id = :book_id AND page_number = :page_number
        """),
        {"book_id": book_id, "page_number": page_num, "updated_by": current_user.email},
    )

    await books_repo.update_one(
        book_id,
        status="pending",
        last_updated=datetime.now(timezone.utc),
        updated_by=current_user.email,
    )
    await session.commit()
    return {"status": "page_reset_started"}


@router.post("/{book_id}/pages/{page_num}/update")
async def update_page_text(
    book_id: str,
    page_num: int,
    payload: dict,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Update page text with SQLAlchemy and synchronously re-chunk/re-embed (Edge Case #4a)"""
    books_repo = BooksRepository(session)
    pages_repo = PagesRepository(session)
    configs_repo = SystemConfigsRepository(session)

    # Fetch embedding model from system_configs (no fallback — must be configured in DB)
    gemini_embedding_model = await configs_repo.get_value("gemini_embedding_model")
    if not gemini_embedding_model:
        raise HTTPException(status_code=500, detail="system_config 'gemini_embedding_model' is not set")

    new_text = normalize_markdown(payload.get("text", ""))
    new_text = normalize_uyghur_chars(new_text)

    # 1. Update page text and status
    page = await pages_repo.find_one(book_id, page_num)
    if not page:
        raise HTTPException(status_code=404, detail=t("errors.page_not_found"))
    
    # Check if text actually changed
    text_changed = page.text != new_text

    page.text = new_text
    page.status = 'ocr_done'
    page.is_verified = True
    page.is_indexed = (not text_changed) and page.is_indexed
    page.last_updated = datetime.now(timezone.utc)
    page.updated_by = current_user.email
    
    # If text changed, invalidate stale spell check issues (offsets are now invalid)
    if text_changed:
        from app.db.models import PageSpellIssue
        await session.execute(
            delete(PageSpellIssue).where(PageSpellIssue.page_id == page.id)
        )
        page.spell_check_milestone = "idle"
    
    await session.flush()

    # 2. Synchronous Re-chunking (Instant Feedback)
    text_content = strip_markdown(new_text).strip()
    if text_content:
        # Delete old chunks
        await session.execute(
            delete(Chunk).where(and_(Chunk.book_id == book_id, Chunk.page_number == page_num))
        )
        
        # Split into chunks
        chunks_text = [c for c in chunking_service.split_text(text_content) if c.strip()]
        if not chunks_text:
            chunks_text = [text_content]
            
        chunk_records = []
        for idx, txt in enumerate(chunks_text):
            chunk = Chunk(
                book_id=book_id,
                page_number=page_num,
                chunk_index=idx,
                text=txt,
                embedding=None,
                created_at=datetime.now(timezone.utc)
            )
            session.add(chunk)
            chunk_records.append(chunk)
        
        page.status = 'chunked'
        page.pipeline_step = 'chunking'
        page.milestone = 'succeeded'

        await books_repo.update_one(
            book_id,
            last_updated=datetime.now(timezone.utc),
            updated_by=current_user.email
        )
        await session.commit()
        
        # 3. Synchronous Embedding (Instant Feedback) - RELEASED TRANSACTION
        try:
            embedder = GeminiEmbeddings(gemini_embedding_model)
            vectors = await embedder.aembed_documents([c.text for c in chunk_records])
            
            # Start a new transaction for vectors
            for chunk, vector in zip(chunk_records, vectors):
                # We need to re-query or use a fresh statement because old session.commit() might have detached objects
                await session.execute(
                    update(Chunk).where(Chunk.id == chunk.id).values(embedding=vector)
                )
            
            await session.execute(
                update(Page).where(Page.id == page.id).values(
                    status='indexed',
                    is_indexed=True,
                    pipeline_step='embedding',
                    milestone='succeeded'
                )
            )
            await session.commit()
            final_status = 'indexed'
        except Exception as e:
            logger.error(f"Failed to embed page {page_num} for book {book_id} during update: {e}")
            # Page remains 'chunked'; batch cron will embed it on next cycle
            await session.execute(
                update(BookDB).where(BookDB.id == book_id).values(
                    last_error=f"Page {page_num} embedding failed during manual update: {e}",
                    last_updated=datetime.now(timezone.utc)
                )
            )
            await session.commit()
            final_status = 'chunked'
    else:
        # If text is empty, just mark as indexed
        page.status = 'indexed'
        page.is_indexed = True
        page.pipeline_step = 'embedding'
        page.milestone = 'succeeded'
        await books_repo.update_one(
            book_id,
            last_updated=datetime.now(timezone.utc),
            updated_by=current_user.email
        )
        await session.commit()
        final_status = 'indexed'

    # Invalidate book and RAG cache
    await cache_service.delete(f"book:{book_id}")
    await cache_service.delete_pattern(f"rag:search:{book_id}:*")

    return {"status": "page_updated", "requires_rag": True, "synchronous": final_status == 'indexed'}



@router.post("/")
async def create_book(
    book: Book,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Create or upsert book with SQLAlchemy"""
    books_repo = BooksRepository(session)
    pages_repo = PagesRepository(session)

    book_dict = book.model_dump()
    book_id = book_dict.get("id")

    # Remove fields we don't want to store
    book_dict.pop("upload_date", None)
    book_dict.pop("content", None)
    book_dict.pop("pipeline_stats", None)
    book_dict.pop("page_stats", None)
    book_dict.pop("completed_count", None)
    pages_input = book_dict.pop("pages", []) or []

    # Sync pages if they exist
    if pages_input:
        for r in pages_input:
            page_text = normalize_markdown(r.get("text") or "")
            page_text = normalize_uyghur_chars(page_text)
            page_data = {
                "book_id": book_id,
                "page_number": r.get("page_number"),
                "text": page_text,
                "status": r.get("status", "ocr_done"),
                "is_verified": r.get("is_verified", False),
                "updated_by": current_user.email,
            }
            # Use repository upsert method
            await pages_repo.upsert(page_data)

    # Check if book exists
    existing_book = await books_repo.get(book_id)

    if existing_book:
        # Update existing book
        book_dict["updated_by"] = current_user.email
        book_dict["last_updated"] = datetime.now(timezone.utc)
        await books_repo.update_one(book_id, **book_dict)
    else:
        # Create new book
        book_dict["created_by"] = current_user.email
        book_dict["updated_by"] = current_user.email
        book_dict["upload_date"] = datetime.now(timezone.utc)
        book_dict["last_updated"] = datetime.now(timezone.utc)
        await books_repo.create(**book_dict)

    # Set pages with text to chunking/idle so the v2 chunking scanner picks them up
    if pages_input:
        await session.execute(
            update(Page)
            .where(and_(Page.book_id == book_id, Page.text.isnot(None)))
            .values(
                pipeline_step="chunking",
                milestone="idle",
                last_updated=datetime.now(timezone.utc),
                updated_by=current_user.email,
            )
        )

    await session.commit()

    # Invalidate cache
    await cache_service.delete(f"book:{book_id}")
    await cache_service.delete_pattern("books:list:*")
    await cache_service.delete_pattern("category:*")

    return {"status": "success"}



@router.put("/{book_id}")
async def update_book_details(
    book_id: str,
    book_update: dict,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Update book details with SQLAlchemy"""
    books_repo = BooksRepository(session)
    PagesRepository(session)

    # Verify book exists
    book = await books_repo.get(book_id)
    if not book:
        raise HTTPException(status_code=404, detail=t("errors.book_not_found"))

    # Convert all camelCase keys to snake_case
    book_update = convert_dict_keys_to_snake(book_update)

    # Remove fields we don't want to update
    book_update.pop("upload_date", None)
    book_update.pop("content", None)

    if "pages" in book_update:
        for result in book_update.get("pages") or []:
            if "text" in result:
                result["text"] = normalize_markdown(result.get("text") or "")

            # Sync to pages collection
            if "pageNumber" in result or "page_number" in result:
                page_number = result.get("pageNumber") or result.get("page_number")
                new_text = result.get("text")

                # Only update v2 state if text actually changed (kick off re-chunking)
                await session.execute(
                    text("""
                        UPDATE pages
                        SET text = COALESCE(:text, text),
                            status = COALESCE(:status, status),
                            is_verified = COALESCE(:is_verified, is_verified),
                            is_indexed = CASE
                                WHEN :text IS NOT NULL AND text IS DISTINCT FROM :text
                                THEN FALSE
                                ELSE is_indexed
                            END,
                            pipeline_step = CASE
                                WHEN :text IS NOT NULL AND text IS DISTINCT FROM :text
                                THEN 'chunking'
                                ELSE pipeline_step
                            END,
                            milestone = CASE
                                WHEN :text IS NOT NULL AND text IS DISTINCT FROM :text
                                THEN 'idle'
                                ELSE milestone
                            END,
                            spell_check_milestone = CASE
                                WHEN :text IS NOT NULL AND text IS DISTINCT FROM :text
                                THEN 'idle'
                                ELSE spell_check_milestone
                            END,
                            last_updated = :last_updated,
                            updated_by = :updated_by
                        WHERE book_id = :book_id AND page_number = :page_number
                    """),
                    {
                        "book_id": book_id,
                        "page_number": page_number,
                        "text": normalize_uyghur_chars(new_text) if new_text is not None else None,
                        "status": result.get("status"),
                        "is_verified": result.get("isVerified") or result.get("is_verified"),
                        "last_updated": datetime.now(timezone.utc),
                        "updated_by": current_user.email,
                    }
                )

    # Remove pages from book_update (already processed above)
    book_update.pop("pages", None)

    # Remove id field to avoid conflict with book_id parameter
    book_update.pop("id", None)

    # Remove computed/read-only fields (already in snake_case after conversion)
    read_only_fields = [
        "upload_date", "created_by", "completed_count", "last_error",
        "pipeline_stats", "page_stats"
    ]
    for field in read_only_fields:
        book_update.pop(field, None)

    # Set system fields
    book_update["last_updated"] = datetime.now(timezone.utc)
    book_update["updated_by"] = current_user.email

    # Normalize cover_url to relative path if it contains covers/
    if "cover_url" in book_update and book_update["cover_url"]:
        import re
        match = re.search(r"covers/([^/?#]+)", book_update["cover_url"])
        if match:
            book_update["cover_url"] = f"covers/{match.group(1)}"

    # Normalize categories: strip quotes and filter empties
    if "categories" in book_update and isinstance(book_update["categories"], list):
        book_update["categories"] = [
            c.strip().strip('"').strip() 
            for c in book_update["categories"] 
            if isinstance(c, str) and c.strip()
        ]

    await books_repo.update_one(book_id, **book_update)
    await session.commit()

    # Invalidate cache
    await cache_service.delete(f"book:{book_id}")
    await cache_service.delete_pattern("books:list:*")
    if "categories" in book_update:
        await cache_service.delete_pattern("category:*")

    return {"status": "updated", "modified": True}



@router.get("/{book_id}/summary")
async def get_book_summary(
    book_id: str,
    current_user: Optional[User] = Depends(get_current_user_optional),
    session: AsyncSession = Depends(get_session),
):
    """Return the AI-generated semantic summary for a book.

    Allows guest access for public books.
    """
    from app.db.repositories.book_summaries import BookSummariesRepository
    from app.db.repositories.books import BooksRepository

    # Check if book exists and is accessible to current user
    books_repo = BooksRepository(session)
    book_obj = await books_repo.get(book_id)
    if not book_obj:
        raise HTTPException(status_code=404, detail=t("errors.book_not_found"))

    # Check access permission for guests (directly access book attributes)
    if not current_user:
        # Guest access: only allow if book is public and ready
        book_status = getattr(book_obj, 'status', None)
        book_visibility = getattr(book_obj, 'visibility', 'public')
        if book_status != 'ready' or book_visibility != 'public':
            raise HTTPException(status_code=401, detail=t("errors.authentication_required"))

    summaries_repo = BookSummariesRepository(session)
    summary = await summaries_repo.get_by_book_id(book_id)
    if not summary:
        raise HTTPException(status_code=404, detail=t("errors.book_summary_not_found"))
    return {"summary": summary.summary, "generated_at": summary.generated_at}


@router.delete("/{book_id}")
async def delete_book(
    book_id: str,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Delete book with SQLAlchemy"""
    books_repo = BooksRepository(session)
    pages_repo = PagesRepository(session)

    # Get book record to access original filename
    book = await books_repo.get(book_id)
    if not book:
        raise HTTPException(status_code=404, detail=t("errors.book_not_found"))

    # Delete local PDF file (if exists)
    file_path = settings.uploads_dir / f"{book_id}.pdf"
    if file_path.exists():
        os.remove(file_path)

    # Delete from GCS storage
    try:
        # Delete standardized PDF file
        await storage.delete_file(f"uploads/{book_id}.pdf")
        logger.info(f"Deleted standardized file from GCS: uploads/{book_id}.pdf")

        # Delete original file if it had a non-standard name
        if book.file_name and book.file_name != f"{book_id}.pdf":
            await storage.delete_file(f"uploads/{book.file_name}")
            logger.info(f"Deleted original file from GCS: uploads/{book.file_name}")

        # Delete cover file
        await storage.delete_file(f"covers/{book_id}.jpg")
        logger.info(f"Deleted cover from GCS: covers/{book_id}.jpg")

    except Exception as e:
        # Log but don't fail the deletion if GCS cleanup fails
        logger.warning(f"Failed to delete some GCS files for book {book_id}: {str(e)}")

    # Delete associated pages first
    await pages_repo.delete_by_book(book_id)

    # Delete book from database
    deleted = await books_repo.delete_one(book_id)
    await session.commit()

    if deleted:
        # Invalidate cache
        await cache_service.delete(f"book:{book_id}")
        await cache_service.delete_pattern("books:list:*")
        await cache_service.delete_pattern("category:*")
        await cache_service.delete_pattern(f"rag:search:{book_id}:*")
        await cache_service.delete_pattern("rag:summary_search:*")
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail=t("errors.book_not_found"))



@router.post("/upload-cover")
async def upload_cover(
    title: str = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Upload book cover with SQLAlchemy"""
    from PIL import Image
    from app.db.models import Book as BookDB

    books_repo = BooksRepository(session)

    # Find book by title (case-insensitive search)
    stmt = select(BookDB).where(BookDB.title.ilike(f"%{title}%"))
    result = await session.execute(stmt)
    book = result.scalar_one_or_none()

    if not book:
        raise HTTPException(status_code=404, detail=t("errors.book_title_not_found", title=title))

    book_id = book.id

    allowed_types = ["image/png", "image/jpeg", "image/jpg", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail=t("errors.invalid_file_type", allowed=", ".join(allowed_types)))

    try:
        image_data = await file.read()
        img = Image.open(io.BytesIO(image_data))
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        # Save to temp file first for storage provider to upload
        temp_cover_path = settings.uploads_dir / f".cover_upload_{book_id}.jpg"
        img.save(temp_cover_path, "JPEG", quality=90)
        
        # Upload to storage (works with GCS or Local)
        remote_cover_path = f"covers/{book_id}.jpg"
        await storage.upload_file(temp_cover_path, remote_cover_path)
        cover_url = remote_cover_path
        
        # Cleanup temp file
        temp_cover_path.unlink(missing_ok=True)
        
    except Exception as exc:
        raise HTTPException(status_code=500, detail=t("errors.image_process_failed", error=str(exc)))

    await books_repo.update_one(
        book_id,
        cover_url=cover_url,
        last_updated=datetime.now(timezone.utc),
        updated_by=current_user.email
    )
    await session.commit()

    return {
        "status": "success",
        "bookId": book_id,
        "title": book.title,
        "coverUrl": f"{storage.get_public_url(cover_url)}?v={int(datetime.now(timezone.utc).timestamp())}",
    }


@router.post("/{book_id}/cover")
async def update_book_cover(
    book_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Update book cover by book ID with SQLAlchemy and storage service"""
    from PIL import Image
    
    books_repo = BooksRepository(session)
    book = await books_repo.get(book_id)
    if not book:
        raise HTTPException(status_code=404, detail=t("errors.book_not_found"))

    allowed_types = ["image/png", "image/jpeg", "image/jpg", "image/webp", "application/octet-stream"]
    if file.content_type not in allowed_types:
        # Some browsers might send image/jpg as application/octet-stream for some reason, 
        # but let's be strict for now or trust PIL to check.
        pass

    try:
        image_data = await file.read()
        img = Image.open(io.BytesIO(image_data))
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        
        # Save to temp file first for storage provider to upload
        temp_cover_path = settings.uploads_dir / f".cover_update_{book_id}.jpg"
        img.save(temp_cover_path, "JPEG", quality=90)
        
        # Upload to storage (works with GCS or Local)
        remote_cover_path = f"covers/{book_id}.jpg"
        await storage.upload_file(temp_cover_path, remote_cover_path)
        cover_url = remote_cover_path
        
        # Cleanup temp file
        temp_cover_path.unlink(missing_ok=True)
        
    except Exception as exc:
        logger.error(f"Failed to process cover for book {book_id}: {exc}")
        raise HTTPException(status_code=500, detail=t("errors.image_process_failed", error=str(exc)))

    await books_repo.update_one(
        book_id,
        cover_url=cover_url,
        last_updated=datetime.now(timezone.utc),
        updated_by=current_user.email
    )
    await session.commit()

    return {
        "status": "success",
        "bookId": book_id,
        "coverUrl": f"{storage.get_public_url(cover_url)}?v={int(datetime.now(timezone.utc).timestamp())}",
    }


@router.get("/{book_id}/download")
async def download_book(
    book_id: str,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Download the original book file (PDF or DOCX) from storage."""
    from fastapi.responses import StreamingResponse

    books_repo = BooksRepository(session)
    book = await books_repo.get(book_id)
    if not book:
        raise HTTPException(status_code=404, detail=t("errors.book_not_found"))

    # Determine remote path (standardized or original)
    ext = f".{book.file_type}"
    remote_path = f"uploads/{book_id}{ext}"
    
    # Check if standardized path exists, fallback to original file_name
    if not storage.exists(remote_path) and book.file_name:
        remote_path = f"uploads/{book.file_name}"

    if not storage.exists(remote_path):
        raise HTTPException(status_code=404, detail=t("errors.file_not_found_in_storage"))

    try:
        # Get a readable stream directly from storage (doesn't load entire file into memory)
        stream = storage.get_stream(remote_path)
        media_type = "application/pdf" if book.file_type == "pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        
        # Use a safe filename for the download, handling non-ASCII characters for RFC 5987
        from urllib.parse import quote
        download_name = book.file_name or f"{book.title or book_id}{ext}"
        if not download_name.lower().endswith(ext):
            download_name += ext

        # Sanitize fallback filename for standard 'filename' (latin-1 only)
        # We replace non-latin characters with underscores or similar for the fallback
        safe_fallback = "".join(c if ord(c) < 128 else "_" for c in download_name)
        encoded_filename = quote(download_name)

        def iter_file():
            yield from stream
            stream.close()

        return StreamingResponse(
            iter_file(),
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename=\"{safe_fallback}\"; filename*=UTF-8''{encoded_filename}"}
        )
    except Exception as exc:
        logger.error(f"Failed to download book {book_id}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


