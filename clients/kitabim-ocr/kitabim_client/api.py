from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from kitabim_client.auth import get_valid_token

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
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.config_path = config_path
        self.provider = provider
        self._app_id = (
            app_id
            if app_id is not None
            else (
                os.environ.get("KITABIM_APP_ID")
                or os.environ.get("SECURITY_APP_ID")
                or ""
            )
        )

    def _headers(self) -> dict:
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
    ) -> dict:
        pages_json = json.dumps(
            [
                {"pageNumber": p.page_number, "text": p.text, "isToc": p.is_toc}
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
                files={"file": (upload_filename, f, "application/pdf")},
                data={"pages": pages_json},
                timeout=120.0,
            )
        return self._check(response)

    def push_page_correction(self, book_id: str, page: "PageState") -> dict:
        update_response = httpx.post(
            f"{self.base_url}/books/{book_id}/pages/{page.page_number}/update",
            headers=self._headers(),
            json={"text": page.text},
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

    def download_book_pdf(self, book_id: str, dest: Path) -> Path:
        response = httpx.get(
            f"{self.base_url}/books/{book_id}/download",
            headers=self._headers(),
            timeout=120.0,
        )
        if response.status_code >= 400:
            raise KitabimAPIError(
                f"{response.status_code} from Kitabim API: {response.text}"
            )
        dest.write_bytes(response.content)
        return dest

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
