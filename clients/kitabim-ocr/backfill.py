from __future__ import annotations

import asyncio
from contextlib import contextmanager
import fcntl
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterator, Optional

import fitz

from engine.config import (
    get_configured_concurrency,
    get_configured_engine,
    get_configured_page_timeout,
    resolve_concurrency,
)
from engine.line_ends import apply_cross_page_dehyphenation
from engine.recognize import (
    OCR_ENGINE_VERSION,
    LowConfidenceOcrError,
    get_recognition_predictor,
    ocr_page_with_meta,
)
from engine.text_cleanup import is_title_cover_page, is_toc_page
from engine.workdir import PageState
from kitabim_client.api import KitabimClient

logger = logging.getLogger("kitabim_ocr_client.backfill")

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


def _append_audit_log(audit_log_path: Path, entry: dict[str, Any]) -> None:
    audit_log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(audit_log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


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
) -> dict[str, Any]:
    """Download, Surya-2.5 re-OCR, dehyphenate, and bulk-replace one PDF book."""
    t0 = time.time()
    target_engine = (engine or get_configured_engine()).strip().lower()
    target_concurrency = resolve_concurrency(
        target_engine, concurrency or get_configured_concurrency()
    )

    work_root.mkdir(parents=True, exist_ok=True)
    # Clean up any legacy random-suffix temp dirs for this book
    for stale_dir in work_root.glob(f"backfill-{book_id}-*"):
        if stale_dir.is_dir():
            shutil.rmtree(stale_dir, ignore_errors=True)

    tmp_dir = work_root / f"backfill-{book_id}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = tmp_dir / "checkpoint.jsonl"
    completed = False

    prev_sigint = signal.getsignal(signal.SIGINT)
    prev_sigterm = signal.getsignal(signal.SIGTERM)

    def _cleanup_on_signal(signum, frame):
        raise KeyboardInterrupt(f"Backfill interrupted by signal {signum}")

    try:
        try:
            signal.signal(signal.SIGINT, _cleanup_on_signal)
            signal.signal(signal.SIGTERM, _cleanup_on_signal)
        except ValueError:
            pass

        pdf_path = tmp_dir / "book.pdf"
        need_download = True
        if pdf_path.exists() and pdf_path.stat().st_size > 0:
            try:
                with fitz.open(pdf_path) as check_doc:
                    if len(check_doc) > 0:
                        need_download = False
            except Exception:
                need_download = True

        if need_download:
            part_pdf_path = tmp_dir / "book.pdf.part"
            client.download_book_pdf(book_id, part_pdf_path)
            if part_pdf_path.exists():
                part_pdf_path.replace(pdf_path)

        if not title and hasattr(client, "get_book"):
            try:
                book_meta = client.get_book(book_id) or {}
                if isinstance(book_meta, dict):
                    title = book_meta.get("title")
            except Exception:
                pass
        existing_pages = client.get_book_pages(book_id)
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
        total_pages = len(doc)
        predictor = await get_recognition_predictor(target_engine)
        sem = asyncio.Semaphore(max(1, target_concurrency))

        pages_by_num: dict[int, PageState] = {}
        fresh_page_numbers: set[int] = set()
        hyphen_ended_pages: set[int] = set()

        async def _ocr_one(page_number: int) -> None:
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
                return

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
                return

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
                return

            async with sem:
                fitz_page = doc.load_page(page_number - 1)
                try:
                    res = await ocr_page_with_meta(
                        fitz_page,
                        predictor,
                        max_parallel_pages=target_concurrency,
                        timeout=get_configured_page_timeout(),
                    )
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
                except (
                    LowConfidenceOcrError,
                    TimeoutError,
                    asyncio.TimeoutError,
                    Exception,
                ) as exc:
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

        await asyncio.gather(*(_ocr_one(p) for p in range(1, total_pages + 1)))
        doc.close()

        ordered_pages = [pages_by_num[p] for p in sorted(pages_by_num)]
        dehyphenated_pairs = apply_cross_page_dehyphenation(
            ordered_pages,
            fresh_page_numbers=fresh_page_numbers,
            hyphen_ended_pages=hyphen_ended_pages,
        )

        skipped_count = sum(
            1 for p in ordered_pages if p.skipped and p.status != "failed"
        )
        failed_count = sum(1 for p in ordered_pages if p.status == "failed")

        try:
            replace_res = client.replace_book_ocr(
                book_id,
                ordered_pages,
                ocr_version=ocr_version,
                force_overwrite_manual=force_overwrite_manual,
            )
        except TypeError:
            replace_res = client.replace_book_ocr(
                book_id, ordered_pages, ocr_version=ocr_version
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
        return audit_entry
    finally:
        try:
            signal.signal(signal.SIGINT, prev_sigint)
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
) -> list[dict[str, Any]]:
    """Run sequential headless OCR backfill with server backlog throttling and GPU lock."""
    effective_audit_log = audit_log_path or (work_root / "backfill_audit.jsonl")
    results: list[dict[str, Any]] = []

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

            batch_limit = min(100, (limit - processed) if limit is not None else 100)
            cand_resp = client.get_backfill_candidates(
                ocr_version=ocr_version, limit=max(1, batch_limit)
            )
            pending_backlog = int(
                cand_resp.get(
                    "activePipelineBookCount",
                    cand_resp.get(
                        "active_pipeline_book_count",
                        cand_resp.get(
                            "pendingIndexBooks", cand_resp.get("pending_index_books", 0)
                        ),
                    ),
                )
                or 0
            )
            candidates = cand_resp.get("candidates") or []
            remaining = [c for c in candidates if str(c.get("id")) not in seen_ids]

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

    return results
