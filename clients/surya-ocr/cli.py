from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import fitz

from engine.recognize import (
    LowConfidenceOcrError,
    get_recognition_predictor,
    ocr_page_with_surya,
)
from engine.workdir import OcrWorkDir
from kitabim_client.api import KitabimClient
from preview.server import serve

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "surya-ocr-client" / "token.json"
RENDER_ZOOM = 1.5


def render_page_png(
    doc: "fitz.Document", page_number: int, zoom: float = RENDER_ZOOM
) -> bytes:
    page = doc.load_page(page_number - 1)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    return pix.tobytes("png")


async def cmd_ocr(pdf_path: Path, out_dir: Path, open_preview: bool = True) -> None:
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    workdir = OcrWorkDir.create(out_dir, source_pdf=pdf_path, total_pages=total_pages)

    predictor = await get_recognition_predictor()
    for page_number in range(1, total_pages + 1):
        image_bytes = render_page_png(doc, page_number)
        workdir.image_path(page_number).write_bytes(image_bytes)

        fitz_page = doc.load_page(page_number - 1)
        try:
            text = await ocr_page_with_surya(fitz_page, predictor)
            workdir.set_page(
                page_number, text=text, is_toc=False, confidence=1.0, status="ocrd"
            )
            print(f"OCR'd page {page_number}/{total_pages}")
        except LowConfidenceOcrError as exc:
            # Flag and move on - one bad page must not abort the whole book.
            # The preview UI surfaces status="failed" pages so nothing gets
            # silently pushed with missing/wrong text.
            workdir.set_page(
                page_number,
                text="",
                is_toc=False,
                confidence=0.0,
                status="failed",
                error=str(exc),
            )
            print(f"OCR FAILED on page {page_number}/{total_pages}: {exc}")

    workdir.save()
    print(f"Done. Work directory: {out_dir}")

    if open_preview:
        serve(workdir, client=None)


async def cmd_correct(
    book_id: str, out_dir: Path, base_url: str, open_preview: bool = True
) -> None:
    client = KitabimClient(base_url=base_url, config_path=DEFAULT_CONFIG_PATH)

    pdf_path = out_dir / "book.pdf"
    out_dir.mkdir(parents=True, exist_ok=True)
    client.download_book_pdf(book_id, pdf_path)

    existing_pages = client.get_book_pages(book_id)
    doc = fitz.open(pdf_path)
    total_pages = len(doc)

    workdir = OcrWorkDir.create(
        out_dir, source_pdf=pdf_path, total_pages=total_pages, book_id=book_id
    )
    for page in existing_pages:
        workdir.image_path(page["pageNumber"]).write_bytes(
            render_page_png(doc, page["pageNumber"])
        )
        workdir.set_page(
            page["pageNumber"],
            text=page.get("text") or "",
            is_toc=bool(page.get("isToc")),
            confidence=1.0,
            status="from_kitabim",
        )
    workdir.save()
    print(f"Loaded {len(existing_pages)} existing pages. Work directory: {out_dir}")

    if open_preview:
        serve(workdir, client=client)


def cmd_preview(workdir_path: Path, base_url: str | None) -> None:
    workdir = OcrWorkDir.load(workdir_path)
    client = (
        KitabimClient(base_url=base_url, config_path=DEFAULT_CONFIG_PATH)
        if base_url
        else None
    )
    serve(workdir, client=client)


def cmd_push(workdir_path: Path, base_url: str) -> None:
    workdir = OcrWorkDir.load(workdir_path)
    client = KitabimClient(base_url=base_url, config_path=DEFAULT_CONFIG_PATH)
    if workdir.book_id is None:
        result = client.push_new_book(workdir.source_pdf, workdir.all_pages())
    else:
        for page in workdir.all_pages():
            client.push_page_correction(workdir.book_id, page)
        result = {"status": "corrections_pushed", "count": len(workdir.all_pages())}
    print(result)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local Surya OCR client for Kitabim")
    sub = parser.add_subparsers(dest="command", required=True)

    ocr_parser = sub.add_parser(
        "ocr", help="Render + OCR a new PDF, then open the preview UI"
    )
    ocr_parser.add_argument("pdf")
    ocr_parser.add_argument("--out", required=True)
    ocr_parser.add_argument("--no-preview", action="store_true")

    preview_parser = sub.add_parser(
        "preview", help="Reopen the preview UI for an existing work directory"
    )
    preview_parser.add_argument("workdir")
    preview_parser.add_argument("--base-url")

    push_parser = sub.add_parser(
        "push", help="Push a work directory's results to Kitabim without opening the UI"
    )
    push_parser.add_argument("workdir")
    push_parser.add_argument("--base-url", required=True)

    correct_parser = sub.add_parser(
        "correct", help="Download an existing book and open it for correction"
    )
    correct_parser.add_argument("book_id")
    correct_parser.add_argument("--out", required=True)
    correct_parser.add_argument("--base-url", required=True)
    correct_parser.add_argument("--no-preview", action="store_true")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "ocr":
        asyncio.run(
            cmd_ocr(Path(args.pdf), Path(args.out), open_preview=not args.no_preview)
        )
    elif args.command == "preview":
        cmd_preview(Path(args.workdir), args.base_url)
    elif args.command == "push":
        cmd_push(Path(args.workdir), args.base_url)
    elif args.command == "correct":
        asyncio.run(
            cmd_correct(
                args.book_id,
                Path(args.out),
                args.base_url,
                open_preview=not args.no_preview,
            )
        )


if __name__ == "__main__":
    main()
