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
    assert qm.get_queue_position("b1") is None

    # Check workdirs were marked completed
    w1 = OcrWorkDir.load(tmp_path / "b1")
    w2 = OcrWorkDir.load(tmp_path / "b2")
    w3 = OcrWorkDir.load(tmp_path / "b3")
    assert w1.queue_status == "completed"
    assert w2.queue_status == "completed"
    assert w3.queue_status == "completed"


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
