from __future__ import annotations

import hashlib
import uuid
import os
import io
import re
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import text, and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.db.session import get_session
from app.db.repositories.books import BooksRepository
from app.db.repositories.pages import PagesRepository
from app.db.models import Page, Chunk
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
    current_user: Optional[User] = Depends(get_current_user_optional),
    session: AsyncSession = Depends(get_session),
):
    """Get paginated books list with SQLAlchemy"""
    from sqlalchemy import or_, and_, any_
    from app.db.models import Book as BookDB
    from app.db.models import Page as PageDB
    from app.models.schemas import Book as BookSchema

    skip = (page - 1) * pageSize

    # Build base query conditions
    conditions = []
    
    import logging
    logger = logging.getLogger("app.api.books")
    logger.info(f"Search request: q={repr(q)}, category={repr(category)}, groupByWork={groupByWork}")

    # Guest access restriction
    if current_user is None:
        conditions.append(BookDB.status == "ready")
        conditions.append(or_(BookDB.visibility == "public", BookDB.visibility is None))

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
            or_(BookDB.visibility == "public", BookDB.visibility is None)
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
                or_(BookDB.visibility == "public", BookDB.visibility is None)
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
        
        # Enhanced sorting: Group by (title, author) but sort groups by latest arrival,
        # and then sort volumes within each group.
        # This uses a window function to find the max upload date for each 'Work' (Series)
        series_latest = func.max(BookDB.upload_date).over(partition_by=[BookDB.title, BookDB.author])
        
        if order == -1:
            stmt = stmt.order_by(
                series_latest.desc(), 
                BookDB.title.asc(), 
                BookDB.author.asc(),
                BookDB.volume.asc().nulls_first()
            )
        else:
            stmt = stmt.order_by(
                series_latest.asc(), 
                BookDB.title.asc(), 
                BookDB.author.asc(),
                BookDB.volume.asc().nulls_first()
            )

        result = await session.execute(stmt)
        all_books_models = result.scalars().all()

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
                    except Exception:
                        last_error_obj = None
                else:
                    last_error_obj = rep.last_error

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
                "pipeline_step": rep.pipeline_step,
                "upload_date": rep.upload_date,
                "last_updated": rep.last_updated,
                "updated_by": rep.updated_by,
                "created_by": rep.created_by,
                "cover_url": f"{storage.get_public_url(rep.cover_url)}?v={int(rep.last_updated.timestamp())}" if rep.cover_url and rep.last_updated else (storage.get_public_url(rep.cover_url) if rep.cover_url else None),
                "visibility": rep.visibility,
                "categories": _normalize_categories(rep.categories),
                "last_error": last_error_obj,
                "read_count": rep.read_count or 0,
                "file_name": rep.file_name,
                "file_type": rep.file_type,
                "source": rep.source,
            }
            works_list.append(BookSchema.model_validate(rep_dict))

        for b in no_work_books:
            # Parse last_error from JSON string if needed
            b_last_error_obj = None
            if b.last_error:
                if isinstance(b.last_error, str):
                    try:
                        b_last_error_obj = json.loads(b.last_error)
                    except Exception:
                        b_last_error_obj = None
                else:
                    b_last_error_obj = b.last_error

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
                "pipeline_step": b.pipeline_step,
                "upload_date": b.upload_date,
                "last_updated": b.last_updated,
                "updated_by": b.updated_by,
                "created_by": b.created_by,
                "cover_url": f"{storage.get_public_url(b.cover_url)}?v={int(b.last_updated.timestamp())}" if b.cover_url and b.last_updated else (storage.get_public_url(b.cover_url) if b.cover_url else None),
                "visibility": b.visibility,
                "categories": _normalize_categories(b.categories),
                "last_error": b_last_error_obj,
                "read_count": b.read_count or 0,
                "file_name": b.file_name,
                "file_type": b.file_type,
                "source": b.source,
            }
            works_list.append(BookSchema.model_validate(b_dict))

        # Paginate results
        paginated_works = works_list[skip : skip + pageSize]
        total = len(works_list)
        
        books_data = []
        repo = BooksRepository(session)
        for pydantic_book in paginated_works:
            stats_dict = await repo.get_with_page_stats(str(pydantic_book.id))
            if stats_dict:
                pydantic_book.pipeline_stats = stats_dict.get("pipeline_stats", {})
            books_data.append(pydantic_book)
    else:
        # Standard flat list query
        repo = BooksRepository(session)
        stmt = select(BookDB)
        if conditions:
            stmt = stmt.where(and_(*conditions))
        
        # Mapping sorting
        if sortBy == "uploadDate":
            # Enhanced sorting: Keep series together
            series_latest = func.max(BookDB.upload_date).over(partition_by=[BookDB.title, BookDB.author])
            if order == -1:
                stmt = stmt.order_by(
                    series_latest.desc(), 
                    BookDB.title.asc(), 
                    BookDB.author.asc(),
                    BookDB.volume.asc().nulls_first()
                )
            else:
                stmt = stmt.order_by(
                    series_latest.asc(), 
                    BookDB.title.asc(), 
                    BookDB.author.asc(),
                    BookDB.volume.asc().nulls_first()
                )
        else:
            sort_map = {
                "title": BookDB.title,
                "author": BookDB.author,
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
                    except Exception:
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
                "pipeline_step": b.pipeline_step,
                "upload_date": b.upload_date,
                "last_updated": b.last_updated,
                "updated_by": b.updated_by,
                "created_by": b.created_by,
                "cover_url": f"{storage.get_public_url(b.cover_url)}?v={int(b.last_updated.timestamp())}" if b.cover_url and b.last_updated else (storage.get_public_url(b.cover_url) if b.cover_url else None),
                "visibility": b.visibility,
                "categories": _normalize_categories(b.categories),
                "last_error": last_error_obj,
                "read_count": b.read_count or 0,
                "file_name": b.file_name,
                "file_type": b.file_type,
                "source": b.source,
                "pipeline_stats": (await repo.get_with_page_stats(str(b.id))).get("pipeline_stats", {}) if repo else {}
            }
            s_data = BookSchema.model_validate(b_dict)
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
    keyword: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    """Fetch a random proverb with SQLAlchemy"""
    from app.db.repositories.proverbs import ProverbsRepository

    proverbs_repo = ProverbsRepository(session)
    
    if keyword:
        # Use provided keywords (supports comma-separated list)
        keywords = [k.strip() for k in keyword.split(",") if k.strip()]
        patterns = [generate_uyghur_regex(k) for k in keywords]
    else:
        # Use default keywords
        keywords = ["كىتاب", "بىلىم", "ئەقىل", "پاراسەت"]
        patterns = [generate_uyghur_regex(k) for k in keywords]

    # Build regex pattern (OR condition)
    if patterns:
        combined_pattern = "(" + "|".join(patterns) + ")"
    else:
        combined_pattern = ".*" # Match everything if somehow patterns is empty

    # Get random proverb matching the pattern
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
    limit: int = 100,
    sort: str = "count",  # "count" or "alphabetical"
    current_user: Optional[User] = Depends(get_current_user_optional),
    session: AsyncSession = Depends(get_session),
):
    """Get categories with optional sorting and limit"""
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

    return {"categories": categories}


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

    return {"suggestions": suggestions[:10]}


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
    import json
    last_error_obj = None
    if book_model.last_error:
        if isinstance(book_model.last_error, str):
            try:
                last_error_obj = json.loads(book_model.last_error)
            except Exception:
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
        "pipeline_stats": stats.get("pipeline_stats", {})
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

    return {"bookId": book_id, "status": "uploaded"}


@router.post("/{book_id}/reprocess")
async def reprocess_book(
    book_id: str,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Gracefully reprocess book from OCR step.

    Existing page text and chunks are preserved and replaced per-page as new
    OCR completes, so the book remains fully readable during reprocessing.
    The pipeline handles replacement atomically: OCR overwrites text per page,
    chunking replaces chunks per page, embedding re-embeds per page.
    """
    books_repo = BooksRepository(session)

    book = await books_repo.get(book_id)
    if not book:
        raise HTTPException(status_code=404, detail=t("errors.book_not_found"))

    # Reset all pages to ocr/idle but DO NOT clear text or delete chunks.
    # Existing content stays available for reading until new OCR replaces it
    # page-by-page through the normal pipeline flow.
    await session.execute(
        update(Page)
        .where(Page.book_id == book_id)
        .values(
            pipeline_step="ocr",
            milestone="idle",
            retry_count=0,
            is_indexed=False,
            status="pending",
            spell_check_milestone="idle",
            last_updated=datetime.now(timezone.utc),
            updated_by=current_user.email,
        )
    )

    # Keep book status "ready" so the book stays accessible to readers.
    # Update pipeline_step to "ocr" to signal reprocessing has started.
    await books_repo.update_one(
        book_id,
        pipeline_step="ocr",
        last_updated=datetime.now(timezone.utc),
        updated_by=current_user.email,
    )
    await session.commit()
    return {"status": "reprocessing_started"}


@router.post("/{book_id}/reindex")
async def reindex_book(
    book_id: str,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Reset post-OCR pages to chunking/idle so the worker re-chunks and re-embeds."""
    books_repo = BooksRepository(session)

    book = await books_repo.get(book_id)
    if not book:
        raise HTTPException(status_code=404, detail=t("errors.book_not_found"))

    # Reset all post-OCR pages to chunking/idle (text is intact, skip re-OCR)
    await session.execute(
        update(Page)
        .where(and_(
            Page.book_id == book_id,
            Page.pipeline_step.in_(['chunking', 'embedding', 'ready'])
        ))
        .values(
            is_indexed=False,
            pipeline_step='chunking',
            milestone='idle',
            retry_count=0,
            last_updated=datetime.now(timezone.utc),
            updated_by=current_user.email,
        )
    )

    # Delete existing chunks to force re-creation
    await session.execute(delete(Chunk).where(Chunk.book_id == book_id))

    await books_repo.update_one(
        book_id,
        status="pending",
        pipeline_step=None,
        last_updated=datetime.now(timezone.utc),
        updated_by=current_user.email,
    )
    await session.commit()
    return {"status": "reindex_started"}


@router.post("/{book_id}/reset-failed-pages")
async def reset_failed_pages(
    book_id: str,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Reset all exhausted-retry pages (milestone='failed') back to ocr/idle.

    Used when the worker has given up on pages after max retries and an admin
    wants to force another attempt from the OCR step.
    """
    books_repo = BooksRepository(session)

    book = await books_repo.get(book_id)
    if not book:
        raise HTTPException(status_code=404, detail=t("errors.book_not_found"))

    result = await session.execute(
        update(Page)
        .where(and_(
            Page.book_id == book_id,
            Page.milestone == "failed",
        ))
        .values(
            pipeline_step="ocr",
            milestone="idle",
            retry_count=0,
            last_updated=datetime.now(timezone.utc),
            updated_by=current_user.email,
        )
        .returning(Page.id)
    )
    reset_count = len(result.fetchall())

    if reset_count == 0:
        return {"status": "no_failed_pages", "count": 0}

    await books_repo.update_one(
        book_id,
        status="pending",
        pipeline_step=None,
        last_updated=datetime.now(timezone.utc),
        updated_by=current_user.email,
    )
    await session.commit()
    logger.info(f"Reset {reset_count} failed v2 pages for book {book_id} by {current_user.email}")
    return {"status": "reset", "count": reset_count}


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

    new_text = normalize_markdown(payload.get("text", ""))

    # 1. Update page text and status
    page = await pages_repo.find_one(book_id, page_num)
    if not page:
        raise HTTPException(status_code=404, detail=t("errors.page_not_found"))
    
    page.text = new_text
    page.status = 'ocr_done'
    page.is_verified = True
    page.is_indexed = False
    page.last_updated = datetime.now(timezone.utc)
    page.updated_by = current_user.email
    
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
        await session.flush()
        
        # 3. Synchronous Embedding (Instant Feedback)
        try:
            embedder = GeminiEmbeddings()
            vectors = await embedder.aembed_documents([c.text for c in chunk_records])
            for chunk, vector in zip(chunk_records, vectors):
                chunk.embedding = vector
            
            page.status = 'indexed'
            page.is_indexed = True
        except Exception as e:
            logger.error(f"Failed to embed page {page_num} for book {book_id} during update: {e}")
            # Page remains 'chunked'; batch cron will embed it on next cycle
            await books_repo.update_one(
                book_id,
                last_error=f"Page {page_num} embedding failed during manual update: {e}",
                last_updated=datetime.now(timezone.utc),
            )
    else:
        # If text is empty, just mark as indexed
        page.status = 'indexed'
        page.is_indexed = True

    # Set v2 columns based on final outcome
    if page.status == 'indexed':
        page.pipeline_step = 'embedding'
        page.milestone = 'succeeded'
    elif page.status == 'chunked':
        page.pipeline_step = 'chunking'
        page.milestone = 'succeeded'

    # Invalidate word index so the scanner re-builds it with the updated content
    await session.execute(
        text("DELETE FROM book_word_index WHERE book_id = :book_id"),
        {"book_id": book_id}
    )

    await books_repo.update_one(
        book_id,
        last_updated=datetime.now(timezone.utc),
        updated_by=current_user.email
    )
    await session.commit()

    return {"status": "page_updated", "requires_rag": True, "synchronous": page.status == 'indexed'}


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

    return {"status": "updated", "modified": True}


@router.get("/{book_id}/summary")
async def get_book_summary(
    book_id: str,
    current_user: User = Depends(require_reader),
    session: AsyncSession = Depends(get_session),
):
    """Return the AI-generated semantic summary for a book."""
    from app.db.repositories.book_summaries import BookSummariesRepository
    summaries_repo = BookSummariesRepository(session)
    summary = await summaries_repo.get_by_book_id(book_id)
    if not summary:
        raise HTTPException(status_code=404, detail=t("errors.book_not_found"))
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


