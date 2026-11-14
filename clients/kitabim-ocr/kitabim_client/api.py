from __future__ import annotations

import gzip
import json
import os
import uuid
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import httpx

from kitabim_client.auth import get_valid_token, refresh_access_token

if TYPE_CHECKING:
    from engine.workdir import PageState


class KitabimAPIError(Exception):
    """Raised on any non-2xx response from the Kitabim API."""


class KitabimClient:
    def __init__(
        self,
        base_url: str,
        config_path: Path,
        provider: str = "google",
        app_id: str | None = None,
        *,
        headless: bool = False,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.config_path = config_path
        self.provider = provider
        self.headless = headless
        self._app_id = (
            app_id if app_id is not None else (os.environ.get("SECURITY_APP_ID") or "")
        )

    def _headers(self) -> dict:
        if self.headless:
            token = get_valid_token(
                self.base_url, self.config_path, self.provider, headless=True
            )
        else:
            token = get_valid_token(self.base_url, self.config_path, self.provider)
        headers = {"Authorization": f"Bearer {token}"}
        if self._app_id:
            headers["X-Kitabim-App-Id"] = self._app_id
        return headers

    def _check(self, response: httpx.Response) -> dict:
        if response.status_code >= 400:
            raise KitabimAPIError(
                f"{response.status_code} from Kitabim API: {response.text}"
            )
        return response.json()

    def push_new_book(
        self,
        pdf_path: Path,
        pages: list["PageState"],
        filename: str | None = None,
        ocr_version: str = "surya-2.5-v2",
    ) -> dict:
        pages_json = json.dumps(
            [
                {
                    "pageNumber": p.page_number,
                    "text": (p.text or "").replace("\x00", ""),
                    "isToc": p.is_toc,
                    "detectedPageNumber": getattr(p, "detected_page_number", None),
                }
                for p in pages
            ],
            ensure_ascii=False,
        )
        upload_filename = filename or pdf_path.name
        if not upload_filename.lower().endswith(".pdf"):
            upload_filename = f"{upload_filename}.pdf"
        with open(pdf_path, "rb") as f:
            response = httpx.post(
                f"{self.base_url}/books/upload-ocrd",
                headers=self._headers(),
                data={"ocr_version": ocr_version},
                files={
                    "file": (upload_filename, f, "application/pdf"),
                    "pages": (
                        "pages.json",
                        pages_json.encode("utf-8"),
                        "application/json",
                    ),
                },
                timeout=120.0,
            )
        return self._check(response)

    def push_page_correction(self, book_id: str, page: "PageState") -> dict:
        update_response = httpx.post(
            f"{self.base_url}/books/{book_id}/pages/{page.page_number}/update",
            headers=self._headers(),
            json={"text": (page.text or "").replace("\x00", "")},
            timeout=60.0,
        )
        self._check(update_response)

        toc_response = httpx.post(
            f"{self.base_url}/books/{book_id}/pages/{page.page_number}/toc",
            headers=self._headers(),
            json={"isToc": page.is_toc},
            timeout=30.0,
        )
        return self._check(toc_response)

    def _resolve_ticket_url(self, download_url: str) -> tuple[str, dict[str, str]]:
        """Resolve a download ticket URL and return `(full_url, headers)` without Authorization."""
        if download_url.startswith(("http://", "https://")):
            return download_url, {}
        parsed = urlparse(self.base_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        full_url = (
            f"{origin}{download_url}"
            if download_url.startswith("/")
            else f"{self.base_url}/{download_url}"
        )
        headers: dict[str, str] = {}
        if self._app_id:
            headers["X-Kitabim-App-Id"] = self._app_id
        return full_url, headers

    def download_book_pdf(self, book_id: str, dest: Path) -> Path:
        ticket_res = httpx.post(
            f"{self.base_url}/books/{book_id}/download-ticket",
            headers=self._headers(),
            timeout=30.0,
        )
        if ticket_res.status_code == 401:
            if refresh_access_token(self.base_url, self.config_path):
                ticket_res = httpx.post(
                    f"{self.base_url}/books/{book_id}/download-ticket",
                    headers=self._headers(),
                    timeout=30.0,
                )
        ticket_data = self._check(ticket_res)
        download_url = ticket_data.get("download_url") or ticket_data.get("downloadUrl")
        if not download_url:
            raise KitabimAPIError("Missing download_url in download-ticket response")

        full_url, dl_headers = self._resolve_ticket_url(str(download_url))
        response = httpx.get(
            full_url,
            headers=dl_headers,
            follow_redirects=True,
            timeout=300.0,
        )
        if response.status_code != 200:
            raise KitabimAPIError(
                f"{response.status_code} downloading PDF: {response.text}"
            )
        content = response.content
        if not content.startswith(b"%PDF-"):
            raise KitabimAPIError(
                "Downloaded file is not a valid PDF (missing %PDF- magic header)"
            )
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        return dest

    def get_backfill_candidates(
        self, ocr_version: str = "surya-2.5-v2", limit: int = 100
    ) -> dict:
        response = httpx.get(
            f"{self.base_url}/books/backfill-candidates",
            headers=self._headers(),
            params={"ocr_version": ocr_version, "limit": limit},
            timeout=30.0,
        )
        if response.status_code == 401 and refresh_access_token(
            self.base_url, self.config_path
        ):
            response = httpx.get(
                f"{self.base_url}/books/backfill-candidates",
                headers=self._headers(),
                params={"ocr_version": ocr_version, "limit": limit},
                timeout=30.0,
            )
        return self._check(response)

    list_backfill_candidates = get_backfill_candidates

    def replace_book_ocr(
        self,
        book_id: str,
        pages: list["PageState"],
        ocr_version: str = "surya-2.5-v2",
        request_id: str | None = None,
    ) -> dict:
        payload = {
            "ocrVersion": ocr_version,
            "pages": [
                {
                    "pageNumber": p.page_number,
                    "text": (p.text or "").replace("\x00", ""),
                    "isToc": bool(p.is_toc),
                    "detectedPageNumber": getattr(p, "detected_page_number", None),
                    "skipped": bool(getattr(p, "skipped", False)),
                }
                for p in pages
            ],
        }
        compressed = gzip.compress(
            json.dumps(payload, ensure_ascii=False).encode("utf-8")
        )
        req_id = request_id or str(uuid.uuid4())

        def _make_headers() -> dict[str, str]:
            h = self._headers()
            h["Content-Type"] = "application/json"
            h["Content-Encoding"] = "gzip"
            h["X-Request-ID"] = req_id
            return h

        response = httpx.post(
            f"{self.base_url}/books/{book_id}/replace-ocr",
            headers=_make_headers(),
            content=compressed,
            timeout=180.0,
        )
        if response.status_code == 401 and refresh_access_token(
            self.base_url, self.config_path
        ):
            response = httpx.post(
                f"{self.base_url}/books/{book_id}/replace-ocr",
                headers=_make_headers(),
                content=compressed,
                timeout=180.0,
            )
        return self._check(response)

    def list_books(
        self,
        q: str = "",
        page: int = 1,
        page_size: int = 40,
        sort_by: str = "uploadDate",
        order: int = -1,
    ) -> dict:
        response = httpx.get(
            f"{self.base_url}/books/",
            headers=self._headers(),
            params={
                "q": q,
                "page": page,
                "pageSize": page_size,
                "sortBy": sort_by,
                "order": order,
            },
            timeout=30.0,
        )
        return self._check(response)

    def get_book_pages(self, book_id: str) -> list[dict]:
        all_pages: list[dict] = []
        skip = 0
        limit = 100
        while True:
            response = httpx.get(
                f"{self.base_url}/books/{book_id}/pages",
                headers=self._headers(),
                params={"skip": skip, "limit": limit},
                timeout=60.0,
            )
            batch = self._check(response)
            all_pages.extend(batch)
            if len(batch) < limit:
                break
            skip += limit
        return all_pages

    def get_book(self, book_id: str) -> dict | None:
        response = httpx.get(
            f"{self.base_url}/books/{book_id}",
            headers=self._headers(),
            timeout=15.0,
        )
        if response.status_code == 404:
            return None
        return self._check(response)

    def book_exists(self, book_id: str) -> bool:
        try:
            response = httpx.get(
                f"{self.base_url}/books/{book_id}",
                headers=self._headers(),
                timeout=15.0,
            )
            if response.status_code == 404:
                return False
            if response.status_code < 400:
                return True
            return False
        except Exception:
            return True
