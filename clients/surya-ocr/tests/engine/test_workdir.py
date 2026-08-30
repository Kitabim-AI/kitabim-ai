from pathlib import Path

import pytest

from engine.workdir import OcrWorkDir, PageState


def test_create_writes_book_json_and_empty_pages(tmp_path: Path):
    wd = OcrWorkDir.create(
        tmp_path / "work", source_pdf=Path("book.pdf"), total_pages=3
    )

    assert wd.total_pages == 3
    assert wd.book_id is None
    assert wd.all_pages() == []
    assert (tmp_path / "work" / "book.json").exists()


def test_set_page_then_get_page_round_trips(tmp_path: Path):
    wd = OcrWorkDir.create(
        tmp_path / "work", source_pdf=Path("book.pdf"), total_pages=2
    )

    wd.set_page(1, text="hello", is_toc=False, confidence=0.9, status="ocrd")
    page = wd.get_page(1)

    assert page == PageState(
        page_number=1,
        text="hello",
        is_toc=False,
        confidence=0.9,
        status="ocrd",
        error=None,
    )


def test_set_page_records_error_on_failed_status(tmp_path: Path):
    wd = OcrWorkDir.create(
        tmp_path / "work", source_pdf=Path("book.pdf"), total_pages=1
    )

    wd.set_page(1, text="", is_toc=False, confidence=0.0, status="failed", error="boom")
    page = wd.get_page(1)

    assert page.status == "failed"
    assert page.error == "boom"


def test_save_and_load_round_trips_all_state(tmp_path: Path):
    wd = OcrWorkDir.create(
        tmp_path / "work", source_pdf=Path("book.pdf"), total_pages=1, book_id="abc123"
    )
    wd.set_page(1, text="hi", is_toc=True, confidence=0.5, status="reviewed")
    wd.save()

    reloaded = OcrWorkDir.load(tmp_path / "work")

    assert reloaded.book_id == "abc123"
    assert reloaded.total_pages == 1
    assert reloaded.get_page(1).text == "hi"
    assert reloaded.get_page(1).is_toc is True


def test_image_path_uses_zero_padded_page_number(tmp_path: Path):
    wd = OcrWorkDir.create(
        tmp_path / "work", source_pdf=Path("book.pdf"), total_pages=1
    )
    assert wd.image_path(7) == tmp_path / "work" / "pages" / "0007.png"


def test_get_page_missing_raises_key_error(tmp_path: Path):
    wd = OcrWorkDir.create(
        tmp_path / "work", source_pdf=Path("book.pdf"), total_pages=1
    )
    with pytest.raises(KeyError):
        wd.get_page(1)


def test_all_pages_sorted_by_page_number(tmp_path: Path):
    wd = OcrWorkDir.create(
        tmp_path / "work", source_pdf=Path("book.pdf"), total_pages=2
    )
    wd.set_page(2, text="b", is_toc=False, confidence=0.9, status="ocrd")
    wd.set_page(1, text="a", is_toc=False, confidence=0.9, status="ocrd")

    numbers = [p.page_number for p in wd.all_pages()]
    assert numbers == [1, 2]
