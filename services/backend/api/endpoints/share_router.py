"""Share endpoints — return OG-tagged HTML for social media crawlers."""

from __future__ import annotations

import html
import logging
import re
from urllib.parse import quote as url_quote

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.repositories.books_repository import BooksRepository
from app.db.repositories.pages_repository import PagesRepository
from app.db.session import get_session
from app.utils.observability import log_json

logger = logging.getLogger(__name__)
router = APIRouter()

_SCRAPER_AGENTS = (
    "facebookexternalhit",
    "facebookcatalog",
    "twitterbot",
    "linkedinbot",
    "whatsapp",
    "slackbot",
    "telegrambot",
    "discordbot",
    "googlebot",
    "applebot",
)

_REF_LINK_RE = re.compile(r"\[([^\]]+)\]\(ref:[^)]+\)")
_REF_PAREN_RE = re.compile(r"\(ref:[^)]+\)")
_BOOK_ID_RE = re.compile(r"\s*\(?BookID:\s*[a-zA-Z0-9-]+\)?", re.IGNORECASE)


def _clean_share_text(text: str) -> str:
    """Mirrors the frontend's cleanShareText (apps/frontend/src/utils/shareText.ts)."""
    if not text:
        return ""
    cleaned = _REF_LINK_RE.sub(r"\1", text)
    cleaned = _REF_PAREN_RE.sub("", cleaned)
    cleaned = _BOOK_ID_RE.sub("", cleaned)
    return cleaned.strip()


def _truncate_snippet(text: str, max_len: int = 300) -> str:
    """Same cut-to-last-space-plus-ellipsis pattern as
    PagesRepository.search_content_pages (pages_repository.py)."""
    if len(text) <= max_len:
        return text
    cut = text[:max_len]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut + "..."


@router.get("/book/{book_id}")
async def share_book(
    book_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    safe_id = html.escape(book_id)
    base_url = settings.frontend_base_url
    deep_link = f"{base_url}/books/{safe_id}"
    share_url = f"{base_url}/api/share/book/{safe_id}"
    cover_url = f"{base_url}/api/covers/{safe_id}.jpg"

    user_agent = request.headers.get("user-agent", "").lower()
    is_scraper = any(bot in user_agent for bot in _SCRAPER_AGENTS)

    if not is_scraper:
        return RedirectResponse(url=deep_link, status_code=302)

    try:
        repo = BooksRepository(session)
        book = await repo.get(book_id)
    except Exception as exc:
        log_json(
            logger,
            logging.WARNING,
            "Share endpoint DB error",
            book_id=book_id,
            error=str(exc),
        )
        return RedirectResponse(url=deep_link, status_code=302)

    if not book or book.status != "ready" or book.visibility == "private":
        return RedirectResponse(url=deep_link, status_code=302)

    title = html.escape(book.title or "")
    author = html.escape(book.author or "")
    description = f"{title} — {author}".strip(" —") if author else title

    log_json(
        logger,
        logging.INFO,
        "Book share page served to scraper",
        book_id=book_id,
        agent=user_agent[:80],
    )

    page_html = f"""<!DOCTYPE html>
<html lang="ug" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta property="og:type" content="book">
  <meta property="og:title" content="{title}">
  <meta property="og:description" content="{description}">
  <meta property="og:image" content="{cover_url}">
  <meta property="og:url" content="{share_url}">
  <meta property="og:site_name" content="كىتابىم">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{title}">
  <meta name="twitter:description" content="{description}">
  <meta name="twitter:image" content="{cover_url}">
  <title>{title}</title>
</head>
<body></body>
</html>"""

    return HTMLResponse(content=page_html)


@router.get("/qa")
async def share_qa(
    request: Request,
    q: str = Query(..., max_length=400),
    a: str = Query(..., max_length=1000),
    book_id: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    base_url = settings.frontend_base_url

    # Collapse all whitespace (including \n from markdown) into single spaces
    # so the text is safe to embed inside an HTML content="..." attribute.
    safe_q = html.escape(" ".join(q.split()))
    safe_a = html.escape(" ".join(a.split()))

    # Build the canonical share URL (what scrapers will see as og:url)
    share_url = str(request.url)

    # Browser redirect target
    if book_id:
        redirect_url = f"{base_url}/books/{html.escape(book_id)}"
    else:
        redirect_url = f"{base_url}/chat"

    user_agent = request.headers.get("user-agent", "").lower()
    is_scraper = any(bot in user_agent for bot in _SCRAPER_AGENTS)

    if not is_scraper:
        return RedirectResponse(url=redirect_url, status_code=302)

    # Resolve book cover for OG image if book_id provided
    og_image = ""
    if book_id:
        safe_book_id = html.escape(book_id)
        try:
            repo = BooksRepository(session)
            book = await repo.get(book_id)
            if book and book.status == "ready":
                og_image = f"{base_url}/api/covers/{safe_book_id}.jpg"
        except Exception as exc:
            log_json(
                logger,
                logging.WARNING,
                "QA share: book lookup failed",
                book_id=book_id,
                error=str(exc),
            )

    image_meta = (
        f'<meta property="og:image" content="{og_image}">\n  <meta name="twitter:image" content="{og_image}">'
        if og_image
        else ""
    )
    card_type = "summary_large_image" if og_image else "summary"

    log_json(
        logger, logging.INFO, "QA share page served to scraper", agent=user_agent[:80]
    )

    page_html = f"""<!DOCTYPE html>
<html lang="ug" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta property="og:type" content="article">
  <meta property="og:title" content="{safe_q}">
  <meta property="og:description" content="{safe_a}">
  {image_meta}
  <meta property="og:url" content="{html.escape(share_url)}">
  <meta property="og:site_name" content="كىتابىم">
  <meta name="twitter:card" content="{card_type}">
  <meta name="twitter:title" content="{safe_q}">
  <meta name="twitter:description" content="{safe_a}">
  <title>{safe_q}</title>
</head>
<body></body>
</html>"""

    return HTMLResponse(content=page_html)


@router.get("/page/{book_id}/{page_number}")
async def share_page(
    book_id: str,
    page_number: int,
    request: Request,
    quote: str | None = Query(None, max_length=500),
    session: AsyncSession = Depends(get_session),
):
    safe_id = html.escape(book_id)
    base_url = settings.frontend_base_url
    deep_link = f"{base_url}/books/{safe_id}/{page_number}"
    if quote:
        deep_link = f"{deep_link}?quote={url_quote(quote)}"
    share_url = str(request.url)

    user_agent = request.headers.get("user-agent", "").lower()
    is_scraper = any(bot in user_agent for bot in _SCRAPER_AGENTS)

    if not is_scraper:
        return RedirectResponse(url=deep_link, status_code=302)

    try:
        books_repo = BooksRepository(session)
        book = await books_repo.get(book_id)
    except Exception as exc:
        log_json(
            logger,
            logging.WARNING,
            "Page share endpoint DB error",
            book_id=book_id,
            page_number=page_number,
            error=str(exc),
        )
        return RedirectResponse(url=deep_link, status_code=302)

    if not book or book.status != "ready" or book.visibility == "private":
        return RedirectResponse(url=deep_link, status_code=302)

    try:
        pages_repo = PagesRepository(session)
        page = await pages_repo.find_one(book_id, page_number)
    except Exception as exc:
        log_json(
            logger,
            logging.WARNING,
            "Page share endpoint page lookup failed",
            book_id=book_id,
            page_number=page_number,
            error=str(exc),
        )
        return RedirectResponse(url=deep_link, status_code=302)

    if not page:
        return RedirectResponse(url=deep_link, status_code=302)

    title = html.escape(book.title or "")
    page_label = f"{page_number}-بەت"
    og_title = f"{title} — {page_label}" if title else page_label

    if quote:
        description = html.escape(" ".join(quote.split()))
    else:
        cleaned = _clean_share_text(page.text or "")
        snippet = _truncate_snippet(cleaned)
        description = html.escape(" ".join(snippet.split()))

    cover_url = f"{base_url}/api/covers/{safe_id}.jpg"

    log_json(
        logger,
        logging.INFO,
        "Page share page served to scraper",
        book_id=book_id,
        page_number=page_number,
        agent=user_agent[:80],
    )

    page_html = f"""<!DOCTYPE html>
<html lang="ug" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta property="og:type" content="article">
  <meta property="og:title" content="{og_title}">
  <meta property="og:description" content="{description}">
  <meta property="og:image" content="{cover_url}">
  <meta property="og:url" content="{html.escape(share_url)}">
  <meta property="og:site_name" content="كىتابىم">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{og_title}">
  <meta name="twitter:description" content="{description}">
  <meta name="twitter:image" content="{cover_url}">
  <title>{og_title}</title>
</head>
<body></body>
</html>"""

    return HTMLResponse(content=page_html)
