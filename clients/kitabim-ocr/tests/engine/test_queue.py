import asyncio
from pathlib import Path

import pytest

from engine.queue import BookQueueManager
from engine.workdir import OcrWorkDir


@pytest.mark.asyncio
async def test_queue_processes_items_sequentially(tmp_path: Path):
    processed = []

    async def mock_runner(workdir: OcrWorkDir):
        processed.append(workdir.root.name)
        await asyncio.sleep(0.05)

    pdf = tmp_path / "mock.pdf"
    pdf.write_bytes(b"%PDF-1.4 mock")

    OcrWorkDir.create(tmp_path / "b1", source_pdf=pdf, total_pages=1)
    OcrWorkDir.create(tmp_path / "b2", source_pdf=pdf, total_pages=1)
    OcrWorkDir.create(tmp_path / "b3", source_pdf=pdf, total_pages=1)

    qm = BookQueueManager(work_root=tmp_path, runner=mock_runner)

    pos1, active1 = await qm.enqueue("b1")
    assert active1 is True
    assert pos1 == 0
    assert qm.active_session_id == "b1"

    pos2, active2 = await qm.enqueue("b2")
    assert active2 is False
    assert pos2 == 1

    pos3, active3 = await qm.enqueue("b3")
    assert active3 is False
    assert pos3 == 2

    # Verify queue positions
    assert qm.get_queue_position("b1") == 0
    assert qm.get_queue_position("b2") == 1
    assert qm.get_queue_position("b3") == 2

    # Wait for queue worker to finish all jobs
    await qm.wait_all()
    assert processed == ["b1", "b2", "b3"]
    assert qm.active_session_id is None
    assert qm.active_workdir is None
    assert qm.get_queue_position("b1") is None

    # Check workdirs were marked completed
    w1 = OcrWorkDir.load(tmp_path / "b1")
    w2 = OcrWorkDir.load(tmp_path / "b2")
    w3 = OcrWorkDir.load(tmp_path / "b3")
    assert w1.queue_status == "completed"
    assert w2.queue_status == "completed"
    assert w3.queue_status == "completed"


@pytest.mark.asyncio
async def test_active_workdir_exposes_the_live_instance_the_runner_mutates(
    tmp_path: Path,
):
    seen_workdir = None
    resume_processing = asyncio.Event()

    async def mock_runner(workdir: OcrWorkDir):
        nonlocal seen_workdir
        seen_workdir = workdir
        await resume_processing.wait()

    pdf = tmp_path / "mock.pdf"
    pdf.write_bytes(b"%PDF-1.4 mock")
    OcrWorkDir.create(tmp_path / "b1", source_pdf=pdf, total_pages=1)

    qm = BookQueueManager(work_root=tmp_path, runner=mock_runner)
    await qm.enqueue("b1")
    await asyncio.sleep(0.01)

    # Callers hydrating an active session from active_workdir must get back
    # the exact same object the runner is mutating, not a second, independent
    # OcrWorkDir loaded fresh from disk — otherwise a write through the
    # rehydrated copy could clobber pages the runner has already saved.
    assert qm.active_workdir is seen_workdir

    resume_processing.set()
    await qm.wait_all()
    assert qm.active_workdir is None


@pytest.mark.asyncio
async def test_queue_handles_runner_failure_gracefully(tmp_path: Path):
    failed = []

    async def failing_runner(workdir: OcrWorkDir):
        if workdir.root.name == "bad":
            raise RuntimeError("OCR Engine exploded")
        failed.append(workdir.root.name)

    pdf = tmp_path / "mock.pdf"
    pdf.write_bytes(b"%PDF-1.4 mock")

    OcrWorkDir.create(tmp_path / "bad", source_pdf=pdf, total_pages=1)
    OcrWorkDir.create(tmp_path / "good", source_pdf=pdf, total_pages=1)

    qm = BookQueueManager(work_root=tmp_path, runner=failing_runner)

    await qm.enqueue("bad")
    await qm.enqueue("good")
    await qm.wait_all()

    bad_wd = OcrWorkDir.load(tmp_path / "bad")
    good_wd = OcrWorkDir.load(tmp_path / "good")

    assert bad_wd.queue_status == "failed"
    assert good_wd.queue_status == "completed"
    assert failed == ["good"]


@pytest.mark.asyncio
async def test_queue_cancel(tmp_path: Path):
    async def slow_runner(workdir: OcrWorkDir):
        await asyncio.sleep(0.2)

    pdf = tmp_path / "mock.pdf"
    pdf.write_bytes(b"%PDF-1.4 mock")

    OcrWorkDir.create(tmp_path / "b1", source_pdf=pdf, total_pages=1)
    OcrWorkDir.create(tmp_path / "b2", source_pdf=pdf, total_pages=1)

    qm = BookQueueManager(work_root=tmp_path, runner=slow_runner)

    await qm.enqueue("b1")
    await qm.enqueue("b2")

    assert qm.cancel("b2") is True
    assert qm.get_queue_position("b2") is None

    b2_wd = OcrWorkDir.load(tmp_path / "b2")
    assert b2_wd.queue_status == "idle"

    await qm.wait_all()


@pytest.mark.asyncio
async def test_queue_startup_recovery(tmp_path: Path):
    processed = []

    async def mock_runner(workdir: OcrWorkDir):
        processed.append(workdir.root.name)

    pdf = tmp_path / "mock.pdf"
    pdf.write_bytes(b"%PDF-1.4 mock")

    # Simulate interrupted processing session and a queued session
    OcrWorkDir.create(
        tmp_path / "rec1",
        source_pdf=pdf,
        total_pages=1,
        queue_status="processing",
        queued_at=100.0,
    )
    OcrWorkDir.create(
        tmp_path / "rec2",
        source_pdf=pdf,
        total_pages=1,
        queue_status="queued",
        queued_at=200.0,
    )
    OcrWorkDir.create(
        tmp_path / "done",
        source_pdf=pdf,
        total_pages=1,
        queue_status="completed",
        queued_at=50.0,
    )

    qm = BookQueueManager(work_root=tmp_path, runner=mock_runner)
    recovered = await qm.recover_queue()

    assert recovered == 2
    await qm.wait_all()
    assert processed == ["rec1", "rec2"]


def test_reset_interrupted_sessions_resets_status_without_starting_runner(
    tmp_path: Path,
):
    pdf = tmp_path / "mock.pdf"
    pdf.write_bytes(b"%PDF-1.4 mock")

    w_proc1 = OcrWorkDir.create(
        tmp_path / "proc1",
        source_pdf=pdf,
        total_pages=2,
        queue_status="processing",
    )
    w_proc1.set_page(
        1, text="midway", is_toc=False, confidence=0.5, status="processing"
    )
    w_proc1.save()
    OcrWorkDir.create(
        tmp_path / "queued1",
        source_pdf=pdf,
        total_pages=2,
        queue_status="queued",
    )
    w_done = OcrWorkDir.create(
        tmp_path / "done1",
        source_pdf=pdf,
        total_pages=1,
        queue_status="processing",
    )
    w_done.set_page(1, text="done", is_toc=False, confidence=1.0, status="ocrd")
    w_done.save()

    runner_called = False

    async def mock_runner(wd):
        nonlocal runner_called
        runner_called = True

    qm = BookQueueManager(work_root=tmp_path, runner=mock_runner)
    reset_count = qm.reset_interrupted_sessions()

    assert reset_count == 3
    assert not runner_called
    assert qm.active_session_id is None
    assert qm.queued_session_ids == []

    # Check statuses on disk
    loaded_proc1 = OcrWorkDir.load(tmp_path / "proc1")
    assert loaded_proc1.queue_status == "idle"
    assert loaded_proc1.get_page(1).status == "pending"
    assert OcrWorkDir.load(tmp_path / "queued1").queue_status == "idle"
    assert OcrWorkDir.load(tmp_path / "done1").queue_status == "completed"


async def test_queue_process_loop_preserves_concurrent_edits(tmp_path: Path):
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    session_dir = tmp_path / "b1"
    wd = OcrWorkDir.create(session_dir, source_pdf=pdf, total_pages=2)
    wd.set_page(1, text="initial", is_toc=False, confidence=1.0, status="ocrd")
    wd.save()

    async def mock_runner(active_wd):
        # Simulate user editing page 1 while runner is running
        with active_wd.save_lock:
            active_wd.set_page(
                1,
                text="edited during runner",
                is_toc=True,
                confidence=1.0,
                status="reviewed",
            )
            active_wd.save()

    qm = BookQueueManager(work_root=tmp_path, runner=mock_runner)
    await qm.enqueue("b1")
    await qm.wait_all()

    loaded = OcrWorkDir.load(session_dir)
    assert loaded.queue_status == "completed"
    assert loaded.get_page(1).text == "edited during runner"
    assert loaded.get_page(1).is_toc is True
    assert loaded.get_page(1).status == "reviewed"
