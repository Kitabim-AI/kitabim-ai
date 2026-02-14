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
from app.db.postgres import db_manager
from app.db.postgres_helpers import pg_db, pg_find, pg_count, pg_update_many
from app.db.session import get_session
from app.db.repositories.books import BooksRepository
from app.db.repositories.pages import PagesRepository
from app.models.schemas import Book, PaginatedBooks, ExtractionResult
from app.models.user import User
from app.queue import enqueue_pdf_processing
from app.services.spell_check_service import spell_check_service
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


def get_guest_filter() -> dict:
    """
    Get MongoDB query filter for guest access.
    Returns filter that only matches public, ready books.
    """
    return {
        "status": "ready",
        "$or": [
            {"visibility": "public"},
            {"visibility": {"$exists": False}},  # Legacy books default to public
        ]
    }


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
    from sqlalchemy import select, func, or_, and_
    from app.db.models import Book, Page

    skip = (page - 1) * pageSize

    # Build base query conditions
    conditions = []

    # Guest filter - guests can only see public ready books
    if current_user is None:
        conditions.extend([
            Book.status == "ready",
            or_(
                Book.visibility == "public",
                Book.visibility.is_(None)
            )
        ])

    # Category filter
    if category:
        normalized_category = generate_uyghur_regex(category)
        # Use PostgreSQL regex for array search
        conditions.append(
            func.array_to_string(Book.categories, ',').op("~*")(normalized_category)
        )
    # Search filter
    elif q:
        normalized_q = generate_uyghur_regex(q)
        search_filter = or_(
            Book.title.op("~*")(normalized_q),
            Book.author.op("~*")(normalized_q),
            func.array_to_string(Book.categories, ',').op("~*")(normalized_q)
        )
        conditions.append(search_filter)

    # Build count queries
    count_stmt = select(func.count()).select_from(Book)
    if conditions:
        count_stmt = count_stmt.where(and_(*conditions))

    total_result = await session.execute(count_stmt)
    total = total_result.scalar_one()

    # Count total ready books
    ready_count_stmt = select(func.count()).select_from(Book).where(Book.status == "ready")
    ready_result = await session.execute(ready_count_stmt)
    total_ready = ready_result.scalar_one()

    # Map sortBy parameter (camelCase) to model field (snake_case)
    sort_field_map = {
        "title": "title",
        "author": "author",
        "uploadDate": "upload_date",
        "lastUpdated": "last_updated",
        "status": "status",
    }
    sort_field = sort_field_map.get(sortBy, "title")

    def parse_date(val):
        if val is None:
            return datetime.min
        if isinstance(val, datetime):
            return val.replace(tzinfo=None) if val.tzinfo else val
        if isinstance(val, str):
            try:
                parsed = datetime.fromisoformat(val.replace("Z", "+00:00"))
                return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
            except Exception:
                return datetime.min
        return datetime.min

    if groupByWork and sortBy == "uploadDate":
        # Get ALL matching books for grouping
        stmt = select(Book)
        if conditions:
            stmt = stmt.where(and_(*conditions))

        # Sort by upload_date
        if order == -1:
            stmt = stmt.order_by(Book.upload_date.desc())
        else:
            stmt = stmt.order_by(Book.upload_date.asc())

        result = await session.execute(stmt)
        all_books_models = list(result.scalars().all())

        # Get page stats for all books
        if all_books_models:
            book_ids = [b.id for b in all_books_models]

            stats_stmt = select(
                Page.book_id,
                Page.status,
                func.count().label("count")
            ).where(
                Page.book_id.in_(book_ids)
            ).group_by(Page.book_id, Page.status)

            stats_result = await session.execute(stats_stmt)
            stats_rows = stats_result.fetchall()

            # Build stats lookup
            stats_by_book = {}
            for row in stats_rows:
                book_id = row.book_id
                status = row.status
                count = row.count
                if book_id not in stats_by_book:
                    stats_by_book[book_id] = {}
                stats_by_book[book_id][status] = count

            # Convert to dict format for grouping logic
            all_books = []
            for b in all_books_models:
                book_dict = Book.model_validate(b).model_dump()
                book_stats = stats_by_book.get(b.id, {})
                book_dict["pageStats"] = [{"_id": status, "count": cnt} for status, cnt in book_stats.items()]
                all_books.append(book_dict)
        else:
            all_books = []

        # Group by work
        work_groups = {}
        no_work_books = []
        work_priority = {}

        for b in all_books:
            stats = {s["_id"]: s["count"] for s in b.get("pageStats", [])}
            b["completedCount"] = stats.get("completed", 0)
            b["errorCount"] = stats.get("error", 0)
            if "pages" not in b:
                b["pages"] = []

            book_title = b.get("title")
            book_author = b.get("author") or ""
            book_date = parse_date(b.get("uploadDate"))

            if book_title:
                work_key = (book_title, book_author)
                if work_key not in work_groups:
                    work_groups[work_key] = []
                    work_priority[work_key] = book_date
                work_groups[work_key].append(b)
                current_priority = work_priority[work_key]
                if (order == -1 and book_date > current_priority) or (order == 1 and book_date < current_priority):
                    work_priority[work_key] = book_date
            else:
                no_work_books.append(b)

        for work_key in work_groups:
            work_groups[work_key].sort(key=lambda x: parse_date(x.get("uploadDate")), reverse=(order == -1))

        sortable_items = []
        for work_key, books_in_work in work_groups.items():
            sortable_items.append((work_priority[work_key], True, work_key, books_in_work))

        for book in no_work_books:
            sortable_items.append((parse_date(book.get("uploadDate")), False, None, [book]))

        sortable_items.sort(key=lambda x: x[0], reverse=(order == -1))

        ordered_books = []
        for _, _, _, books_in_group in sortable_items:
            ordered_books.extend(books_in_group)

        paginated_books = ordered_books[skip : skip + pageSize]
        return {
            "books": paginated_books,
            "total": total,
            "totalReady": total_ready,
            "page": page,
            "pageSize": pageSize,
        }

    # Normal pagination (no grouping)
    stmt = select(Book)
    if conditions:
        stmt = stmt.where(and_(*conditions))

    # Sort
    if hasattr(Book, sort_field):
        order_col = getattr(Book, sort_field)
        if order == -1:
            stmt = stmt.order_by(order_col.desc())
        else:
            stmt = stmt.order_by(order_col.asc())

    # Paginate
    stmt = stmt.offset(skip).limit(pageSize)

    result = await session.execute(stmt)
    books_models = list(result.scalars().all())

    # Get page stats
    if books_models:
        book_ids = [b.id for b in books_models]

        stats_stmt = select(
            Page.book_id,
            Page.status,
            func.count().label("count")
        ).where(
            Page.book_id.in_(book_ids)
        ).group_by(Page.book_id, Page.status)

        stats_result = await session.execute(stats_stmt)
        stats_rows = stats_result.fetchall()

        # Build stats lookup
        stats_by_book = {}
        for row in stats_rows:
            book_id = row.book_id
            status = row.status
            count = row.count
            if book_id not in stats_by_book:
                stats_by_book[book_id] = {}
            stats_by_book[book_id][status] = count

        # Convert to dict and attach stats
        books_list = []
        for b in books_models:
            book_dict = Book.model_validate(b).model_dump()
            book_stats = stats_by_book.get(b.id, {})
            book_dict["completedCount"] = book_stats.get("completed", 0)
            book_dict["errorCount"] = book_stats.get("error", 0)
            if "pages" not in book_dict:
                book_dict["pages"] = []
            books_list.append(book_dict)
    else:
        books_list = []

    return {
        "books": books_list,
        "total": total,
        "totalReady": total_ready,
        "page": page,
        "pageSize": pageSize,
    }


@router.get("/random-proverb")
async def get_random_proverb():
    """
    Fetch a random proverb from the proverbs collection containing specific keywords.
    """
    db = pg_db
    keywords = ["كىتاب", "بىلىم", "ئەقىل", "پاراسەت"]
    
    # Create regexes for keywords to handle multi-encoding
    regex_queries = []
    for k in keywords:
        pattern = generate_uyghur_regex(k)
        regex_queries.append({"text": {"$regex": pattern, "$options": "i"}})
    
    query = {"$or": regex_queries}

    # PostgreSQL: Get count then random offset
    from app.db.postgres import db_manager as pg_manager
    import random

    total = await db.proverbs.count_documents(query)
    if total > 0:
        # Get a random record using OFFSET
        random_offset = random.randint(0, total - 1)
        proverbs = await db.proverbs.find(query).skip(random_offset).limit(1).to_list(1)
    else:
        proverbs = []
    
    if proverbs:
        p = proverbs[0]
        return {
            "text": p.get("text"),
            "volume": p.get("volume"),
            "pageNumber": p.get("pageNumber")
        }
    
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
    initial_pages: int = 10000,
    current_user: Optional[User] = Depends(get_current_user_optional),
    session: AsyncSession = Depends(get_session),
):
    """Get a single book by ID with SQLAlchemy"""
    books_repo = BooksRepository(session)
    pages_repo = PagesRepository(session)

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

    # Get pages using repository
    pages_list = await pages_repo.find_by_book(book_id, limit=initial_pages)

    # Convert SQLAlchemy models to Pydantic (automatic camelCase conversion)
    book_response = Book.model_validate(book_model)

    # Add pages as ExtractionResult models
    book_response.pages = [ExtractionResult.model_validate(p) for p in pages_list]

    return book_response


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

    return {"content": full_text.strip()}


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
        file_path = settings.uploads_dir / f"{book_id}.pdf"
        os.replace(temp_path, file_path)
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
        ocr_provider=None,
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
            ocr_provider=provider,
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
        ocr_provider=provider,
        last_updated=datetime.utcnow(),
        updated_by=current_user.email,
    )

    # Reset failed pages to pending using raw SQL for embedding = NULL
    await session.execute(
        text("""
            UPDATE pages
            SET status = 'pending',
                text = '',
                error = NULL,
                is_verified = FALSE,
                embedding = NULL,
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

    # Reset embeddings for all completed pages using raw SQL
    # Note: Page model doesn't have is_indexed field, so we just clear embeddings
    await session.execute(
        text("""
            UPDATE pages
            SET embedding = NULL, last_updated = NOW(), updated_by = :updated_by
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

    # Update page using raw SQL for embedding = NULL
    await session.execute(
        text("""
            UPDATE pages
            SET status = 'pending',
                text = '',
                is_verified = FALSE,
                embedding = NULL,
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

    # Update page using raw SQL for embedding = NULL
    await session.execute(
        text("""
            UPDATE pages
            SET text = :text,
                status = 'completed',
                is_verified = TRUE,
                embedding = NULL,
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

    # Remove fields we don't want to update
    book_update.pop("upload_date", None)
    book_update.pop("uploadDate", None)
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

                # Use raw SQL to update page with embedding = NULL
                await session.execute(
                    text("""
                        UPDATE pages
                        SET text = COALESCE(:text, text),
                            status = COALESCE(:status, status),
                            is_verified = COALESCE(:is_verified, is_verified),
                            embedding = NULL,
                            last_updated = :last_updated,
                            updated_by = :updated_by
                        WHERE book_id = :book_id AND page_number = :page_number
                    """),
                    {
                        "book_id": book_id,
                        "page_number": page_number,
                        "text": result.get("text"),
                        "status": result.get("status"),
                        "is_verified": result.get("isVerified") or result.get("is_verified"),
                        "last_updated": datetime.utcnow(),
                        "updated_by": current_user.email,
                    }
                )

    # Remove pages from book_update
    book_update.pop("pages", None)

    # Convert camelCase to snake_case for model fields
    if "lastUpdated" in book_update:
        book_update.pop("lastUpdated")
    if "updatedBy" in book_update:
        book_update.pop("updatedBy")

    # Update book
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

    # Delete PDF file
    file_path = settings.uploads_dir / f"{book_id}.pdf"
    if file_path.exists():
        os.remove(file_path)

    # Delete associated pages first
    await pages_repo.delete_by_book(book_id)

    # Delete book
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

    books_repo = BooksRepository(session)

    # Find book by title (case-insensitive search)
    stmt = select(Book).where(Book.title.ilike(f"%{title}%"))
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
    """Check spelling for all pages with SQLAlchemy"""
    # Note: spell_check_service still uses pg_db internally
    # TODO: Update spell_check_service to use SQLAlchemy
    db = pg_db
    try:
        results = await spell_check_service.check_book(book_id, db)
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
    """Apply spelling corrections with SQLAlchemy"""
    # Note: spell_check_service still uses pg_db internally
    # TODO: Update spell_check_service to use SQLAlchemy
    db = pg_db
    corrections = payload.get("corrections", [])
    if not corrections:
        raise HTTPException(status_code=400, detail="No corrections provided")

    try:
        success = await spell_check_service.apply_corrections(book_id, page_num, corrections, db, user_email=current_user.email)
        if success:
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
