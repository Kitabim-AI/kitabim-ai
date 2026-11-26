from __future__ import annotations

import gzip
import json
import os
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Callable
from urllib.parse import urlparse

import httpx

from kitabim_client.auth import AuthError, get_valid_token, refresh_access_token

if TYPE_CHECKING:
    from engine.workdir import PageState


class KitabimAPIError(Exception):
    """Raised on any non-2xx response from the Kitabim API."""


class KitabimAuthError(KitabimAPIError):
    """Raised when the Kitabim API returns HTTP 401 even after token refresh retry."""


def is_auth_failure(exc: BaseException) -> bool:
    """Return True if ``exc`` indicates an expired or invalid authentication token."""
    if isinstance(exc, (AuthError, KitabimAuthError)):
        return True
    if isinstance(exc, KitabimAPIError) and str(exc).lstrip().startswith("401 "):
        return True
    return False


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
        self._explicit_app_id = app_id
        self._app_id = (
            app_id if app_id is not None else (os.environ.get("SECURITY_APP_ID") or "")
        )

    def _current_app_id(self) -> str:
        if self._explicit_app_id is not None:
            return self._explicit_app_id
        dotenv_path = Path(__file__).resolve().parent.parent / ".env"
        if dotenv_path.exists():
            try:
                from dotenv import dotenv_values

                vals = dotenv_values(dotenv_path)
                if vals.get("SECURITY_APP_ID"):
                    self._app_id = str(vals["SECURITY_APP_ID"]).strip()
                    return self._app_id
            except Exception:
                pass
        return os.environ.get("SECURITY_APP_ID") or self._app_id

    def as_headless(self) -> "KitabimClient":
        """Return a headless view of this client sharing the same token config and credentials."""
        if self.headless:
            return self
        return KitabimClient(
            base_url=self.base_url,
            config_path=self.config_path,
            provider=self.provider,
            app_id=self._explicit_app_id,
            headless=True,
        )

    def _headers_with_token(
        self, token: str, extra_headers: dict[str, str] | None = None
    ) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {token}"}
        app_id = self._current_app_id()
        if app_id:
            headers["X-Kitabim-App-Id"] = app_id
        if extra_headers:
            headers.update(extra_headers)
        return headers

    def _headers(self) -> dict:
        if self.headless:
            token = get_valid_token(
                self.base_url, self.config_path, self.provider, headless=True
            )
        else:
            token = get_valid_token(self.base_url, self.config_path, self.provider)
        return self._headers_with_token(token)

    def _request_with_auth_retry(
        self,
        request_fn: Callable[[dict[str, str]], httpx.Response],
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        headers = self._headers()
        if extra_headers:
            headers.update(extra_headers)
        used_token = (
            headers.get("Authorization", "").removeprefix("Bearer ").strip() or None
        )

        response = request_fn(headers)
        if response.status_code != 401:
            return response

        try:
            refreshed = refresh_access_token(
                self.base_url, self.config_path, rejected_token=used_token
            )
        except TypeError:
            refreshed = refresh_access_token(self.base_url, self.config_path)

        if refreshed:
            retry_headers = (
                self._headers_with_token(refreshed, extra_headers)
                if isinstance(refreshed, str)
                else {**self._headers(), **(extra_headers or {})}
            )
            used_token = (
                retry_headers.get("Authorization", "").removeprefix("Bearer ").strip()
                or used_token
            )
            response = request_fn(retry_headers)
            if response.status_code != 401:
                return response

        if not self.headless:
            try:
                new_token = get_valid_token(
                    self.base_url,
                    self.config_path,
                    self.provider,
                    force_refresh=True,
                    rejected_token=used_token,
                )
            except TypeError:
                new_token = get_valid_token(
                    self.base_url, self.config_path, self.provider
                )
            if new_token and new_token != used_token:
                retry_headers = self._headers_with_token(new_token, extra_headers)
                response = request_fn(retry_headers)

        return response

    def _check(self, response: httpx.Response) -> dict:
        if response.status_code == 401:
            raise KitabimAuthError(
                f"{response.status_code} from Kitabim API: {response.text}"
            )
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
        pages_bytes = pages_json.encode("utf-8")
        upload_filename = filename or pdf_path.name
        if not upload_filename.lower().endswith(".pdf"):
            upload_filename = f"{upload_filename}.pdf"

        def _send(headers: dict[str, str]) -> httpx.Response:
            with open(pdf_path, "rb") as f:
                return httpx.post(
                    f"{self.base_url}/books/upload-ocrd",
                    headers=headers,
                    data={"ocr_version": ocr_version},
                    files={
                        "file": (upload_filename, f, "application/pdf"),
                        "pages": (
                            "pages.json",
                            pages_bytes,
                            "application/json",
                        ),
                    },
                    timeout=120.0,
                )

        response = self._request_with_auth_retry(_send)
        return self._check(response)

    def push_page_correction(self, book_id: str, page: "PageState") -> dict:
        clean_text = (page.text or "").replace("\x00", "")
        update_response = self._request_with_auth_retry(
            lambda headers: httpx.post(
                f"{self.base_url}/books/{book_id}/pages/{page.page_number}/update",
                headers=headers,
                json={"text": clean_text},
                timeout=60.0,
            )
        )
        self._check(update_response)

        toc_response = self._request_with_auth_retry(
            lambda headers: httpx.post(
                f"{self.base_url}/books/{book_id}/pages/{page.page_number}/toc",
                headers=headers,
                json={"isToc": page.is_toc},
                timeout=30.0,
            )
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
        app_id = self._current_app_id()
        if app_id:
            headers["X-Kitabim-App-Id"] = app_id
        return full_url, headers

    def download_book_pdf(self, book_id: str, dest: Path) -> Path:
        response: httpx.Response | None = None
        for attempt in range(2):
            ticket_res = self._request_with_auth_retry(
                lambda headers: httpx.post(
                    f"{self.base_url}/books/{book_id}/download-ticket",
                    headers=headers,
                    timeout=30.0,
                )
            )
            ticket_data = self._check(ticket_res)
            download_url = ticket_data.get("download_url") or ticket_data.get(
                "downloadUrl"
            )
            if not download_url:
                raise KitabimAPIError(
                    "Missing download_url in download-ticket response"
                )

            full_url, dl_headers = self._resolve_ticket_url(str(download_url))
            response = httpx.get(
                full_url,
                headers=dl_headers,
                follow_redirects=True,
                timeout=300.0,
            )
            if response.status_code in (401, 403) and attempt == 0:
                continue
            break

        assert response is not None
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
        response = self._request_with_auth_retry(
            lambda headers: httpx.get(
                f"{self.base_url}/books/backfill-candidates",
                headers=headers,
                params={"ocr_version": ocr_version, "limit": limit},
                timeout=30.0,
            )
        )
        return self._check(response)

    list_backfill_candidates = get_backfill_candidates

    def replace_book_ocr(
        self,
        book_id: str,
        pages: list["PageState"],
        ocr_version: str = "surya-2.5-v2",
        request_id: str | None = None,
        *,
        force_overwrite_manual: bool = True,
    ) -> dict:
        payload = {
            "ocrVersion": ocr_version,
            "forceOverwriteManual": bool(force_overwrite_manual),
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
        extra_headers = {
            "Content-Type": "application/json",
            "Content-Encoding": "gzip",
            "X-Request-ID": req_id,
        }

        response = self._request_with_auth_retry(
            lambda headers: httpx.post(
                f"{self.base_url}/books/{book_id}/replace-ocr",
                headers=headers,
                content=compressed,
                timeout=180.0,
            ),
            extra_headers=extra_headers,
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
        response = self._request_with_auth_retry(
            lambda headers: httpx.get(
                f"{self.base_url}/books/",
                headers=headers,
                params={
                    "q": q,
                    "page": page,
                    "pageSize": page_size,
                    "sortBy": sort_by,
                    "order": order,
                },
                timeout=30.0,
            )
        )
        return self._check(response)

    def get_book_pages(self, book_id: str) -> list[dict]:
        all_pages: list[dict] = []
        skip = 0
        limit = 100
        while True:
            response = self._request_with_auth_retry(
                lambda headers, _skip=skip: httpx.get(
                    f"{self.base_url}/books/{book_id}/pages",
                    headers=headers,
                    params={"skip": _skip, "limit": limit},
                    timeout=60.0,
                )
            )
            batch = self._check(response)
            all_pages.extend(batch)
            if len(batch) < limit:
                break
            skip += limit
        return all_pages

    def get_book(self, book_id: str) -> dict | None:
        response = self._request_with_auth_retry(
            lambda headers: httpx.get(
                f"{self.base_url}/books/{book_id}",
                headers=headers,
                timeout=15.0,
            )
        )
        if response.status_code == 404:
            return None
        return self._check(response)

    def book_exists(self, book_id: str) -> bool:
        try:
            response = self._request_with_auth_retry(
                lambda headers: httpx.get(
                    f"{self.base_url}/books/{book_id}",
                    headers=headers,
                    timeout=15.0,
                )
            )
            if response.status_code == 404:
                return False
            if response.status_code == 401:
                raise KitabimAuthError(
                    f"{response.status_code} from Kitabim API: {response.text}"
                )
            if response.status_code < 400:
                return True
            return True
        except (AuthError, KitabimAuthError):
            raise
        except Exception:
            return True
