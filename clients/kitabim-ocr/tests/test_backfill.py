from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import fitz
import pytest

import backfill
from engine.recognize import LowConfidenceOcrError, PageOcrResult


def _create_sample_pdf(path: Path, num_pages: int = 4) -> None:
    doc = fitz.open()
    for _ in range(num_pages):
        doc.new_page(width=200, height=200)
    doc.save(path)
    doc.close()


def _make_wave_ocr_mock(per_page_fn):
    """Wrap a per-page async OCR fake into ``ocr_prepared_wave_with_meta`` shape
    so backfill tests exercise the default wave-batching production code path."""

    async def _fake_wave(doc, prepared_items, predictor, *, doc_lock, **kwargs):
        out = {}
        for item in prepared_items:
            with doc_lock:
                fitz_page = doc.load_page(item.page_number - 1)
            try:
                out[item.page_number] = await per_page_fn(
                    fitz_page, predictor, **kwargs
                )
            except Exception as exc:
                out[item.page_number] = exc
        return out

    return _fake_wave


def test_has_formatted_pipe_toc():
    assert (
        backfill.has_formatted_pipe_toc(
            "| بىرىنچى باب | 3 |\n| ئىككىنچى باب | 15 |", min_rows=2
        )
        is True
    )
    assert backfill.has_formatted_pipe_toc("| بىرىنچى باب | 3 |", min_rows=2) is False
    assert (
        backfill.has_formatted_pipe_toc(
            "1. بىرىنچى باب ....... 3\n2. ئىككىنچى باب ....... 15"
        )
        is False
    )


@pytest.mark.asyncio
async def test_backfill_single_book_skips_cover_and_formatted_toc_and_dehyphenates(
    tmp_path: Path,
):
    client = MagicMock()

    def _fake_download(book_id: str, dest: Path):
        _create_sample_pdf(dest, num_pages=4)
        return dest

    client.download_book_pdf.side_effect = _fake_download
    client.get_book_pages.return_value = [
        {"pageNumber": 1, "text": "Cover text", "isToc": False},
        {
            "pageNumber": 2,
            "text": "مۇندەرىجە\n| باب بىر | 1 |\n| باب ئىككى | 10 |",
            "isToc": True,
        },
        {"pageNumber": 3, "text": "Old p3", "isToc": False},
        {"pageNumber": 4, "text": "Old p4", "isToc": False},
    ]
    client.replace_book_ocr.return_value = {
        "pagesUpdated": 2,
        "pagesUnchanged": 2,
        "backupUri": "gs://bucket/backup.json.gz",
    }

    async def _fake_ocr_with_meta(fitz_page, predictor, **kwargs):
        pno = fitz_page.number + 1
        if pno == 3:
            return PageOcrResult(
                text="# باب بىر\n\nبۇ تەتقى-",
                detected_page_number=1,
                ended_with_hyphen=True,
            )
        if pno == 4:
            return PageOcrResult(
                text="قاتلار مۇھىم.",
                detected_page_number=2,
                ended_with_hyphen=False,
            )
        raise AssertionError(f"Unexpected OCR call for page {pno}")

    audit_log = tmp_path / "backfill_audit.jsonl"
    with (
        patch("backfill.get_recognition_predictor", new=AsyncMock(return_value="pred")),
        patch(
            "backfill.ocr_prepared_wave_with_meta",
            side_effect=_make_wave_ocr_mock(_fake_ocr_with_meta),
        ),
    ):
        entry = await backfill.backfill_single_book(
            "book-1",
            client,
            tmp_path,
            title="Test Book",
            audit_log_path=audit_log,
        )

    assert entry["ocrd_pages"] == 2
    assert entry["skipped_pages"] == 2
    assert entry["failed_pages"] == 0
    assert entry["dehyphenated_pairs"] == 1

    # Verify temporary directory was cleaned up
    assert not list(tmp_path.glob("backfill-book-1*"))

    # Verify replace_book_ocr payload
    sent_pages = client.replace_book_ocr.call_args.args[1]
    assert len(sent_pages) == 4
    assert sent_pages[0].skipped is True  # page 1 cover
    assert sent_pages[1].skipped is True  # page 2 pipe ToC
    assert sent_pages[2].skipped is False
    assert sent_pages[2].text == "# باب بىر\n\nبۇ تەتقىقاتلار"
    assert sent_pages[2].detected_page_number == 1
    assert sent_pages[3].text == "مۇھىم."
    assert sent_pages[3].detected_page_number == 2

    # Verify audit log written
    logged = json.loads(audit_log.read_text(encoding="utf-8").strip())
    assert logged["book_id"] == "book-1"
    assert logged["backup_uri"] == "gs://bucket/backup.json.gz"


@pytest.mark.asyncio
async def test_backfill_single_book_reocrs_unformatted_toc_and_marks_failed_pages_skipped(
    tmp_path: Path,
):
    client = MagicMock()
    client.download_book_pdf.side_effect = lambda b, dest: _create_sample_pdf(
        dest, num_pages=3
    )
    client.get_book_pages.return_value = [
        {"pageNumber": 1, "text": "Cover", "isToc": False},
        {"pageNumber": 2, "text": "مۇندەرىجە\nباب بىر .... 1", "isToc": True},
        {"pageNumber": 3, "text": "Existing body page 3", "isToc": False},
    ]
    client.replace_book_ocr.return_value = {"pagesUpdated": 1, "pagesUnchanged": 2}

    async def _fake_ocr(fitz_page, predictor, **kwargs):
        pno = fitz_page.number + 1
        if pno == 2:
            return PageOcrResult(
                text="## مۇندەرىجە\n\n| باب بىر | 1 |\n| باب ئىككى | 5 |",
                detected_page_number=None,
                ended_with_hyphen=False,
            )
        raise LowConfidenceOcrError("blurry scan")

    with (
        patch("backfill.get_recognition_predictor", new=AsyncMock(return_value="pred")),
        patch(
            "backfill.ocr_prepared_wave_with_meta",
            side_effect=_make_wave_ocr_mock(_fake_ocr),
        ),
    ):
        entry = await backfill.backfill_single_book("book-2", client, tmp_path)

    assert entry["ocrd_pages"] == 1
    assert entry["failed_pages"] == 1
    sent_pages = client.replace_book_ocr.call_args.args[1]
    # Unformatted ToC page 2 was re-OCR'd
    assert sent_pages[1].skipped is False
    assert "| باب بىر | 1 |" in sent_pages[1].text
    # Failed page 3 fell back to skipped=True preserving existing text
    assert sent_pages[2].skipped is True
    assert sent_pages[2].text == "Existing body page 3"


@pytest.mark.asyncio
async def test_run_backfill_throttles_on_server_backlog_and_supports_dry_run(
    tmp_path: Path,
):
    client = MagicMock()
    client.get_backfill_candidates.side_effect = [
        {
            "candidates": [{"id": "b1", "title": "Book 1", "totalPages": 10}],
            "pending_index_books": 3,
        },
        {
            "candidates": [{"id": "b1", "title": "Book 1", "totalPages": 10}],
            "pendingIndexBooks": 1,
        },
        {"candidates": [], "pending_index_books": 0},
    ]

    with (
        patch(
            "backfill.backfill_single_book",
            new=AsyncMock(return_value={"book_id": "b1", "ocrd_pages": 9}),
        ) as mock_single,
        patch("asyncio.sleep", new=AsyncMock()) as mock_sleep,
    ):
        results = await backfill.run_backfill(
            client,
            tmp_path,
            max_server_backlog=3,
            poll_interval=0.01,
        )

    assert len(results) == 1
    assert results[0]["book_id"] == "b1"
    mock_sleep.assert_awaited_once_with(0.01)
    mock_single.assert_awaited_once()

    # Dry run mode should never invoke backfill_single_book
    client.get_backfill_candidates.side_effect = [
        {
            "candidates": [{"id": "b2", "title": "Book 2", "totalPages": 20}],
            "pending_index_books": 0,
        }
    ]
    with patch("backfill.backfill_single_book", new=AsyncMock()) as mock_dry_single:
        dry_res = await backfill.run_backfill(client, tmp_path, dry_run=True)

    assert len(dry_res) == 1
    assert dry_res[0]["dry_run"] is True
    mock_dry_single.assert_not_awaited()


@pytest.mark.asyncio
async def test_backfill_single_book_skips_secondary_calligraphy_title_pages(
    tmp_path: Path,
):
    client = MagicMock()
    client.download_book_pdf.side_effect = lambda b, dest: _create_sample_pdf(
        dest, num_pages=4
    )
    client.get_book.return_value = {"id": "b-cover", "title": "باياۋاندىكى گۈلخان"}
    client.get_book_pages.return_value = [
        {"pageNumber": 1, "text": "Outer cover", "isToc": False},
        {
            "pageNumber": 2,
            "text": "غۇلام ئۆمەر\n\n# باياۋاندىكى گۈلخان\n\n(تارىخىي رومان)\n\nشىنجاڭ خەلق نەشرىياتى",
            "isToc": False,
        },
        {
            "pageNumber": 3,
            "text": "# باياۋاندىكى گۈلخان\n\nبىرىنچى باب مەزمۇنى ئۇزۇن ئابزاس تېكىستى بولۇپ، بۇ بەتتە ھېكايىنىڭ ئاساسىي ۋەقەلىكى باشلىنىدۇ ۋە داۋاملىشىدۇ.",
            "isToc": False,
        },
        {"pageNumber": 4, "text": "Body page 4", "isToc": False},
    ]
    client.replace_book_ocr.return_value = {"pagesUpdated": 2, "pagesUnchanged": 2}

    async def _fake_ocr(fitz_page, predictor, **kwargs):
        pno = fitz_page.number + 1
        if pno in (1, 2):
            raise AssertionError(
                f"Page {pno} is a cover/title page and must be skipped"
            )
        return PageOcrResult(
            text=f"New Surya text {pno}",
            detected_page_number=pno - 2,
            ended_with_hyphen=False,
        )

    with (
        patch("backfill.get_recognition_predictor", new=AsyncMock(return_value="pred")),
        patch(
            "backfill.ocr_prepared_wave_with_meta",
            side_effect=_make_wave_ocr_mock(_fake_ocr),
        ),
    ):
        entry = await backfill.backfill_single_book("b-cover", client, tmp_path)

    assert entry["ocrd_pages"] == 2
    assert entry["skipped_pages"] == 2
    sent_pages = client.replace_book_ocr.call_args.args[1]
    assert sent_pages[0].skipped is True  # page 1 outer cover
    assert sent_pages[1].skipped is True  # page 2 inner calligraphy title page
    assert sent_pages[2].skipped is False  # page 3 has long body prose -> OCR'd
    assert sent_pages[3].skipped is False


@pytest.mark.asyncio
async def test_backfill_single_book_resumes_from_local_checkpoint_with_overlap(
    tmp_path: Path,
):
    client = MagicMock()
    client.download_book_pdf.side_effect = lambda b, dest: _create_sample_pdf(
        dest, num_pages=6
    )
    client.get_book_pages.return_value = [
        {"pageNumber": p, "text": f"Old page {p}", "isToc": False} for p in range(1, 7)
    ]
    client.replace_book_ocr.return_value = {"pagesUpdated": 5, "pagesUnchanged": 1}

    class _SimulatedPowerLoss(BaseException):
        pass

    first_run_ocrd: list[int] = []

    async def _crash_on_page_6(fitz_page, predictor, **kwargs):
        pno = fitz_page.number + 1
        if pno == 6:
            raise _SimulatedPowerLoss("Simulated laptop battery death on page 6")
        first_run_ocrd.append(pno)
        if pno == 3:
            return PageOcrResult(
                text="بۇ تەتقى-",
                detected_page_number=2,
                ended_with_hyphen=True,
            )
        if pno == 4:
            return PageOcrResult(
                text="قاتلار داۋامى.",
                detected_page_number=3,
                ended_with_hyphen=False,
            )
        return PageOcrResult(
            text=f"Surya text {pno}",
            detected_page_number=pno - 1,
            ended_with_hyphen=False,
        )

    with (
        patch("backfill.get_recognition_predictor", new=AsyncMock(return_value="pred")),
        patch(
            "backfill.ocr_prepared_wave_with_meta",
            side_effect=_make_wave_ocr_mock(_crash_on_page_6),
        ),
    ):
        with pytest.raises(_SimulatedPowerLoss):
            await backfill.backfill_single_book(
                "b-ckpt", client, tmp_path, concurrency=1, checkpoint_overlap=2
            )

    # Pages 2, 3, 4, 5 were OCR'd and checkpointed before page 6 crashed; workdir still exists
    assert first_run_ocrd == [2, 3, 4, 5]
    ckpt_dir = tmp_path / "backfill-b-ckpt"
    assert (ckpt_dir / "book.pdf").exists()
    assert (ckpt_dir / "checkpoint.jsonl").exists()
    client.replace_book_ocr.assert_not_called()

    # Append a simulated half-written JSON line at the end of checkpoint.jsonl
    with open(ckpt_dir / "checkpoint.jsonl", "a", encoding="utf-8") as f:
        f.write('{"ocr_version": "surya-2.5-v2", "page_number": 6, "text": "trunc')

    second_run_ocrd: list[int] = []

    async def _succeed_on_resume(fitz_page, predictor, **kwargs):
        pno = fitz_page.number + 1
        second_run_ocrd.append(pno)
        if pno == 4:
            return PageOcrResult(
                text="قاتلار داۋامى.",
                detected_page_number=3,
                ended_with_hyphen=False,
            )
        return PageOcrResult(
            text=f"Surya text {pno}",
            detected_page_number=pno - 1,
            ended_with_hyphen=False,
        )

    with (
        patch("backfill.get_recognition_predictor", new=AsyncMock(return_value="pred")),
        patch(
            "backfill.ocr_prepared_wave_with_meta",
            side_effect=_make_wave_ocr_mock(_succeed_on_resume),
        ),
    ):
        entry = await backfill.backfill_single_book(
            "b-ckpt", client, tmp_path, concurrency=1, checkpoint_overlap=2
        )

    # PDF was NOT re-downloaded on resume
    assert client.download_book_pdf.call_count == 1
    # Pages 2 & 3 were loaded from checkpoint; pages 4 & 5 were re-OCR'd (2-page overlap) + page 6
    assert second_run_ocrd == [4, 5, 6]
    assert entry["resumed_pages"] == 2
    assert entry["ocrd_pages"] == 5
    # Cross-page dehyphenation between checkpointed page 3 and re-OCR'd page 4 still worked
    assert entry["dehyphenated_pairs"] == 1
    sent_pages = client.replace_book_ocr.call_args.args[1]
    assert sent_pages[2].text == "بۇ تەتقىقاتلار"
    assert sent_pages[3].text == "داۋامى."
    # Workdir cleaned up after successful completion
    assert not ckpt_dir.exists()


@pytest.mark.asyncio
async def test_backfill_wave_batching_double_buffers_and_prefetches_next_book(
    tmp_path: Path,
):
    from types import SimpleNamespace

    client = MagicMock()

    def _fake_download(book_id: str, dest: Path):
        doc = fitz.open()
        for i in range(5):
            p = doc.new_page(width=300, height=400)
            p.draw_rect(fitz.Rect(30, 40, 260, 180), fill=(0, 0, 0))
        doc.save(dest)
        doc.close()
        return dest

    client.download_book_pdf.side_effect = _fake_download
    client.get_book_pages.side_effect = lambda bid: [
        {"pageNumber": p, "text": f"Old {bid} p{p}", "isToc": False}
        for p in range(1, 6)
    ]
    client.replace_book_ocr.return_value = {"pagesUpdated": 4, "pagesUnchanged": 1}
    client.get_backfill_candidates.side_effect = [
        {
            "candidates": [
                {"id": "wave-b1", "title": "Wave Book 1", "totalPages": 5},
                {"id": "wave-b2", "title": "Wave Book 2", "totalPages": 5},
            ],
            "pending_index_books": 0,
        },
        {
            "candidates": [
                {"id": "wave-b2", "title": "Wave Book 2", "totalPages": 5},
            ],
            "pending_index_books": 0,
        },
        {"candidates": [], "pending_index_books": 0},
    ]

    wave_sizes: list[int] = []

    def _fake_predictor(images, full_page=True):
        wave_sizes.append(len(images))
        out = []
        for idx in range(len(images)):
            blk = MagicMock()
            blk.label = "Text"
            blk.html = f"<p>Wave OCR text {idx + 1}</p>"
            blk.reading_order = 0
            blk.skipped = False
            blk.error = False
            blk.confidence = 0.98
            blk.polygon = [[30.0, 40.0], [260.0, 40.0], [260.0, 180.0], [30.0, 180.0]]
            out.append(SimpleNamespace(blocks=[blk]))
        return out

    with (
        patch(
            "backfill.get_recognition_predictor",
            new=AsyncMock(return_value=_fake_predictor),
        ),
        patch("engine.recognize._is_phantom_bleed_through_block", return_value=False),
    ):
        results = await backfill.run_backfill(
            client, tmp_path, concurrency=2, max_server_backlog=3
        )

    assert len(results) == 2
    # Each 5-page book skips p1 cover -> 4 pages OCR'd in two synchronized waves of 2
    assert wave_sizes == [2, 2, 2, 2]
    # Both books downloaded once each (wave-b2 reused prefetched PDF + existing_pages.json)
    assert client.download_book_pdf.call_count == 2
    assert client.get_book_pages.call_count == 2
    assert not list(tmp_path.glob("backfill-*"))


@pytest.mark.asyncio
async def test_backfill_single_book_non_wave_path_when_wave_batching_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("KITABIM_OCR_WAVE_BATCHING", "0")
    client = MagicMock()
    client.download_book_pdf.side_effect = lambda b, dest: _create_sample_pdf(
        dest, num_pages=2
    )
    client.get_book_pages.return_value = [
        {"pageNumber": 1, "text": "Cover", "isToc": False},
        {"pageNumber": 2, "text": "Old p2", "isToc": False},
    ]
    client.replace_book_ocr.return_value = {"pagesUpdated": 1, "pagesUnchanged": 1}

    async def _fake_single_page_ocr(fitz_page, predictor, **kwargs):
        return PageOcrResult(
            text="Non-wave page 2",
            detected_page_number=1,
            ended_with_hyphen=False,
        )

    with (
        patch("backfill.get_recognition_predictor", new=AsyncMock(return_value="pred")),
        patch(
            "backfill.ocr_page_with_meta", side_effect=_fake_single_page_ocr
        ) as mock_p,
    ):
        entry = await backfill.backfill_single_book("book-nowave", client, tmp_path)

    assert entry["ocrd_pages"] == 1
    assert mock_p.call_count == 1


def test_local_skipped_books_persistence_and_manual_list_format(tmp_path: Path):
    # Supports hand-edited plain JSON list of book IDs
    (tmp_path / "skipped_books.json").write_text(
        '["legacy-skip-1", "legacy-skip-2"]', encoding="utf-8"
    )
    loaded = backfill.load_skipped_books(tmp_path)
    assert set(loaded.keys()) == {"legacy-skip-1", "legacy-skip-2"}

    # Skipping a book also cleans up any unstarted prefetched directory
    prefetch_dir = tmp_path / "backfill-skip-me"
    prefetch_dir.mkdir(parents=True)
    (prefetch_dir / "book.pdf").write_bytes(b"%PDF-1.4")

    entry = backfill.skip_book_locally(
        tmp_path,
        "skip-me",
        title="چوڭ لۇغەت",
        author="ئاپتور",
        total_pages=850,
        reason="Scanned dictionary",
    )
    assert entry["book_id"] == "skip-me"
    assert entry["title"] == "چوڭ لۇغەت"
    assert entry["total_pages"] == 850
    assert not prefetch_dir.exists()

    ordered = backfill.list_skipped_books(tmp_path)
    assert ordered[0]["book_id"] == "skip-me"
    assert len(ordered) == 3

    assert backfill.unskip_book_locally(tmp_path, "legacy-skip-1") is True
    assert backfill.unskip_book_locally(tmp_path, "non-existent") is False
    assert set(backfill.load_skipped_books(tmp_path).keys()) == {
        "skip-me",
        "legacy-skip-2",
    }


@pytest.mark.asyncio
async def test_run_backfill_excludes_locally_skipped_books_with_limit(tmp_path: Path):
    backfill.skip_book_locally(tmp_path, "b-skip-1", title="Skip 1")

    client = MagicMock()
    client.get_backfill_candidates.return_value = {
        "candidates": [
            {"id": "b-skip-1", "title": "Skip 1", "totalPages": 100},
            {"id": "b-skip-2", "title": "Skip 2", "totalPages": 200},
            {"id": "b-process", "title": "Process Me", "totalPages": 30},
        ],
        "pending_index_books": 0,
    }

    with patch(
        "backfill.backfill_single_book",
        new=AsyncMock(return_value={"book_id": "b-process", "ocrd_pages": 29}),
    ) as mock_single:
        results = await backfill.run_backfill(
            client,
            tmp_path,
            limit=1,
            skip_book_ids=["b-skip-2"],
        )

    assert len(results) == 1
    assert results[0]["book_id"] == "b-process"
    mock_single.assert_awaited_once()
    assert mock_single.await_args.args[0] == "b-process"
    # Requested batch_limit accounted for the 2 skipped IDs so limit=1 did not starve
    assert client.get_backfill_candidates.call_args.kwargs["limit"] == 3
