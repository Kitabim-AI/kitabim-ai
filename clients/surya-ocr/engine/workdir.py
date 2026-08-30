from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional


@dataclass
class PageState:
    page_number: int
    text: str
    is_toc: bool
    confidence: float
    status: str  # "pending" | "ocrd" | "reviewed" | "failed"
    error: Optional[str] = None  # set when status == "failed"


class OcrWorkDir:
    """Local on-disk state for one book's OCR session: book.json (metadata),
    pages.json (per-page text/status), pages/NNNN.png (cached rendered
    images, written by callers via image_path())."""

    def __init__(
        self,
        path: Path,
        source_pdf: Path,
        total_pages: int,
        book_id: Optional[str] = None,
        pages: Optional[dict[int, PageState]] = None,
    ) -> None:
        self.path = path
        self.source_pdf = source_pdf
        self.total_pages = total_pages
        self.book_id = book_id
        self._pages: dict[int, PageState] = pages or {}

    @classmethod
    def create(
        cls,
        path: Path,
        source_pdf: Path,
        total_pages: int,
        book_id: Optional[str] = None,
    ) -> "OcrWorkDir":
        path.mkdir(parents=True, exist_ok=True)
        (path / "pages").mkdir(exist_ok=True)
        wd = cls(path, source_pdf, total_pages, book_id)
        wd.save()
        return wd

    @classmethod
    def load(cls, path: Path) -> "OcrWorkDir":
        book_meta = json.loads((path / "book.json").read_text())
        pages_raw = []
        pages_path = path / "pages.json"
        if pages_path.exists():
            pages_raw = json.loads(pages_path.read_text())
        pages = {p["page_number"]: PageState(**p) for p in pages_raw}
        return cls(
            path,
            source_pdf=Path(book_meta["source_pdf"]),
            total_pages=book_meta["total_pages"],
            book_id=book_meta["book_id"],
            pages=pages,
        )

    def save(self) -> None:
        (self.path / "book.json").write_text(
            json.dumps(
                {
                    "source_pdf": str(self.source_pdf),
                    "book_id": self.book_id,
                    "total_pages": self.total_pages,
                },
                indent=2,
            )
        )
        (self.path / "pages.json").write_text(
            json.dumps(
                [asdict(p) for p in self.all_pages()],
                ensure_ascii=False,
                indent=2,
            )
        )

    def image_path(self, page_number: int) -> Path:
        return self.path / "pages" / f"{page_number:04d}.png"

    def get_page(self, page_number: int) -> PageState:
        return self._pages[page_number]

    def set_page(
        self,
        page_number: int,
        *,
        text: str,
        is_toc: bool,
        confidence: float,
        status: str,
        error: Optional[str] = None,
    ) -> None:
        self._pages[page_number] = PageState(
            page_number=page_number,
            text=text,
            is_toc=is_toc,
            confidence=confidence,
            status=status,
            error=error,
        )

    def all_pages(self) -> list[PageState]:
        return [self._pages[n] for n in sorted(self._pages)]
