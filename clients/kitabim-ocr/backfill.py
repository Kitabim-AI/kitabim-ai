from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, contextmanager
import fcntl
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Iterator, Optional, Sequence

import fitz

from engine.config import (
    get_configured_concurrency,
    get_configured_engine,
    get_configured_page_timeout,
    is_wave_batching_enabled,
    resolve_concurrency,
)
from engine.line_ends import apply_cross_page_dehyphenation
from engine.recognize import (
    OCR_ENGINE_VERSION,
    LowConfidenceOcrError,
    PageOcrResult,
    get_recognition_predictor,
    ocr_page_with_meta,
    ocr_prepared_wave_with_meta,
    prepare_page_wave_async,
)
from engine.text_cleanup import is_title_cover_page, is_toc_page
from engine.workdir import PageState
from kitabim_client.api import KitabimClient

logger = logging.getLogger("kitabim_ocr_client.backfill")

_BOOK_DOWNLOAD_LOCKS: dict[tuple[int, str], asyncio.Lock] = {}


def _get_book_download_lock(book_id: str) -> asyncio.Lock:
    key = (id(asyncio.get_running_loop()), book_id)
    lock = _BOOK_DOWNLOAD_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _BOOK_DOWNLOAD_LOCKS[key] = lock
    return lock


def _is_valid_pdf(pdf_path: Path) -> bool:
    if not pdf_path.exists() or pdf_path.stat().st_size <= 0:
        return False
    try:
        with fitz.open(pdf_path) as check_doc:
            return len(check_doc) > 0
    except Exception:
        return False


async def prefetch_book_assets_async(
    book_id: str, client: KitabimClient, work_root: Path
) -> bool:
    """Speculatively download next book's PDF and existing pages while GPU is busy."""
    try:
        async with _get_book_download_lock(book_id):
            tmp_dir = work_root / f"backfill-{book_id}"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            pdf_path = tmp_dir / "book.pdf"
            pages_cache_path = tmp_dir / "existing_pages.json"

            async def _dl_pdf() -> None:
                if _is_valid_pdf(pdf_path):
                    return
                part_pdf = tmp_dir / "book.pdf.part"
                await asyncio.to_thread(client.download_book_pdf, book_id, part_pdf)
                if part_pdf.exists():
                    part_pdf.replace(pdf_path)

            async def _dl_pages() -> None:
                if pages_cache_path.exists() and pages_cache_path.stat().st_size > 0:
                    return
                pages = await asyncio.to_thread(client.get_book_pages, book_id)
                if isinstance(pages, list):
                    part_pages = tmp_dir / "existing_pages.json.part"
                    part_pages.write_text(
                        json.dumps(pages, ensure_ascii=False), encoding="utf-8"
                    )
                    part_pages.replace(pages_cache_path)

            await asyncio.gather(_dl_pdf(), _dl_pages())
            return True
    except Exception as exc:
        logger.debug("Prefetch skipped for book=%s: %s", book_id, exc)
        return False


def cleanup_unstarted_prefetch_dir(book_id: str, work_root: Path) -> None:
    """Remove a prefetched temp dir if the run stopped before OCR started on ``book_id``."""
    tmp_dir = work_root / f"backfill-{book_id}"
    if tmp_dir.is_dir() and not (tmp_dir / "checkpoint.jsonl").exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)


_PIPE_TOC_ROW_RE = re.compile(
    r"^\|\s*(?:[^|]+?\s*\|\s*[0-9\u0660-\u0669\u06F0-\u06F9]{1,4}|[0-9\u0660-\u0669\u06F0-\u06F9]{1,4}\s*\|\s*[^|]+?)\s*\|?\s*$"
)


def has_formatted_pipe_toc(text: str, min_rows: int = 2) -> bool:
    """Return True if ``text`` already contains at least ``min_rows`` pipe-table ToC rows."""
    if not text:
        return False
    count = 0
    for line in text.split("\n"):
        if _PIPE_TOC_ROW_RE.match(line.strip()):
            count += 1
            if count >= min_rows:
                return True
    return False


_ACTIVE_CAFFEINATE_PROC: Optional[subprocess.Popen] = None


@contextmanager
def prevent_macos_sleep() -> Iterator[Optional[subprocess.Popen]]:
    """Prevent macOS idle/display/system sleep via ``caffeinate`` while backfill runs."""
    global _ACTIVE_CAFFEINATE_PROC
    if _ACTIVE_CAFFEINATE_PROC is not None and _ACTIVE_CAFFEINATE_PROC.poll() is None:
        yield _ACTIVE_CAFFEINATE_PROC
        return

    proc: Optional[subprocess.Popen] = None
    if sys.platform == "darwin" and shutil.which("caffeinate"):
        try:
            proc = subprocess.Popen(
                ["caffeinate", "-dims", "-w", str(os.getpid())],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _ACTIVE_CAFFEINATE_PROC = proc
            logger.info(
                "Started macOS caffeinate (pid=%s) to prevent sleep during backfill",
                proc.pid,
            )
        except Exception as exc:
            logger.warning("Failed to start caffeinate: %s", exc)
    try:
        yield proc
    finally:
        if proc is not None:
            _ACTIVE_CAFFEINATE_PROC = None
            if proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=2.0)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass


_IN_PROCESS_GPU_ASYNC_LOCK: Optional[asyncio.Lock] = None
_IN_PROCESS_GPU_LOCK_LOOP: Optional[asyncio.AbstractEventLoop] = None


def _get_in_process_gpu_lock() -> asyncio.Lock:
    global _IN_PROCESS_GPU_ASYNC_LOCK, _IN_PROCESS_GPU_LOCK_LOOP
    loop = asyncio.get_running_loop()
    if _IN_PROCESS_GPU_ASYNC_LOCK is None or _IN_PROCESS_GPU_LOCK_LOOP is not loop:
        _IN_PROCESS_GPU_ASYNC_LOCK = asyncio.Lock()
        _IN_PROCESS_GPU_LOCK_LOOP = loop
    return _IN_PROCESS_GPU_ASYNC_LOCK


@contextmanager
def acquire_surya_gpu_lock(work_root: Path) -> Iterator[Path]:
    """Acquire process-exclusive flock on ``$KITABIM_WORK_DIR/.surya_gpu.lock``."""
    work_root.mkdir(parents=True, exist_ok=True)
    lock_path = work_root / ".surya_gpu.lock"
    f = open(lock_path, "a+", encoding="utf-8")
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        with prevent_macos_sleep():
            yield lock_path
    finally:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        f.close()


@asynccontextmanager
async def acquire_surya_gpu_lock_async(
    work_root: Path, poll_interval: float = 0.05
) -> AsyncIterator[Path]:
    """Async-safe GPU lock combining an in-process asyncio.Lock with non-blocking flock."""
    async_lock = _get_in_process_gpu_lock()
    async with async_lock:
        work_root.mkdir(parents=True, exist_ok=True)
        lock_path = work_root / ".surya_gpu.lock"
        f = open(lock_path, "a+", encoding="utf-8")
        try:
            while True:
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    await asyncio.sleep(poll_interval)
            with prevent_macos_sleep():
                yield lock_path
        finally:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            f.close()


def _append_audit_log(audit_log_path: Path, entry: dict[str, Any]) -> None:
    audit_log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(audit_log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_backfill_audit_log(
    audit_log_path: Path, limit: int = 50
) -> list[dict[str, Any]]:
    """Read recent backfill audit entries (newest first) from a JSONL file."""
    if not audit_log_path.exists():
        return []
    entries: list[dict[str, Any]] = []
    try:
        with open(audit_log_path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    if isinstance(row, dict):
                        entries.append(row)
                except json.JSONDecodeError:
                    continue
    except Exception as exc:
        logger.warning("Failed to read audit log %s: %s", audit_log_path, exc)
        return []
    entries.reverse()
    return entries[: max(1, limit)]


SKIPPED_BOOKS_FILENAME = "skipped_books.json"


def _skipped_books_path(work_root: Path) -> Path:
    return work_root / SKIPPED_BOOKS_FILENAME


def load_skipped_books(work_root: Path) -> dict[str, dict[str, Any]]:
    """Load locally skipped book entries from ``$KITABIM_WORK_DIR/skipped_books.json``.

    Supports both the structured dict format ``{book_id: {...}}`` and a plain
    JSON list of string book IDs (or entry dicts) if edited manually.
    """
    path = _skipped_books_path(work_root)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to read skipped books file %s: %s", path, exc)
        return {}

    normalized: dict[str, dict[str, Any]] = {}
    if isinstance(raw, dict):
        items = raw.get("books") if isinstance(raw.get("books"), (dict, list)) else raw
        if isinstance(items, dict):
            for k, val in items.items():
                bid = str(k).strip()
                if not bid:
                    continue
                if isinstance(val, dict):
                    entry = dict(val)
                    entry["book_id"] = str(entry.get("book_id") or bid).strip()
                    normalized[entry["book_id"]] = entry
                else:
                    normalized[bid] = {"book_id": bid}
            return normalized
        raw = items

    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                bid = item.strip()
                if bid:
                    normalized[bid] = {"book_id": bid}
            elif isinstance(item, dict):
                bid = str(item.get("book_id") or item.get("id") or "").strip()
                if bid:
                    entry = dict(item)
                    entry["book_id"] = bid
                    normalized[bid] = entry
    return normalized


def list_skipped_books(work_root: Path) -> list[dict[str, Any]]:
    """Return locally skipped books sorted newest-skipped first."""
    skipped_map = load_skipped_books(work_root)
    entries = list(skipped_map.values())
    entries.sort(
        key=lambda e: (float(e.get("skipped_at") or 0.0), str(e.get("book_id") or "")),
        reverse=True,
    )
    return entries


def save_skipped_books(work_root: Path, skipped: dict[str, dict[str, Any]]) -> None:
    """Atomically write ``$KITABIM_WORK_DIR/skipped_books.json``."""
    work_root.mkdir(parents=True, exist_ok=True)
    path = _skipped_books_path(work_root)
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(
        json.dumps(skipped, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(path)


def skip_book_locally(
    work_root: Path,
    book_id: str,
    *,
    title: Optional[str] = None,
    author: Optional[str] = None,
    total_pages: Optional[int] = None,
    upload_date: Optional[str] = None,
    reason: Optional[str] = None,
) -> dict[str, Any]:
    """Persistently skip ``book_id`` locally without modifying any server data."""
    bid = str(book_id).strip()
    if not bid:
        raise ValueError("book_id must not be empty")
    skipped = load_skipped_books(work_root)
    existing = skipped.get(bid) or {}
    entry: dict[str, Any] = {
        "book_id": bid,
        "title": title if title is not None else existing.get("title"),
        "author": author if author is not None else existing.get("author"),
        "total_pages": (
            int(total_pages) if total_pages is not None else existing.get("total_pages")
        ),
        "upload_date": (
            upload_date if upload_date is not None else existing.get("upload_date")
        ),
        "reason": reason if reason is not None else existing.get("reason"),
        "skipped_at": existing.get("skipped_at") or time.time(),
    }
    skipped[bid] = entry
    save_skipped_books(work_root, skipped)
    cleanup_unstarted_prefetch_dir(bid, work_root)
    return entry


def unskip_book_locally(work_root: Path, book_id: str) -> bool:
    """Remove ``book_id`` from the local skip list. Returns True if it was present."""
    bid = str(book_id).strip()
    if not bid:
        return False
    skipped = load_skipped_books(work_root)
    if bid not in skipped:
        return False
    del skipped[bid]
    save_skipped_books(work_root, skipped)
    return True


DEFAULT_CHECKPOINT_OVERLAP_PAGES = 2


def _load_page_checkpoint(
    checkpoint_path: Path,
    ocr_version: str,
    overlap_pages: int = DEFAULT_CHECKPOINT_OVERLAP_PAGES,
) -> dict[int, dict[str, Any]]:
    """Load per-page OCR results from a local JSONL checkpoint file.

    Drops the trailing ``overlap_pages`` checkpointed entries (and any truncated
    tail line) and rewrites the checkpoint file cleanly so pages right at the
    crash boundary are always re-OCR'd fresh.
    """
    ordered_by_pno: dict[int, dict[str, Any]] = {}
    if not checkpoint_path.exists():
        return ordered_by_pno
    try:
        with open(checkpoint_path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict) or row.get("ocr_version") != ocr_version:
                    continue
                pno = row.get("page_number")
                if (
                    isinstance(pno, int)
                    and pno >= 1
                    and isinstance(row.get("text"), str)
                ):
                    ordered_by_pno[pno] = row
    except Exception as exc:
        logger.warning("Failed to read checkpoint %s: %s", checkpoint_path, exc)
        return {}

    if not ordered_by_pno:
        return {}

    rows = list(ordered_by_pno.values())
    if overlap_pages > 0:
        rows = rows[:-overlap_pages] if len(rows) > overlap_pages else []

    kept: dict[int, dict[str, Any]] = {int(r["page_number"]): r for r in rows}
    try:
        tmp_ckpt = checkpoint_path.with_suffix(".jsonl.tmp")
        with open(tmp_ckpt, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
        tmp_ckpt.replace(checkpoint_path)
    except Exception as exc:
        logger.warning("Failed to compact checkpoint %s: %s", checkpoint_path, exc)

    return kept


def _append_page_checkpoint(checkpoint_path: Path, row: dict[str, Any]) -> None:
    """Append a single OCR'd page record to the local JSONL checkpoint file."""
    with open(checkpoint_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()


async def backfill_single_book(
    book_id: str,
    client: KitabimClient,
    work_root: Path,
    *,
    title: Optional[str] = None,
    engine: Optional[str] = None,
    concurrency: Optional[int] = None,
    audit_log_path: Optional[Path] = None,
    ocr_version: str = OCR_ENGINE_VERSION,
    checkpoint_overlap: int = DEFAULT_CHECKPOINT_OVERLAP_PAGES,
    force_overwrite_manual: bool = True,
    on_progress: Optional[Callable[[dict[str, Any]], None]] = None,
    pages_sink: Optional[dict[int, PageState]] = None,
    user_edits: Optional[dict[int, dict[str, Any]]] = None,
    install_signal_handlers: bool = True,
) -> dict[str, Any]:
    """Download, Surya-2.5 re-OCR, dehyphenate, and bulk-replace one PDF book."""
    t0 = time.time()
    target_engine = (engine or get_configured_engine()).strip().lower()
    target_concurrency = resolve_concurrency(
        target_engine, concurrency or get_configured_concurrency()
    )

    def _emit(event: dict[str, Any]) -> None:
        if on_progress is not None:
            try:
                on_progress(event)
            except Exception:
                pass

    work_root.mkdir(parents=True, exist_ok=True)
    # Clean up any legacy random-suffix temp dirs for this book
    for stale_dir in work_root.glob(f"backfill-{book_id}-*"):
        if stale_dir.is_dir():
            shutil.rmtree(stale_dir, ignore_errors=True)

    tmp_dir = work_root / f"backfill-{book_id}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = tmp_dir / "checkpoint.jsonl"
    completed = False

    prev_sigint = signal.getsignal(signal.SIGINT) if install_signal_handlers else None
    prev_sigterm = signal.getsignal(signal.SIGTERM) if install_signal_handlers else None

    def _cleanup_on_signal(signum, frame):
        raise KeyboardInterrupt(f"Backfill interrupted by signal {signum}")

    try:
        if install_signal_handlers:
            try:
                signal.signal(signal.SIGINT, _cleanup_on_signal)
                signal.signal(signal.SIGTERM, _cleanup_on_signal)
            except ValueError:
                pass

        _emit({"phase": "downloading", "book_id": book_id, "title": title})

        pdf_path = tmp_dir / "book.pdf"
        pages_cache_path = tmp_dir / "existing_pages.json"

        async with _get_book_download_lock(book_id):

            async def _ensure_pdf() -> None:
                if _is_valid_pdf(pdf_path):
                    return
                part_pdf_path = tmp_dir / "book.pdf.part"
                await asyncio.to_thread(
                    client.download_book_pdf, book_id, part_pdf_path
                )
                if part_pdf_path.exists():
                    part_pdf_path.replace(pdf_path)

            async def _ensure_title() -> Optional[str]:
                if title or not hasattr(client, "get_book"):
                    return title
                try:
                    book_meta = await asyncio.to_thread(client.get_book, book_id) or {}
                    if isinstance(book_meta, dict):
                        return book_meta.get("title")
                except Exception:
                    pass
                return title

            async def _ensure_existing_pages() -> list[dict[str, Any]]:
                if pages_cache_path.exists() and pages_cache_path.stat().st_size > 0:
                    try:
                        cached = json.loads(
                            pages_cache_path.read_text(encoding="utf-8")
                        )
                        pages_cache_path.unlink(missing_ok=True)
                        if isinstance(cached, list):
                            return cached
                    except Exception:
                        pages_cache_path.unlink(missing_ok=True)
                return await asyncio.to_thread(client.get_book_pages, book_id)

            _, resolved_title, existing_pages = await asyncio.gather(
                _ensure_pdf(), _ensure_title(), _ensure_existing_pages()
            )
            if resolved_title:
                title = resolved_title

        existing_by_num = {
            int(p["pageNumber"]): p for p in existing_pages if "pageNumber" in p
        }

        checkpoint_by_num = _load_page_checkpoint(
            checkpoint_path, ocr_version, overlap_pages=checkpoint_overlap
        )
        if checkpoint_by_num:
            logger.info(
                "Resuming book=%s from local checkpoint (%d pages reused, overlap=%d)",
                book_id,
                len(checkpoint_by_num),
                checkpoint_overlap,
            )

        doc = fitz.open(pdf_path)
        doc_lock = threading.Lock()
        total_pages = len(doc)
        predictor = await get_recognition_predictor(target_engine)

        pages_by_num: dict[int, PageState] = (
            pages_sink if pages_sink is not None else {}
        )
        pages_by_num.clear()
        for pno in range(1, total_pages + 1):
            ex = existing_by_num.get(pno, {})
            pages_by_num[pno] = PageState(
                page_number=pno,
                text=ex.get("text") or "",
                is_toc=bool(ex.get("isToc")),
                confidence=0.0,
                status="pending",
            )

        _emit(
            {
                "phase": "ocr",
                "book_id": book_id,
                "title": title,
                "total_pages": total_pages,
                "pdf_path": str(pdf_path),
            }
        )

        fresh_page_numbers: set[int] = set()
        hyphen_ended_pages: set[int] = set()
        todo_pages: list[int] = []

        for page_number in range(1, total_pages + 1):
            existing = existing_by_num.get(page_number, {})
            is_toc = bool(existing.get("isToc"))
            existing_text = existing.get("text") or ""

            # 1. Skip page 1 cover or front-matter calligraphic inner-title pages unless marked as ToC
            if not is_toc and (
                page_number == 1
                or is_title_cover_page(existing_text, title, page_number, is_toc=False)
            ):
                pages_by_num[page_number] = PageState(
                    page_number=page_number,
                    text=existing_text,
                    is_toc=False,
                    confidence=1.0,
                    status="skipped",
                    skipped=True,
                )
                _emit(
                    {
                        "phase": "ocr",
                        "page_number": page_number,
                        "status": "skipped",
                    }
                )
                continue

            # 2. Skip existing ToC pages that already have >= 2 formatted pipe rows
            if is_toc and has_formatted_pipe_toc(existing_text, min_rows=2):
                pages_by_num[page_number] = PageState(
                    page_number=page_number,
                    text=existing_text,
                    is_toc=True,
                    confidence=1.0,
                    status="skipped",
                    skipped=True,
                )
                _emit(
                    {
                        "phase": "ocr",
                        "page_number": page_number,
                        "status": "skipped",
                    }
                )
                continue

            # 3. Reuse checkpointed OCR result if available from an interrupted run
            ckpt = checkpoint_by_num.get(page_number)
            if ckpt is not None:
                ended_hyphen = bool(ckpt.get("ended_with_hyphen", False))
                pages_by_num[page_number] = PageState(
                    page_number=page_number,
                    text=ckpt["text"],
                    is_toc=bool(ckpt.get("is_toc", is_toc)),
                    confidence=1.0,
                    status="ocrd",
                    detected_page_number=ckpt.get("detected_page_number"),
                    skipped=False,
                    ended_with_hyphen=ended_hyphen,
                )
                fresh_page_numbers.add(page_number)
                if ended_hyphen:
                    hyphen_ended_pages.add(page_number)
                _emit(
                    {
                        "phase": "ocr",
                        "page_number": page_number,
                        "status": "ocrd",
                    }
                )
                continue

            todo_pages.append(page_number)

        def _record_page_success(page_number: int, res: PageOcrResult) -> None:
            existing = existing_by_num.get(page_number, {})
            is_toc = bool(existing.get("isToc"))
            detected_toc = is_toc or is_toc_page(res.text)
            pages_by_num[page_number] = PageState(
                page_number=page_number,
                text=res.text,
                is_toc=detected_toc,
                confidence=1.0,
                status="ocrd",
                detected_page_number=res.detected_page_number,
                skipped=False,
                ended_with_hyphen=res.ended_with_hyphen,
            )
            fresh_page_numbers.add(page_number)
            if res.ended_with_hyphen:
                hyphen_ended_pages.add(page_number)
            _append_page_checkpoint(
                checkpoint_path,
                {
                    "ocr_version": ocr_version,
                    "page_number": page_number,
                    "text": res.text,
                    "is_toc": detected_toc,
                    "detected_page_number": res.detected_page_number,
                    "ended_with_hyphen": res.ended_with_hyphen,
                },
            )
            _emit(
                {
                    "phase": "ocr",
                    "page_number": page_number,
                    "status": "ocrd",
                }
            )

        def _record_page_failure(page_number: int, exc: BaseException) -> None:
            existing = existing_by_num.get(page_number, {})
            is_toc = bool(existing.get("isToc"))
            existing_text = existing.get("text") or ""
            logger.warning(
                "Backfill OCR failed on book=%s page=%s (marking skipped=True): %s",
                book_id,
                page_number,
                exc,
            )
            pages_by_num[page_number] = PageState(
                page_number=page_number,
                text=existing_text,
                is_toc=is_toc,
                confidence=0.0,
                status="failed",
                error=str(exc),
                skipped=True,
            )
            _emit(
                {
                    "phase": "ocr",
                    "page_number": page_number,
                    "status": "failed",
                    "error": str(exc),
                }
            )

        use_wave_batching = is_wave_batching_enabled()
        next_prep_task: Optional[asyncio.Task] = None
        try:
            if todo_pages and use_wave_batching:
                wave_size = max(1, target_concurrency)
                waves = [
                    todo_pages[i : i + wave_size]
                    for i in range(0, len(todo_pages), wave_size)
                ]
                page_timeout = get_configured_page_timeout()
                next_prep_task = asyncio.create_task(
                    prepare_page_wave_async(
                        doc,
                        waves[0],
                        doc_lock,
                        max_parallel_pages=target_concurrency,
                    )
                )
                for w_idx, wave_pnos in enumerate(waves):
                    assert next_prep_task is not None
                    prepared_wave = await next_prep_task
                    next_prep_task = (
                        asyncio.create_task(
                            prepare_page_wave_async(
                                doc,
                                waves[w_idx + 1],
                                doc_lock,
                                max_parallel_pages=target_concurrency,
                            )
                        )
                        if (w_idx + 1) < len(waves)
                        else None
                    )
                    for pno in wave_pnos:
                        ex = existing_by_num.get(pno, {})
                        pages_by_num[pno] = PageState(
                            page_number=pno,
                            text=ex.get("text") or "",
                            is_toc=bool(ex.get("isToc")),
                            confidence=0.0,
                            status="processing",
                        )
                        _emit(
                            {
                                "phase": "ocr",
                                "page_number": pno,
                                "status": "processing",
                            }
                        )
                    outcomes = await ocr_prepared_wave_with_meta(
                        doc,
                        prepared_wave,
                        predictor,
                        doc_lock=doc_lock,
                        timeout=page_timeout,
                        max_parallel_pages=target_concurrency,
                    )
                    for pno in wave_pnos:
                        outcome = outcomes.get(pno)
                        if isinstance(outcome, PageOcrResult):
                            _record_page_success(pno, outcome)
                        else:
                            _record_page_failure(
                                pno,
                                outcome
                                if isinstance(outcome, BaseException)
                                else RuntimeError("Missing wave OCR result"),
                            )
            elif todo_pages:
                sem = asyncio.Semaphore(max(1, target_concurrency))
                page_timeout = get_configured_page_timeout()

                async def _ocr_one(page_number: int) -> None:
                    existing = existing_by_num.get(page_number, {})
                    is_toc = bool(existing.get("isToc"))
                    existing_text = existing.get("text") or ""
                    async with sem:
                        pages_by_num[page_number] = PageState(
                            page_number=page_number,
                            text=existing_text,
                            is_toc=is_toc,
                            confidence=0.0,
                            status="processing",
                        )
                        _emit(
                            {
                                "phase": "ocr",
                                "page_number": page_number,
                                "status": "processing",
                            }
                        )
                        with doc_lock:
                            fitz_page = doc.load_page(page_number - 1)
                        try:
                            res = await ocr_page_with_meta(
                                fitz_page,
                                predictor,
                                max_parallel_pages=target_concurrency,
                                timeout=page_timeout,
                            )
                            _record_page_success(page_number, res)
                        except (
                            LowConfidenceOcrError,
                            TimeoutError,
                            asyncio.TimeoutError,
                            Exception,
                        ) as exc:
                            _record_page_failure(page_number, exc)

                await asyncio.gather(*(_ocr_one(p) for p in todo_pages))
        finally:
            if next_prep_task is not None and not next_prep_task.done():
                next_prep_task.cancel()
                try:
                    await next_prep_task
                except (asyncio.CancelledError, Exception):
                    pass
            doc.close()

        ordered_pages = [pages_by_num[p] for p in sorted(pages_by_num)]
        dehyphenated_pairs = apply_cross_page_dehyphenation(
            ordered_pages,
            fresh_page_numbers=fresh_page_numbers,
            hyphen_ended_pages=hyphen_ended_pages,
        )

        if user_edits:
            for p in ordered_pages:
                edit = user_edits.get(p.page_number)
                if edit:
                    if "text" in edit and edit["text"] is not None:
                        p.text = str(edit["text"])
                    if "is_toc" in edit and edit["is_toc"] is not None:
                        p.is_toc = bool(edit["is_toc"])
                    p.skipped = False
                    if p.status in ("skipped", "failed"):
                        p.status = "ocrd"
                        fresh_page_numbers.add(p.page_number)

        skipped_count = sum(
            1 for p in ordered_pages if p.skipped and p.status != "failed"
        )
        failed_count = sum(1 for p in ordered_pages if p.status == "failed")

        _emit({"phase": "submitting", "book_id": book_id, "title": title})

        try:
            replace_res = await asyncio.to_thread(
                client.replace_book_ocr,
                book_id,
                ordered_pages,
                ocr_version=ocr_version,
                force_overwrite_manual=force_overwrite_manual,
            )
        except TypeError:
            replace_res = await asyncio.to_thread(
                client.replace_book_ocr,
                book_id,
                ordered_pages,
                ocr_version=ocr_version,
            )
        completed = failed_count == 0
        elapsed_s = round(time.time() - t0, 2)

        audit_entry = {
            "book_id": book_id,
            "title": title,
            "ocr_version": ocr_version,
            "total_pages": total_pages,
            "ocrd_pages": len(fresh_page_numbers),
            "resumed_pages": len(checkpoint_by_num),
            "skipped_pages": skipped_count,
            "failed_pages": failed_count,
            "dehyphenated_pairs": dehyphenated_pairs,
            "pages_updated": replace_res.get(
                "pagesUpdated", replace_res.get("pages_updated", 0)
            ),
            "pages_unchanged": replace_res.get(
                "pagesUnchanged", replace_res.get("pages_unchanged", 0)
            ),
            "backup_uri": replace_res.get("backupUri", replace_res.get("backup_uri")),
            "elapsed_s": elapsed_s,
            "timestamp": time.time(),
        }
        if audit_log_path is not None:
            _append_audit_log(audit_log_path, audit_entry)
        _emit({"phase": "completed", "book_id": book_id, "audit_entry": audit_entry})
        return audit_entry
    finally:
        if install_signal_handlers:
            try:
                if prev_sigint is not None:
                    signal.signal(signal.SIGINT, prev_sigint)
                if prev_sigterm is not None:
                    signal.signal(signal.SIGTERM, prev_sigterm)
            except ValueError:
                pass
        if completed:
            shutil.rmtree(tmp_dir, ignore_errors=True)


async def run_backfill(
    client: KitabimClient,
    work_root: Path,
    *,
    book_id: Optional[str] = None,
    limit: Optional[int] = None,
    max_server_backlog: int = 3,
    dry_run: bool = False,
    engine: Optional[str] = None,
    concurrency: Optional[int] = None,
    audit_log_path: Optional[Path] = None,
    poll_interval: float = 30.0,
    ocr_version: str = OCR_ENGINE_VERSION,
    skip_book_ids: Optional[Sequence[str]] = None,
) -> list[dict[str, Any]]:
    """Run sequential headless OCR backfill with server backlog throttling and GPU lock."""
    effective_audit_log = audit_log_path or (work_root / "backfill_audit.jsonl")
    results: list[dict[str, Any]] = []
    extra_skipped: set[str] = {
        str(bid).strip() for bid in (skip_book_ids or []) if str(bid).strip()
    }

    if book_id:
        if dry_run:
            book_meta = client.get_book(book_id) or {"id": book_id}
            entry = {
                "book_id": book_id,
                "title": book_meta.get("title"),
                "total_pages": book_meta.get("totalPages") or book_meta.get("pages"),
                "dry_run": True,
            }
            print(
                f"[DRY-RUN] Would backfill book {book_id} ({entry.get('title') or '—'})"
            )
            return [entry]

        with acquire_surya_gpu_lock(work_root):
            res = await backfill_single_book(
                book_id,
                client,
                work_root,
                engine=engine,
                concurrency=concurrency,
                audit_log_path=effective_audit_log,
                ocr_version=ocr_version,
            )
            results.append(res)
        return results

    processed = 0
    seen_ids: set[str] = set()

    with prevent_macos_sleep():
        while True:
            if limit is not None and processed >= limit:
                break

            skipped_ids = set(load_skipped_books(work_root).keys()) | extra_skipped
            excluded_ids = seen_ids | skipped_ids
            desired_batch = ((limit - processed) if limit is not None else 100) + len(
                excluded_ids
            )
            batch_limit = min(500, max(1, desired_batch))
            cand_resp = client.get_backfill_candidates(
                ocr_version=ocr_version, limit=batch_limit
            )
            pending_backlog = int(
                cand_resp.get(
                    "pendingIndexBooks", cand_resp.get("pending_index_books", 0)
                )
                or 0
            )
            candidates = cand_resp.get("candidates") or []
            remaining = [c for c in candidates if str(c.get("id")) not in excluded_ids]

            if not remaining:
                break

            if dry_run:
                for c in remaining:
                    if limit is not None and len(results) >= limit:
                        break
                    cid = str(c["id"])
                    seen_ids.add(cid)
                    entry = {
                        "book_id": cid,
                        "title": c.get("title"),
                        "total_pages": c.get("totalPages") or c.get("total_pages"),
                        "ocr_version": c.get("ocrVersion") or c.get("ocr_version"),
                        "dry_run": True,
                    }
                    print(
                        f"[DRY-RUN] Candidate #{len(results) + 1}: {cid} "
                        f"({entry['title'] or '—'}, {entry['total_pages']} pages)"
                    )
                    results.append(entry)
                break

            if pending_backlog >= max_server_backlog:
                logger.info(
                    "Server pending index backlog (%s) >= max_server_backlog (%s); sleeping %.1fs",
                    pending_backlog,
                    max_server_backlog,
                    poll_interval,
                )
                await asyncio.sleep(poll_interval)
                continue

            target = remaining[0]
            target_id = str(target["id"])
            seen_ids.add(target_id)

            next_prefetch_id: Optional[str] = None
            prefetch_task: Optional[asyncio.Task] = None
            can_prefetch_next = len(remaining) >= 2 and (
                limit is None or (processed + 1) < limit
            )
            if can_prefetch_next:
                next_prefetch_id = str(remaining[1]["id"])
                prefetch_task = asyncio.create_task(
                    prefetch_book_assets_async(next_prefetch_id, client, work_root)
                )

            try:
                with acquire_surya_gpu_lock(work_root):
                    res = await backfill_single_book(
                        target_id,
                        client,
                        work_root,
                        title=target.get("title"),
                        engine=engine,
                        concurrency=concurrency,
                        audit_log_path=effective_audit_log,
                        ocr_version=ocr_version,
                    )
                    results.append(res)
                    processed += 1
                if prefetch_task is not None:
                    await prefetch_task
            except BaseException:
                if prefetch_task is not None and not prefetch_task.done():
                    prefetch_task.cancel()
                    try:
                        await prefetch_task
                    except (asyncio.CancelledError, Exception):
                        pass
                if next_prefetch_id and next_prefetch_id not in seen_ids:
                    cleanup_unstarted_prefetch_dir(next_prefetch_id, work_root)
                raise

    return results
