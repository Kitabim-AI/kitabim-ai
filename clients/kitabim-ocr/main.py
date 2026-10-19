from __future__ import annotations

import argparse
import os
import time
from pathlib import Path


from dotenv import load_dotenv

from engine.workdir import OcrWorkDir
from kitabim_client.api import KitabimClient
from preview.app_server import serve_app
from preview.server import serve

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "kitabim-ocr-client" / "token.json"
DOTENV_PATH = Path(__file__).resolve().parent / ".env"


def cmd_app(engine: str | None = None, concurrency: int | None = None) -> None:
    load_dotenv(DOTENV_PATH)
    base_url = os.environ.get("KITABIM_BASE_URL")
    if not base_url:
        raise SystemExit("KITABIM_BASE_URL environment variable is required")
    work_dir = os.environ.get("KITABIM_WORK_DIR")
    if not work_dir:
        raise SystemExit("KITABIM_WORK_DIR environment variable is required")

    client = KitabimClient(base_url=base_url, config_path=DEFAULT_CONFIG_PATH)
    serve_app(
        client,
        Path(work_dir).expanduser(),
        engine=engine,
        concurrency=concurrency,
    )


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
    if (
        workdir.book_id is not None
        and hasattr(client, "book_exists")
        and not client.book_exists(workdir.book_id)
    ):
        workdir.book_id = None
        workdir.uploaded = False
        workdir.save_metadata()

    if workdir.book_id is None:
        result = client.push_new_book(
            workdir.source_pdf,
            workdir.all_pages(),
            filename=workdir.original_filename,
        )
        if isinstance(result, dict) and result.get("bookId"):
            workdir.book_id = str(result["bookId"])
            workdir.uploaded = True
            workdir.uploaded_at = time.time()
            workdir.save_metadata()
    else:
        for page in workdir.all_pages():
            client.push_page_correction(workdir.book_id, page)
        workdir.uploaded = True
        workdir.uploaded_at = time.time()
        workdir.save_metadata()
        result = {"status": "corrections_pushed", "count": len(workdir.all_pages())}
    print(result)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Kitabim OCR Desktop Client")
    parser.add_argument(
        "--engine",
        choices=["surya"],
        default=None,
        help="OCR engine to use (default: configured in .env or 'surya')",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=None,
        help="Number of pages to process concurrently (default: configured in .env or 4; max 4 for Surya)",
    )
    sub = parser.add_subparsers(dest="command", required=False)

    app_parser = sub.add_parser(
        "app",
        help=(
            "Open the book-picker landing page (correct an existing Kitabim book "
            "or OCR a new local PDF). Reads KITABIM_BASE_URL and KITABIM_WORK_DIR "
            "from the environment."
        ),
    )
    app_parser.add_argument(
        "--engine",
        choices=["surya"],
        default=argparse.SUPPRESS,
        help="OCR engine to use (default: configured in .env or 'surya')",
    )
    app_parser.add_argument(
        "--concurrency",
        type=int,
        default=argparse.SUPPRESS,
        help="Number of pages to process concurrently (default: configured in .env or 4; max 4 for Surya)",
    )

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

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    command = args.command or "app"
    engine = getattr(args, "engine", None)
    concurrency = getattr(args, "concurrency", None)

    if command == "app":
        cmd_app(engine=engine, concurrency=concurrency)
    elif command == "preview":
        cmd_preview(Path(args.workdir), args.base_url)
    elif command == "push":
        cmd_push(Path(args.workdir), args.base_url)


if __name__ == "__main__":
    main()
