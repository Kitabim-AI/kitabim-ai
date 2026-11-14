from __future__ import annotations

import argparse
import asyncio
import os
import time
from pathlib import Path


from dotenv import load_dotenv

from backfill import run_backfill
from engine.workdir import OcrWorkDir
from kitabim_client.api import KitabimClient
from kitabim_client.auth import login_and_save
from preview.app_server import serve_app
from preview.server import serve

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "kitabim-ocr-client" / "token.json"
DOTENV_PATH = Path(__file__).resolve().parent / ".env"


def cmd_login(base_url: str | None = None, provider: str = "google") -> None:
    load_dotenv(DOTENV_PATH)
    effective_base_url = base_url or os.environ.get("KITABIM_BASE_URL")
    if not effective_base_url:
        raise SystemExit("KITABIM_BASE_URL environment variable is required")
    tokens = login_and_save(effective_base_url, DEFAULT_CONFIG_PATH, provider=provider)
    has_refresh = bool(tokens.get("refresh_token"))
    print(
        f"Logged in successfully. Saved token to {DEFAULT_CONFIG_PATH} "
        f"(refresh_token={'yes' if has_refresh else 'no'})."
    )


def cmd_backfill(
    *,
    book_id: str | None = None,
    limit: int | None = None,
    max_server_backlog: int = 3,
    dry_run: bool = False,
    audit_log: str | None = None,
    engine: str | None = None,
    concurrency: int | None = None,
    base_url: str | None = None,
) -> list[dict]:
    load_dotenv(DOTENV_PATH)
    effective_base_url = base_url or os.environ.get("KITABIM_BASE_URL")
    if not effective_base_url:
        raise SystemExit("KITABIM_BASE_URL environment variable is required")
    work_dir = os.environ.get("KITABIM_WORK_DIR")
    if not work_dir:
        raise SystemExit("KITABIM_WORK_DIR environment variable is required")
    work_root = Path(work_dir).expanduser()
    client = KitabimClient(
        base_url=effective_base_url,
        config_path=DEFAULT_CONFIG_PATH,
        headless=True,
    )
    audit_path = Path(audit_log).expanduser() if audit_log else None
    return asyncio.run(
        run_backfill(
            client,
            work_root,
            book_id=book_id,
            limit=limit,
            max_server_backlog=max_server_backlog,
            dry_run=dry_run,
            engine=engine,
            concurrency=concurrency,
            audit_log_path=audit_path,
        )
    )


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
    load_dotenv(DOTENV_PATH)
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

    login_parser = sub.add_parser(
        "login",
        help="Authenticate via loopback browser OAuth and store access_token + refresh_token in token.json",
    )
    login_parser.add_argument("--base-url", default=None)
    login_parser.add_argument("--provider", default="google")

    backfill_parser = sub.add_parser(
        "backfill",
        help="Headless sequential re-OCR backfill for legacy PDFs using Surya 2.5",
    )
    backfill_parser.add_argument("--dry-run", action="store_true")
    backfill_parser.add_argument("--book-id", default=None)
    backfill_parser.add_argument("--limit", type=int, default=None)
    backfill_parser.add_argument(
        "--max-server-backlog",
        type=int,
        default=3,
        help="Pause backfill when server has >= N books with unsubmitted index work (default: 3)",
    )
    backfill_parser.add_argument("--audit-log", default=None)
    backfill_parser.add_argument("--base-url", default=None)
    backfill_parser.add_argument(
        "--engine",
        choices=["surya"],
        default=argparse.SUPPRESS,
        help="OCR engine to use (default: configured in .env or 'surya')",
    )
    backfill_parser.add_argument(
        "--concurrency",
        type=int,
        default=argparse.SUPPRESS,
        help="Number of pages to process concurrently (default: configured in .env or 4; max 4 for Surya)",
    )

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
    elif command == "login":
        cmd_login(base_url=args.base_url, provider=args.provider)
    elif command == "backfill":
        cmd_backfill(
            book_id=args.book_id,
            limit=args.limit,
            max_server_backlog=args.max_server_backlog,
            dry_run=args.dry_run,
            audit_log=args.audit_log,
            engine=engine,
            concurrency=concurrency,
            base_url=args.base_url,
        )


if __name__ == "__main__":
    main()
