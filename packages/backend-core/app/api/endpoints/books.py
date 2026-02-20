from __future__ import annotations

import hashlib
import uuid
import os
import io
import re
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.db.session import get_session
from app.db.repositories.books import BooksRepository
from app.db.repositories.pages import PagesRepository
from app.services.discovery_service import DiscoveryService
from app.models.schemas import Book, PaginatedBooks, ExtractionResult
from app.models.user import User
from app.queue import enqueue_pdf_processing
from app.services.spell_check_service import spell_check_service
from app.services.storage_service import storage
from app.auth.dependencies import (
    get_current_user,
    get_current_user_optional,
    require_admin,
    require_editor,
    require_reader,
)
import logging
from app.utils.markdown import normalize_markdown
from app.utils.text import generate_uyghur_regex

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

router = APIRouter()


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
    current_user: Optional[User] = Depends(get_current_user_optional),
    session: AsyncSession = Depends(get_session),
):
    """Get paginated books list with SQLAlchemy"""
    from sqlalchemy import select, func, or_, and_, desc, asc, any_
    from app.db.models import Book as BookDB
    from app.db.models import Page as PageDB
    from app.models.schemas import Book as BookSchema, ExtractionResult

    skip = (page - 1) * pageSize

    # Build base query conditions
    conditions = []
    
    import logging
    logger = logging.getLogger("app.api.books")
    logger.info(f"Search request: q={repr(q)}, category={repr(category)}, groupByWork={groupByWork}")

    # Guest access restriction
    if current_user is None:
        conditions.append(BookDB.status == "ready")
        conditions.append(or_(BookDB.visibility == "public", BookDB.visibility == None))

    # Category filter
    if category:
        conditions.append(category == any_(BookDB.categories))

    # Search filter
    if q:
        if '\u0626' in q:
            q_alt = q.replace('\u0626', '\u064A\u0654')
        elif '\u064A\u0654' in q:
            q_alt = q.replace('\u064A\u0654', '\u0626')
        else:
            q_alt = q
        
        search_filter = or_(
            BookDB.title.ilike(f"%{q}%"),
            BookDB.author.ilike(f"%{q}%"),
            BookDB.title.ilike(f"%{q_alt}%"),
            BookDB.author.ilike(f"%{q_alt}%"),
            q == any_(BookDB.categories),
            q_alt == any_(BookDB.categories)
        )
        conditions.append(search_filter)
        logger.info(f"Applied search filter: q={repr(q)}, q_alt={repr(q_alt)}")

    # Base query for counting
    total_stmt = select(func.count(BookDB.id))
    if conditions:
        total_stmt = total_stmt.where(and_(*conditions))
    
    total_res = await session.execute(total_stmt)
    total = total_res.scalar() or 0

    # Query for total ready (publicly accessible) books
    if groupByWork:
        # For grouped view, count unique (title, author, volume) combinations
        subq_conditions = [
            BookDB.status == "ready",
            or_(BookDB.visibility == "public", BookDB.visibility == None)
        ]
        # Append search/category filters to the ready count too
        if category:
            subq_conditions.append(category == any_(BookDB.categories))
        if q:
             if '\u0626' in q:
                q_alt = q.replace('\u0626', '\u064A\u0654')
             elif '\u064A\u0654' in q:
                q_alt = q.replace('\u064A\u0654', '\u0626')
             else:
                q_alt = q
                
             subq_conditions.append(or_(
                BookDB.title.ilike(f"%{q}%"),
                BookDB.author.ilike(f"%{q}%"),
                BookDB.title.ilike(f"%{q_alt}%"),
                BookDB.author.ilike(f"%{q_alt}%"),
                q == any_(BookDB.categories),
                q_alt == any_(BookDB.categories)
             ))

        subq = (
            select(BookDB.title, BookDB.author, BookDB.volume)
            .where(and_(*subq_conditions))
            .group_by(BookDB.title, BookDB.author, BookDB.volume)
            .subquery()
        )
        ready_stmt = select(func.count()).select_from(subq)
    else:
        ready_stmt = select(func.count(BookDB.id)).where(
            and_(
                BookDB.status == "ready",
                or_(BookDB.visibility == "public", BookDB.visibility == None)
            )
        )
    ready_res = await session.execute(ready_stmt)
    total_ready = ready_res.scalar() or 0
    logger.info(f"Total ready count: {total_ready}")

    if groupByWork:
        # Get ALL matching books for grouping
        stmt = select(BookDB)
        if conditions:
            stmt = stmt.where(and_(*conditions))
        
        # Sort by upload_date for work grouping
        if order == -1:
            stmt = stmt.order_by(BookDB.upload_date.desc())
        else:
            stmt = stmt.order_by(BookDB.upload_date.asc())

        result = await session.execute(stmt)
        all_books_models = result.scalars().all()

        # Get page stats for these books
        book_ids = [str(b.id) for b in all_books_models]
        stats_by_book = {}
        if book_ids:
            stats_stmt = select(
                PageDB.book_id,
                PageDB.status,
                func.count().label("count")
            ).where(
                PageDB.book_id.in_(book_ids)
            ).group_by(PageDB.book_id, PageDB.status)

            stats_result = await session.execute(stats_stmt)
            for row in stats_result.fetchall():
                if row.book_id not in stats_by_book:
                    stats_by_book[row.book_id] = {}
                stats_by_book[row.book_id][row.status] = row.count

        # Group by work (title and author)
        work_groups = {}
        no_work_books = []
        
        for b in all_books_models:
            book_title = b.title
            book_author = b.author or ""
            
            if book_title:
                # Include volume in work_key to treat different volumes as separate works for deduplication
                work_key = (book_title, book_author, b.volume)
                if work_key not in work_groups:
                    work_groups[work_key] = []
                work_groups[work_key].append(b)
            else:
                no_work_books.append(b)

        # Build list of works (using newest/oldest book as representative)
        works_list = []
        import json
        for work_key, volumes in work_groups.items():
            rep = volumes[0]
            # Parse last_error from JSON string if needed
            last_error_obj = None
            if rep.last_error:
                if isinstance(rep.last_error, str):
                    try:
                        last_error_obj = json.loads(rep.last_error)
                    except:
                        last_error_obj = None
                else:
                    last_error_obj = rep.last_error

            # Calculate total stats for the work group
            group_completed = 0
            group_error = 0
            for v in volumes:
                v_stats = stats_by_book.get(str(v.id), {})
                group_completed += v_stats.get("completed", 0)
                group_error += v_stats.get("error", 0)

            # Convert ORM object to dict
            rep_dict = {
                "id": rep.id,
                "content_hash": rep.content_hash,
                "title": rep.title,
                "author": rep.author or "",
                "volume": rep.volume,
                "total_pages": sum(v.total_pages or 0 for v in volumes),
                "pages": [],
                "status": rep.status,
                "upload_date": rep.upload_date,
                "last_updated": rep.last_updated,
                "updated_by": rep.updated_by,
                "created_by": rep.created_by,
                "cover_url": rep.cover_url,
                "visibility": rep.visibility,
                "processing_step": rep.processing_step,
                "categories": rep.categories,
                "last_error": last_error_obj,
                "completed_count": group_completed,
                "error_count": group_error,
            }
            works_list.append(BookSchema.model_validate(rep_dict))

        for b in no_work_books:
            # Parse last_error from JSON string if needed
            b_last_error_obj = None
            if b.last_error:
                if isinstance(b.last_error, str):
                    try:
                        b_last_error_obj = json.loads(b.last_error)
                    except:
                        b_last_error_obj = None
                else:
                    b_last_error_obj = b.last_error

            b_stats = stats_by_book.get(str(b.id), {})
            # Convert ORM object to dict
            b_dict = {
                "id": b.id,
                "content_hash": b.content_hash,
                "title": b.title,
                "author": b.author or "",
                "volume": b.volume,
                "total_pages": b.total_pages or 0,
                "pages": [],
                "status": b.status,
                "upload_date": b.upload_date,
                "last_updated": b.last_updated,
                "updated_by": b.updated_by,
                "created_by": b.created_by,
                "cover_url": b.cover_url,
                "visibility": b.visibility,
                "processing_step": b.processing_step,
                "categories": b.categories,
                "errors": b.errors,
                "last_error": b_last_error_obj,
                "completed_count": b_stats.get("completed", 0),
                "error_count": b_stats.get("error", 0),
            }
            works_list.append(BookSchema.model_validate(b_dict))

        # Paginate results
        books_data = works_list[skip : skip + pageSize]
        total = len(works_list)
    else:
        # Standard flat list query
        stmt = select(BookDB)
        if conditions:
            stmt = stmt.where(and_(*conditions))
        
        # Mapping sorting
        sort_map = {
            "title": BookDB.title,
            "author": BookDB.author,
            "uploadDate": BookDB.upload_date,
            "lastUpdated": BookDB.last_updated
        }
        sort_col = sort_map.get(sortBy, BookDB.upload_date)
        if order == -1:
            stmt = stmt.order_by(sort_col.desc())
        else:
            stmt = stmt.order_by(sort_col.asc())

        stmt = stmt.offset(skip).limit(pageSize)
        result = await session.execute(stmt)
        books_objs = result.scalars().all()

        # Get page stats for these books
        book_ids = [str(b.id) for b in books_objs]
        stats_by_book = {}
        if book_ids:
            stats_stmt = select(
                PageDB.book_id,
                PageDB.status,
                func.count().label("count")
            ).where(
                PageDB.book_id.in_(book_ids)
            ).group_by(PageDB.book_id, PageDB.status)

            stats_result = await session.execute(stats_stmt)
            for row in stats_result.fetchall():
                if row.book_id not in stats_by_book:
                    stats_by_book[row.book_id] = {}
                stats_by_book[row.book_id][row.status] = row.count

        books_data = []
        import json
        for b in books_objs:
            # Parse last_error from JSON string if needed
            last_error_obj = None
            if b.last_error:
                if isinstance(b.last_error, str):
                    try:
                        last_error_obj = json.loads(b.last_error)
                    except:
                        last_error_obj = None
                else:
                    last_error_obj = b.last_error

            # Create dict from ORM object, excluding lazy-loaded pages relationship
            b_dict = {
                "id": b.id,
                "content_hash": b.content_hash,
                "title": b.title,
                "author": b.author or "",
                "volume": b.volume,
                "total_pages": b.total_pages,
                "pages": [],  # We don't load pages in this endpoint
                "status": b.status,
                "upload_date": b.upload_date,
                "last_updated": b.last_updated,
                "updated_by": b.updated_by,
                "created_by": b.created_by,
                "cover_url": b.cover_url,
                "visibility": b.visibility,
                "processing_step": b.processing_step,
                "categories": b.categories,
                "errors": b.errors,
                "last_error": last_error_obj,
                "completed_count": 0,
                "error_count": 0,
            }
            s_data = BookSchema.model_validate(b_dict)
            b_stats = stats_by_book.get(str(b.id), {})
            s_data.completed_count = b_stats.get("completed", 0)
            s_data.error_count = b_stats.get("error", 0)
            books_data.append(s_data)

    return {
        "books": books_data,
        "total": total,
        "total_ready": total_ready,
        "page": page,
        "page_size": pageSize,
    }



@router.get("/random-proverb")
async def get_random_proverb(
    session: AsyncSession = Depends(get_session),
):
    """Fetch a random proverb with SQLAlchemy"""
    from app.db.repositories.proverbs import ProverbsRepository

    proverbs_repo = ProverbsRepository(session)
    keywords = ["كىتاب", "بىلىم", "ئەقىل", "پاراسەت"]

    # Build regex pattern for all keywords (OR condition)
    # Pattern: (keyword1|keyword2|keyword3|keyword4)
    patterns = [generate_uyghur_regex(k) for k in keywords]
    combined_pattern = "(" + "|".join(patterns) + ")"

    # Get random proverb matching any of the keywords
    proverb = await proverbs_repo.get_random_proverb(text_pattern=combined_pattern)

    if proverb:
        return {
            "text": proverb.text,
            "volume": proverb.volume,
            "pageNumber": proverb.page_number
        }

    # Fallback if no proverbs found
    return {
        "text": "كىتاب — بىلىم بۇلىقى.",
        "volume": 1,
        "pageNumber": 1
    }


@router.get("/top-categories")
async def get_top_categories(
    limit: int = 10,
    current_user: Optional[User] = Depends(get_current_user_optional),
    session: AsyncSession = Depends(get_session),
):
    """Get most popular categories with SQLAlchemy"""
    # Build WHERE clause for guest access
    where_conditions = []
    params = {"limit": limit}

    if current_user is None:
        # Guests can only see public ready books
        where_conditions.append("status = 'ready'")
        where_conditions.append("(visibility = 'public' OR visibility IS NULL)")

    where_clause = " AND ".join(where_conditions) if where_conditions else "TRUE"

    # SQL to unnest categories and count
    sql = text(f"""
        SELECT category, COUNT(*) as count
        FROM books,
        UNNEST(categories) AS category
        WHERE {where_clause}
        GROUP BY category
        ORDER BY count DESC
        LIMIT :limit
    """)

    result = await session.execute(sql, params)
    rows = result.fetchall()
    categories = [row.category for row in rows]

    return {"categories": categories}


@router.get("/suggest")
async def suggest_books(
    q: str = "",
    current_user: Optional[User] = Depends(get_current_user_optional),
    session: AsyncSession = Depends(get_session),
):
    """Provide autocomplete suggestions with SQLAlchemy"""
    from sqlalchemy import select, or_, and_, func
    from app.db.models import Book

    if not q or len(q) < 2:
        return {"suggestions": []}

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
    search_pattern = f"%{normalized_q}%"

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

        for cat in (categories or []):
            if cat and search_re.search(cat) and cat not in seen:
                suggestions.append({"text": cat, "type": "category"})
                seen.add(cat)

    # Sort suggestions: titles first, then authors, then categories
    type_priority = {"title": 0, "author": 1, "category": 2}
    suggestions.sort(key=lambda x: type_priority.get(x["type"], 3))

    return {"suggestions": suggestions[:10]}


@router.get("/{book_id}", response_model=Book)
async def get_book(
    book_id: str,
    current_user: Optional[User] = Depends(get_current_user_optional),
    session: AsyncSession = Depends(get_session),
):
    """Get a single book by ID with SQLAlchemy - returns metadata only, no pages"""
    from sqlalchemy import select, func
    from app.db.models import Page as PageDB
    books_repo = BooksRepository(session)

    # Get book from SQLAlchemy
    book_model = await books_repo.get(book_id)
    if not book_model:
        raise HTTPException(status_code=404, detail="Book not found")

    # Convert to dict for access check (legacy function expects dict)
    book_dict = {
        "id": str(book_model.id),
        "status": book_model.status,
        "visibility": book_model.visibility,
    }

    # Check guest access
    if not await check_book_access_for_guest(book_dict, current_user):
        raise HTTPException(status_code=403, detail="Access denied")

    # No longer fetch pages here - frontend fetches them via /pages endpoint
    # This saves a wasteful DB query for up to 10,000 rows we were discarding

    # Parse last_error from JSON string if needed
    import json
    last_error_obj = None
    if book_model.last_error:
        if isinstance(book_model.last_error, str):
            try:
                last_error_obj = json.loads(book_model.last_error)
            except:
                last_error_obj = None
        else:
            last_error_obj = book_model.last_error

    # Get page stats for this book
    stats_stmt = select(
        PageDB.status,
        func.count().label("count")
    ).where(
        PageDB.book_id == book_id
    ).group_by(PageDB.status)

    stats_result = await session.execute(stats_stmt)
    stats = {row.status: row.count for row in stats_result.fetchall()}

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
        "upload_date": book_model.upload_date,
        "last_updated": book_model.last_updated,
        "updated_by": book_model.updated_by,
        "created_by": book_model.created_by,
        "cover_url": book_model.cover_url,
        "visibility": book_model.visibility,
        "processing_step": book_model.processing_step,
        "categories": book_model.categories,
        "last_error": last_error_obj,
        "completed_count": stats.get("completed", 0),
        "error_count": stats.get("error", 0),
    }

    # Convert SQLAlchemy models to Pydantic (automatic camelCase conversion)
    book_response = Book.model_validate(book_dict)

    # We intentionally return empty pages here. The frontend should fetch content 
    # via the /content endpoint or paginated API.
    book_response.pages = []

    return book_response


@router.get("/stats")
async def get_book_stats(
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Get book statistics for admin dashboard"""
    repo = BooksRepository(session)
    
    # Count by status
    pending = await repo.count_by_status("pending")
    processing = await repo.count_by_status("processing")
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
    current_user: Optional[User] = Depends(get_current_user_optional),
    session: AsyncSession = Depends(get_session),
):
    """Get full book content with SQLAlchemy"""
    books_repo = BooksRepository(session)
    pages_repo = PagesRepository(session)

    # Verify book exists and check access
    book_model = await books_repo.get(book_id)
    if not book_model:
        raise HTTPException(status_code=404, detail="Book not found")

    # Convert to dict for access check
    book_dict = {
        "id": str(book_model.id),
        "status": book_model.status,
        "visibility": book_model.visibility,
    }

    if not await check_book_access_for_guest(book_dict, current_user):
        raise HTTPException(status_code=403, detail="Access denied")

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
        raise HTTPException(status_code=404, detail="Book not found")

    # Convert to dict for access check
    book_dict = {
        "id": str(book_model.id),
        "status": book_model.status,
        "visibility": book_model.visibility,
    }

    if not await check_book_access_for_guest(book_dict, current_user):
        raise HTTPException(status_code=403, detail="Access denied")

    # Get page by number
    page = await pages_repo.find_one(book_id, page_num)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

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
        raise HTTPException(status_code=404, detail="Book not found")

    # Convert to dict for access check
    book_dict = {
        "id": str(book_model.id),
        "status": book_model.status,
        "visibility": book_model.visibility,
    }

    if not await check_book_access_for_guest(book_dict, current_user):
        raise HTTPException(status_code=403, detail="Access denied")

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
        raise HTTPException(status_code=404, detail="Book not found")

    # Convert to dict for access check (legacy function expects dict)
    book_dict = {
        "id": str(book_model.id),
        "status": book_model.status,
        "visibility": book_model.visibility,
    }

    # Check guest access
    if not await check_book_access_for_guest(book_dict, current_user):
        raise HTTPException(status_code=403, detail="Access denied")

    # Convert to Pydantic with automatic camelCase
    return Book.model_validate(book_model)


@router.post("/upload")
async def upload_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Upload PDF with SQLAlchemy"""
    books_repo = BooksRepository(session)

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    temp_path = settings.uploads_dir / f".upload_{uuid.uuid4().hex}.pdf"
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

        book_id = hashlib.md5(f"{file.filename}{datetime.utcnow()}".encode()).hexdigest()[:12]
        remote_path = f"uploads/{book_id}.pdf"
        await storage.upload_file(temp_path, remote_path)
        temp_path.unlink(missing_ok=True)
    except Exception:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise

    now = datetime.utcnow()

    # Create book using repository
    new_book = await books_repo.create(
        id=book_id,
        content_hash=content_hash,
        title=file.filename.replace(".pdf", ""),
        file_name=file.filename,
        author="",
        volume=None,
        total_pages=0,
        status="pending",
        upload_date=now,
        last_updated=now,
        created_by=current_user.email,
        updated_by=current_user.email,
        categories=[],
        visibility="private",
        processing_step="ocr",
        source="upload",
    )

    await session.commit()

    return {"bookId": book_id, "status": "uploaded"}


@router.post("/{book_id}/start-ocr")
async def start_ocr(
    book_id: str,
    payload: dict,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Start OCR processing with SQLAlchemy"""
    books_repo = BooksRepository(session)
    pages_repo = PagesRepository(session)
    provider = "gemini"

    book = await books_repo.get(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if book.status == "processing":
        # Note: processing_lock_expires_at field doesn't exist in current schema
        # TODO: Add processing lock mechanism if needed
        logger.warning(f"Book {book_id} is already processing. Allowing restart anyway.")

    # CLEAR OLD DATA
    if book.status != "pending":
        # Delete existing pages
        await pages_repo.delete_by_book(book_id)

    # Update book status
    await books_repo.update_one(
        book_id,
        status="processing",
        processing_step="ocr",
        last_updated=datetime.utcnow(),
        updated_by=current_user.email,
    )
    await session.commit()

    await enqueue_pdf_processing(book_id, reason=f"start_{provider}", background_tasks=background_tasks)
    return {"status": "started", "provider": provider}


@router.post("/{book_id}/retry-ocr")
async def retry_failed_ocr(
    book_id: str,
    background_tasks: BackgroundTasks,
    payload: Optional[dict] = None,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Retry failed OCR pages with SQLAlchemy"""
    from sqlalchemy import select, update
    from app.db.models import Page

    books_repo = BooksRepository(session)

    book = await books_repo.get(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if book.status == "processing":
        # Note: processing_lock_expires_at field doesn't exist in current schema
        logger.warning(f"Book {book_id} is already processing. Allowing retry anyway.")

    provider = "gemini"

    # Find failed pages
    failed_pages_stmt = select(Page.page_number).where(
        Page.book_id == book_id,
        Page.status == "error"
    )
    result = await session.execute(failed_pages_stmt)
    failed_pages = [row[0] for row in result.fetchall()]

    # Resume Logic: If no specific pages failed but book is in error state
    if not failed_pages and book.status == "error":
        await books_repo.update_one(
            book_id,
            status="processing",
            processing_step="ocr",
            last_updated=datetime.utcnow(),
            updated_by=current_user.email,
        )
        await session.commit()
        await enqueue_pdf_processing(book_id, reason="resume_error", background_tasks=background_tasks)
        return {"status": "resumed", "provider": provider}

    if not failed_pages:
        return {"status": "no_failed_pages"}

    # Update book status
    await books_repo.update_one(
        book_id,
        status="processing",
        processing_step="ocr",
        last_updated=datetime.utcnow(),
        updated_by=current_user.email,
    )

    # Reset failed pages to pending using raw SQL for is_indexed = FALSE
    await session.execute(
        text("""
            UPDATE pages
            SET status = 'pending',
                text = '',
                error = NULL,
                is_verified = FALSE,
                is_indexed = FALSE,
                last_updated = :last_updated,
                updated_by = :updated_by
            WHERE book_id = :book_id AND page_number = ANY(:page_numbers)
        """),
        {
            "book_id": book_id,
            "page_numbers": failed_pages,
            "last_updated": datetime.utcnow(),
            "updated_by": current_user.email
        }
    )

    await session.commit()
    await enqueue_pdf_processing(book_id, reason="retry_failed", background_tasks=background_tasks)
    return {"status": "retry_started", "provider": provider, "failedPages": failed_pages}





@router.post("/{book_id}/reprocess")
async def reprocess_book(
    book_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Reprocess book with SQLAlchemy"""
    books_repo = BooksRepository(session)

    book = await books_repo.get(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if book.status == "processing":
        logger.warning(f"Book {book_id} is already processing. Allowing reprocess anyway.")

    await books_repo.update_one(
        book_id,
        status="processing",
        last_updated=datetime.utcnow(),
        updated_by=current_user.email
    )
    await session.commit()

    await enqueue_pdf_processing(book_id, reason="reprocess", background_tasks=background_tasks)
    return {"status": "reprocessing_started"}


@router.post("/{book_id}/reindex")
async def reindex_book(
    book_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Reindex book embeddings with SQLAlchemy"""
    books_repo = BooksRepository(session)

    book = await books_repo.get(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if book.status == "processing":
        logger.warning(f"Book {book_id} is already processing. Allowing reindex anyway.")

    # Reset indexing status for all completed pages using raw SQL
    # Note: Page model now uses is_indexed field instead of embedding
    await session.execute(
        text("""
            UPDATE pages
            SET is_indexed = FALSE, last_updated = NOW(), updated_by = :updated_by
            WHERE book_id = :book_id AND status = 'completed'
        """),
        {"book_id": book_id, "updated_by": current_user.email}
    )

    await books_repo.update_one(
        book_id,
        status="processing",
        last_updated=datetime.utcnow(),
        updated_by=current_user.email
    )
    await session.commit()

    await enqueue_pdf_processing(book_id, reason="reindex", background_tasks=background_tasks)
    return {"status": "reindex_started"}


@router.post("/{book_id}/pages/{page_num}/reset")
async def reset_page(
    book_id: str,
    page_num: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Reset page to pending status with SQLAlchemy"""
    books_repo = BooksRepository(session)

    # Update page using raw SQL for is_indexed = FALSE
    await session.execute(
        text("""
            UPDATE pages
            SET status = 'pending',
                text = '',
                is_verified = FALSE,
                is_indexed = FALSE,
                last_updated = NOW(),
                updated_by = :updated_by
            WHERE book_id = :book_id AND page_number = :page_number
        """),
        {"book_id": book_id, "page_number": page_num, "updated_by": current_user.email}
    )

    await books_repo.update_one(
        book_id,
        status="processing",
        last_updated=datetime.utcnow(),
        updated_by=current_user.email
    )
    await session.commit()

    await enqueue_pdf_processing(book_id, reason="page_reset", background_tasks=background_tasks)
    return {"status": "page_reset_started"}


@router.post("/{book_id}/pages/{page_num}/update")
async def update_page_text(
    book_id: str,
    page_num: int,
    payload: dict,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Update page text with SQLAlchemy"""
    books_repo = BooksRepository(session)

    new_text = normalize_markdown(payload.get("text", ""))

    # Update page using raw SQL for is_indexed = FALSE
    await session.execute(
        text("""
            UPDATE pages
            SET text = :text,
                status = 'completed',
                is_verified = TRUE,
                is_indexed = FALSE,
                last_updated = NOW(),
                updated_by = :updated_by
            WHERE book_id = :book_id AND page_number = :page_number
        """),
        {"book_id": book_id, "page_number": page_num, "text": new_text, "updated_by": current_user.email}
    )

    await books_repo.update_one(
        book_id,
        last_updated=datetime.utcnow(),
        updated_by=current_user.email
    )
    await session.commit()

    await enqueue_pdf_processing(book_id, reason="page_update", background_tasks=background_tasks)
    return {"status": "page_updated", "requires_rag": True}


@router.post("/")
async def create_book(
    book: Book,
    background_tasks: BackgroundTasks,
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
    pages_input = book_dict.pop("pages", []) or []

    # Sync pages if they exist
    if pages_input:
        for r in pages_input:
            page_text = normalize_markdown(r.get("text") or "")
            page_data = {
                "book_id": book_id,
                "page_number": r.get("page_number"),
                "text": page_text,
                "status": r.get("status", "completed"),
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
        book_dict["last_updated"] = datetime.utcnow()
        await books_repo.update_one(book_id, **book_dict)
    else:
        # Create new book
        book_dict["created_by"] = current_user.email
        book_dict["updated_by"] = current_user.email
        book_dict["upload_date"] = datetime.utcnow()
        book_dict["last_updated"] = datetime.utcnow()
        await books_repo.create(**book_dict)

    await session.commit()
    await enqueue_pdf_processing(book_id, reason="create_book", background_tasks=background_tasks)
    return {"status": "success"}


@router.put("/{book_id}")
async def update_book_details(
    book_id: str,
    book_update: dict,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Update book details with SQLAlchemy"""
    books_repo = BooksRepository(session)
    pages_repo = PagesRepository(session)

    # Verify book exists
    book = await books_repo.get(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    # Convert all camelCase keys to snake_case
    book_update = convert_dict_keys_to_snake(book_update)

    # Remove fields we don't want to update
    book_update.pop("upload_date", None)
    book_update.pop("content", None)

    has_page_updates = False
    if "pages" in book_update:
        for result in book_update.get("pages") or []:
            if "text" in result:
                result["text"] = normalize_markdown(result.get("text") or "")

            # Sync to pages collection
            if "pageNumber" in result or "page_number" in result:
                has_page_updates = True
                page_number = result.get("pageNumber") or result.get("page_number")
                new_text = result.get("text")

                # Only set is_indexed = FALSE if text actually changed
                # This optimizes reindexing to only process modified pages
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
                            last_updated = :last_updated,
                            updated_by = :updated_by
                        WHERE book_id = :book_id AND page_number = :page_number
                    """),
                    {
                        "book_id": book_id,
                        "page_number": page_number,
                        "text": new_text,
                        "status": result.get("status"),
                        "is_verified": result.get("isVerified") or result.get("is_verified"),
                        "last_updated": datetime.utcnow(),
                        "updated_by": current_user.email,
                    }
                )

    # Remove pages from book_update (already processed above)
    book_update.pop("pages", None)

    # Remove id field to avoid conflict with book_id parameter
    book_update.pop("id", None)

    # Remove computed/read-only fields (already in snake_case after conversion)
    read_only_fields = [
        "upload_date", "created_by", "error_count", "completed_count", "last_error"
    ]
    for field in read_only_fields:
        book_update.pop(field, None)

    # Set system fields
    book_update["last_updated"] = datetime.utcnow()
    book_update["updated_by"] = current_user.email

    await books_repo.update_one(book_id, **book_update)
    await session.commit()

    if has_page_updates:
        await enqueue_pdf_processing(book_id, reason="global_edit", background_tasks=background_tasks)

    return {"status": "updated", "modified": True}


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
        raise HTTPException(status_code=404, detail="Book not found")

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
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Book not found")


@router.post("/upload-cover")
async def upload_cover(
    title: str = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Upload book cover with SQLAlchemy"""
    from PIL import Image
    from sqlalchemy import select
    from app.db.models import Book as BookDB

    books_repo = BooksRepository(session)

    # Find book by title (case-insensitive search)
    stmt = select(BookDB).where(BookDB.title.ilike(f"%{title}%"))
    result = await session.execute(stmt)
    book = result.scalar_one_or_none()

    if not book:
        raise HTTPException(status_code=404, detail=f"Book with title '{title}' not found")

    book_id = book.id

    allowed_types = ["image/png", "image/jpeg", "image/jpg", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"Invalid file type. Allowed: {allowed_types}")

    try:
        image_data = await file.read()
        img = Image.open(io.BytesIO(image_data))
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        cover_path = settings.covers_dir / f"{book_id}.jpg"
        img.save(cover_path, "JPEG", quality=90)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to process image: {exc}")

    cover_url = f"/api/covers/{book_id}.jpg"
    await books_repo.update_one(
        book_id,
        cover_url=cover_url,
        last_updated=datetime.utcnow(),
        updated_by=current_user.email
    )
    await session.commit()

    return {
        "status": "success",
        "bookId": book_id,
        "title": book.title,
        "coverUrl": cover_url,
    }


@router.post("/{book_id}/spell-check")
async def check_book_spelling(
    book_id: str,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    try:
        results = await spell_check_service.check_book(book_id, session)
        return {
            "bookId": book_id,
            "status": "success",
            "totalPagesWithIssues": len(results),
            "results": {
                str(page_num): {
                    "pageNumber": check.pageNumber,
                    "corrections": [c.dict() for c in check.corrections],
                    "totalIssues": check.totalIssues,
                    "checkedAt": check.checkedAt,
                }
                for page_num, check in results.items()
            },
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Spell check failed: {exc}")


@router.post("/{book_id}/pages/{page_num}/spell-check")
async def check_page_spelling(
    book_id: str,
    page_num: int,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Check spelling for a single page with SQLAlchemy"""
    pages_repo = PagesRepository(session)

    page = await pages_repo.find_one(book_id, page_num)
    if not page:
        raise HTTPException(status_code=404, detail=f"Page {page_num} not found")

    page_text = page.text or ""
    if not page_text:
        return {
            "bookId": book_id,
            "pageNumber": page_num,
            "corrections": [],
            "totalIssues": 0,
            "message": "Page has no text to check",
        }

    try:
        spell_check = await spell_check_service.check_page_text(page_text, page_num)
        return {
            "bookId": book_id,
            "pageNumber": spell_check.pageNumber,
            "corrections": [c.dict() for c in spell_check.corrections],
            "totalIssues": spell_check.totalIssues,
            "checkedAt": spell_check.checkedAt,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Spell check failed: {exc}")


@router.post("/{book_id}/pages/{page_num}/apply-corrections")
async def apply_spelling_corrections(
    book_id: str,
    page_num: int,
    payload: dict,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    corrections = payload.get("corrections", [])
    try:
        success = await spell_check_service.apply_corrections(book_id, page_num, corrections, session, user_email=current_user.email)
        if success:
            await session.commit()
            await enqueue_pdf_processing(book_id, reason="spell_apply", background_tasks=background_tasks)
            return {
                "status": "success",
                "bookId": book_id,
                "pageNumber": page_num,
                "correctionsApplied": len(corrections),
                "message": "Corrections applied successfully. Embeddings will be regenerated.",
            }
        raise HTTPException(status_code=404, detail="Book or page not found")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to apply corrections: {exc}")


@router.post("/storage/sync")
async def sync_gcs_storage(
    force: bool = False,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Manually trigger GCS book discovery sync"""
    discovery = DiscoveryService(session)
    try:
        result = await discovery.sync_gcs_books(force=force)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"GCS sync failed: {exc}")
