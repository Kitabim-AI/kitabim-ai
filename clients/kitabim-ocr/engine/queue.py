from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Awaitable, Callable, Optional

from engine.workdir import OcrWorkDir

logger = logging.getLogger(__name__)


class BookQueueManager:
    """Sequential background queue processor for local OCR jobs.

    Ensures strictly one book undergoes OCR processing at any given time,
    preventing heavy GPU/CPU and memory exhaustion, while allowing multiple
    books to be queued up in FIFO order.
    """

    def __init__(
        self,
        work_root: Path,
        runner: Callable[[OcrWorkDir], Awaitable[None]],
    ) -> None:
        self.work_root = work_root
        self.runner = runner
        self._queue: list[str] = []
        self._active_session_id: Optional[str] = None
        self._worker_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    @property
    def active_session_id(self) -> Optional[str]:
        return self._active_session_id

    @property
    def queued_session_ids(self) -> list[str]:
        return list(self._queue)

    def get_queue_position(self, session_id: str) -> Optional[int]:
        """Returns 0 if actively running, 1..N if waiting in queue, or None if neither."""
        if self._active_session_id == session_id:
            return 0
        try:
            return self._queue.index(session_id) + 1
        except ValueError:
            return None

    async def enqueue(self, session_id: str) -> tuple[int, bool]:
        """Enqueues a session ID for OCR processing.

        Returns:
            tuple of (position, is_active):
            position: 0 if active, 1..N if in queue
            is_active: True if currently processing
        """
        async with self._lock:
            if self._active_session_id == session_id:
                return (0, True)

            session_dir = self.work_root / session_id
            if (session_dir / "book.json").exists():
                try:
                    workdir = OcrWorkDir.load(session_dir)
                    workdir.queue_status = "queued"
                    if not workdir.queued_at:
                        workdir.queued_at = time.time()
                    workdir.save()
                except Exception as exc:
                    logger.warning(
                        "Failed to update queue_status for %s: %s", session_id, exc
                    )

            if session_id not in self._queue:
                self._queue.append(session_id)

            self._ensure_worker_running()

        # Yield to allow the worker loop to pick up the item if idle
        await asyncio.sleep(0)

        async with self._lock:
            if self._active_session_id == session_id:
                return (0, True)
            try:
                pos = self._queue.index(session_id) + 1
                return (pos, False)
            except ValueError:
                return (0, self._active_session_id == session_id)

    def cancel(self, session_id: str) -> bool:
        """Removes a session from the queue if not yet active."""
        if session_id in self._queue:
            self._queue.remove(session_id)
            session_dir = self.work_root / session_id
            if (session_dir / "book.json").exists():
                try:
                    workdir = OcrWorkDir.load(session_dir)
                    workdir.queue_status = "idle"
                    workdir.save()
                except Exception:
                    pass
            return True
        return False

    def _ensure_worker_running(self) -> None:
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._process_loop())

    async def _process_loop(self) -> None:
        while True:
            session_id: Optional[str] = None
            async with self._lock:
                if not self._queue:
                    self._active_session_id = None
                    break
                session_id = self._queue.pop(0)
                self._active_session_id = session_id

            session_dir = self.work_root / session_id
            if not (session_dir / "book.json").exists():
                async with self._lock:
                    self._active_session_id = None
                continue

            workdir: Optional[OcrWorkDir] = None
            try:
                workdir = OcrWorkDir.load(session_dir)
                workdir.queue_status = "processing"
                workdir.save()

                await self.runner(workdir)

                workdir = OcrWorkDir.load(session_dir)
                workdir.queue_status = "completed"
                workdir.save()
            except Exception as exc:
                logger.error("Error processing OCR for %s: %s", session_id, exc)
                if workdir is not None:
                    try:
                        workdir = OcrWorkDir.load(session_dir)
                        workdir.queue_status = "failed"
                        workdir.save()
                    except Exception:
                        pass
            finally:
                async with self._lock:
                    if self._active_session_id == session_id:
                        self._active_session_id = None

    async def wait_all(self) -> None:
        """Waits until all currently queued and active items have finished processing."""
        while True:
            task = self._worker_task
            if task and not task.done():
                await task
            else:
                async with self._lock:
                    if not self._queue and self._active_session_id is None:
                        break
                    self._ensure_worker_running()
            await asyncio.sleep(0.01)

    async def recover_queue(self) -> int:
        """Scans work_root on startup for queued or interrupted sessions."""
        if not self.work_root.exists():
            return 0

        pending: list[tuple[float, str]] = []
        for item in self.work_root.iterdir():
            if not item.is_dir() or not (item / "book.json").exists():
                continue
            try:
                wd = OcrWorkDir.load(item)
                if wd.queue_status in ("queued", "processing"):
                    q_time = wd.queued_at or item.stat().st_mtime
                    pending.append((q_time, item.name))
            except Exception:
                continue

        # Sort by queued_at ascending (FIFO)
        pending.sort(key=lambda x: x[0])
        count = 0
        for _, s_id in pending:
            await self.enqueue(s_id)
            count += 1
        return count
