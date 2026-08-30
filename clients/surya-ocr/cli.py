from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from engine.workdir import OcrWorkDir
from kitabim_client.api import KitabimClient
from preview.app_server import serve_app
from preview.server import serve

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "surya-ocr-client" / "token.json"
DOTENV_PATH = Path(__file__).resolve().parent / ".env"


def cmd_app() -> None:
    load_dotenv(DOTENV_PATH)
    base_url = os.environ.get("KITABIM_BASE_URL")
    if not base_url:
        raise SystemExit("KITABIM_BASE_URL environment variable is required")
    work_dir = os.environ.get("KITABIM_WORK_DIR")
    if not work_dir:
        raise SystemExit("KITABIM_WORK_DIR environment variable is required")

    client = KitabimClient(base_url=base_url, config_path=DEFAULT_CONFIG_PATH)
    serve_app(client, Path(work_dir).expanduser())


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

    sub.add_parser(
        "app",
        help=(
            "Open the book-picker landing page (correct an existing Kitabim book "
            "or OCR a new local PDF). Reads KITABIM_BASE_URL and KITABIM_WORK_DIR "
            "from the environment."
        ),
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

    if args.command == "app":
        cmd_app()
    elif args.command == "preview":
        cmd_preview(Path(args.workdir), args.base_url)
    elif args.command == "push":
        cmd_push(Path(args.workdir), args.base_url)


if __name__ == "__main__":
    main()
