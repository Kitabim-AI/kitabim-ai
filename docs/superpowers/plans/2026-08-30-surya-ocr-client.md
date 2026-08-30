# Local Surya OCR Client Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone, non-containerized desktop client that runs Surya OCR locally, lets the user preview/redo results, and pushes finished text to Kitabim over its public API — plus the one backend endpoint (`POST /books/upload-ocrd`) needed to ingest a pre-OCR'd PDF as a new book.

**Architecture:** Two independent pieces connected only by HTTP. Backend: one new FastAPI endpoint in `books_router.py` that mirrors the existing DOCX-upload pattern (pages pre-filled, `ocr_milestone='succeeded'`, pipeline enters at chunking). Client (`clients/surya-ocr/`): a vendored Surya recognition engine (adapted from `poc/easy-ocr-v2`'s `surya_service.py`), a small on-disk work-directory format, a thin Kitabim HTTP API client with lazy browser-based OAuth login, a local FastAPI preview server, and an `argparse` CLI tying it together.

**Tech Stack:** Backend — existing FastAPI/SQLAlchemy/Pydantic v2 stack, no new dependencies. Client — Python 3.13, `surya-ocr==0.22.1`, PyMuPDF (`fitz`), Pillow, BeautifulSoup4, FastAPI + Uvicorn (preview server), `httpx` (API client), stdlib `argparse`/`http.server`/`webbrowser` (CLI + OAuth capture). No Docker.

## Global Constraints

- No `print()` in the backend — use `log_json(logger, level, "message", key=value)`. The client is a standalone CLI tool, not part of the backend's logging setup — plain `print()` there is fine (it's console UX, not a server).
- No `os.environ.get()` in backend application code — use `settings.*` from `core/config.py`. The client is not part of that settings system; it reads its own CLI flags/env vars directly.
- No hardcoded user-visible strings in the **backend** — use `t("errors.key")` from `app.core.i18n`, with matching entries in both `services/backend/locales/en.json` and `services/backend/locales/ug.json`.
- No raw SQL with user input — always SQLAlchemy bound parameters (not touched by this plan; no new raw SQL is introduced).
- Migration file first, ORM model second, repository third, endpoint last — **not applicable to Task 2**: it reuses the existing `books.source` column (plain `text`, no check constraint) and existing `Book`/`Page` ORM models as-is. No migration needed.
- All new API endpoints need an auth dependency — `POST /books/upload-ocrd` uses `Depends(require_editor)`, matching `POST /books/upload`.
- The client vendors its text-cleanup and Surya-recognition code from `packages/backend-core` rather than importing it, so it stays free of FastAPI/SQLAlchemy/Neo4j and every other backend dependency it doesn't need (per the approved spec). Do not add `packages/backend-core` as a client dependency.
- Per project memory: **do not auto-translate to Uyghur and treat it as final** — the `ug.json` strings added in Task 1 are a best-effort draft and Task 1's steps say so explicitly; flag them for the user's review rather than presenting them as done.

---

## File Structure

```
packages/backend-core/app/models/schemas.py          # + OcrPageInput
services/backend/locales/en.json                     # + 2 error keys
services/backend/locales/ug.json                     # + 2 error keys (draft, needs review)
services/backend/api/endpoints/books_router.py        # + POST /upload-ocrd
services/backend/tests/api/endpoints/books_router_test.py   # + tests for it

clients/surya-ocr/
├── requirements.txt
├── pytest.ini
├── README.md
├── cli.py                          # Task 9
├── engine/
│   ├── __init__.py
│   ├── text_cleanup.py             # Task 3
│   ├── recognize.py                # Task 4
│   └── workdir.py                  # Task 5
├── kitabim_client/
│   ├── __init__.py
│   ├── auth.py                     # Task 6
│   └── api.py                      # Task 7
├── preview/
│   ├── __init__.py
│   └── server.py                   # Task 8
└── tests/
    ├── engine/
    │   ├── test_text_cleanup.py
    │   ├── test_recognize.py
    │   └── test_workdir.py
    ├── kitabim_client/
    │   ├── test_auth.py
    │   └── test_api.py
    ├── preview/
    │   └── test_server.py
    └── test_cli.py
```

**Interfaces at a glance** (exact signatures, so later tasks can be implemented without re-reading earlier ones):

```python
# engine/text_cleanup.py
def normalize_uyghur_chars(text: str) -> str
def clean_uyghur_text(text: str) -> str
def is_toc_page(text: str) -> bool
def is_degenerate_ocr_output(text: str) -> bool

# engine/recognize.py
class LowConfidenceOcrError(Exception): ...
async def get_recognition_predictor() -> "RecognitionPredictor"
async def ocr_page_with_surya(
    page: "fitz.Page",
    recognition_predictor: "RecognitionPredictor",
    timeout: float | None = None,
    *,
    max_parallel_pages: int = 1,
    min_confidence: float = 0.3,
) -> str

# engine/workdir.py
@dataclass
class PageState:
    page_number: int
    text: str
    is_toc: bool
    confidence: float
    status: str   # "pending" | "ocrd" | "reviewed" | "failed"
    error: str | None = None   # set when status == "failed"

class OcrWorkDir:
    path: Path
    source_pdf: Path
    book_id: str | None
    total_pages: int
    @classmethod
    def create(cls, path: Path, source_pdf: Path, total_pages: int, book_id: str | None = None) -> "OcrWorkDir": ...
    @classmethod
    def load(cls, path: Path) -> "OcrWorkDir": ...
    def save(self) -> None: ...
    def image_path(self, page_number: int) -> Path: ...
    def get_page(self, page_number: int) -> PageState: ...
    def set_page(self, page_number: int, *, text: str, is_toc: bool, confidence: float, status: str, error: str | None = None) -> None: ...
    def all_pages(self) -> list[PageState]: ...

# kitabim_client/auth.py
class AuthError(Exception): ...
def get_valid_token(base_url: str, config_path: Path, provider: str = "google") -> str

# kitabim_client/api.py
class KitabimAPIError(Exception): ...
class KitabimClient:
    def __init__(self, base_url: str, config_path: Path, provider: str = "google") -> None: ...
    def push_new_book(self, pdf_path: Path, pages: list["PageState"]) -> dict: ...
    def push_page_correction(self, book_id: str, page: "PageState") -> dict: ...
    def download_book_pdf(self, book_id: str, dest: Path) -> Path: ...
    def get_book_pages(self, book_id: str) -> list[dict]: ...

# preview/server.py
def create_app(workdir: "OcrWorkDir", client: "KitabimClient | None") -> "FastAPI"
def serve(workdir: "OcrWorkDir", client: "KitabimClient | None", port: int = 8765, open_browser: bool = True) -> None

# cli.py — argparse subcommands: ocr, preview, push, correct
```

---

## Task 1: Backend — `OcrPageInput` schema + i18n error keys

**Files:**
- Modify: `packages/backend-core/app/models/schemas.py`
- Modify: `services/backend/locales/en.json`
- Modify: `services/backend/locales/ug.json`
- Test: `packages/backend-core/tests/app/models/schemas_test.py` (create if it doesn't exist)

**Interfaces:**
- Produces: `OcrPageInput` (pydantic model), importable as `from app.models.schemas import OcrPageInput`. Fields: `page_number: int`, `text: str`, `is_toc: bool = False`. Consumed by Task 2.
- Produces: i18n keys `errors.invalid_pages_payload` and `errors.pages_count_mismatch`, consumed by Task 2 via `t(...)`.

- [ ] **Step 1: Check whether a schema test file already exists**

Run: `ls packages/backend-core/tests/app/models/ 2>/dev/null`

If `schemas_test.py` doesn't exist, this task creates it. If it exists, add the new test function to it instead of creating a new file.

- [ ] **Step 2: Write the failing test**

Create/append to `packages/backend-core/tests/app/models/schemas_test.py`:

```python
from app.models.schemas import OcrPageInput


def test_ocr_page_input_accepts_camel_case_payload():
    page = OcrPageInput.model_validate(
        {"pageNumber": 3, "text": "سالام دۇنيا", "isToc": True}
    )
    assert page.page_number == 3
    assert page.text == "سالام دۇنيا"
    assert page.is_toc is True


def test_ocr_page_input_is_toc_defaults_false():
    page = OcrPageInput.model_validate({"pageNumber": 1, "text": ""})
    assert page.is_toc is False
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd packages/backend-core && python -m pytest tests/app/models/schemas_test.py -v`
Expected: FAIL with `ImportError: cannot import name 'OcrPageInput'`

- [ ] **Step 4: Add the schema**

In `packages/backend-core/app/models/schemas.py`, add immediately after the `PageTocUpdate` class (which already shows the exact convention — `alias_generator=to_camel, populate_by_name=True`):

```python
class OcrPageInput(BaseModel):
    """One page's pre-OCR'd content, for POST /books/upload-ocrd."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    page_number: int  # API: pageNumber
    text: str
    is_toc: bool = False  # API: isToc
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd packages/backend-core && python -m pytest tests/app/models/schemas_test.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Add the i18n error keys**

In `services/backend/locales/en.json`, inside the `"errors"` object, add:

```json
    "invalid_pages_payload": "Invalid pages payload: must be a JSON array of {{pageNumber, text, isToc}}",
    "pages_count_mismatch": "Pages array must cover every page from 1 to {total} exactly once (got {count} entries for a {total}-page PDF)",
```

In `services/backend/locales/ug.json`, inside the `"errors"` object, add (draft machine-assisted translation — **flag for the user to review before this is considered final**, per this project's standing preference to defer Uyghur translation quality to a native speaker rather than trust automated output):

```json
    "invalid_pages_payload": "ئىناۋەتسىز بەت مەزمۇنى: چوقۇم {{pageNumber, text, isToc}} گۇرۇپپىسىدىن تۈزۈلگەن JSON بولۇشى كېرەك",
    "pages_count_mismatch": "بەتلەر گۇرۇپپىسى 1 دىن {total} گىچە بولغان ھەممە بەتنى بىر قېتىمدىن ئۆز ئىچىگە ئېلىشى كېرەك ({total} بەتلىك PDF ئۈچۈن {count} تۈر تاپشۇرۇلدى)",
```

- [ ] **Step 7: Verify both locale files are still valid JSON**

Run: `python3 -c "import json; json.load(open('services/backend/locales/en.json')); json.load(open('services/backend/locales/ug.json')); print('ok')"`
Expected: `ok`

- [ ] **Step 8: Commit**

```bash
git add packages/backend-core/app/models/schemas.py \
        packages/backend-core/tests/app/models/schemas_test.py \
        services/backend/locales/en.json services/backend/locales/ug.json
git commit -m "feat(api): add OcrPageInput schema and upload-ocrd error strings"
```

---

## Task 2: Backend — `POST /books/upload-ocrd` endpoint

**Files:**
- Modify: `services/backend/api/endpoints/books_router.py`
- Test: `services/backend/tests/api/endpoints/books_router_test.py`

**Interfaces:**
- Consumes: `OcrPageInput` from Task 1 (`app.models.schemas`), `t("errors.invalid_pages_payload")` / `t("errors.pages_count_mismatch")` from Task 1.
- Produces: `POST /books/upload-ocrd` — response `{"bookId": str, "status": "uploaded" | "existing"}`, consumed by the client's `kitabim_client/api.py` (Task 7).

- [ ] **Step 1: Write the failing tests**

Add to `services/backend/tests/api/endpoints/books_router_test.py` (same direct-call pattern as `test_upload_pdf_exceeds_size_limit` above it — call the endpoint function directly with mocked dependencies, no TestClient/DB needed):

```python
@pytest.mark.asyncio
async def test_upload_ocrd_rejects_page_count_mismatch():
    setup_paths()
    from api.endpoints.books_router import upload_pdf_ocrd
    import fitz

    # A real 1-page PDF so read_pdf_page_count() sees total_pages=1.
    doc = fitz.open()
    doc.new_page()
    pdf_bytes = doc.tobytes()
    doc.close()

    mock_file = AsyncMock()
    mock_file.filename = "book.pdf"
    mock_file.read = AsyncMock(side_effect=[pdf_bytes, b""])

    mock_user = MagicMock()
    mock_user.email = "editor@example.com"
    mock_session = AsyncMock()

    with patch("api.endpoints.books_router.BooksRepository", return_value=MagicMock()):
        with pytest.raises(HTTPException) as excinfo:
            await upload_pdf_ocrd(
                file=mock_file,
                pages='[{"pageNumber": 1, "text": "a"}, {"pageNumber": 2, "text": "b"}]',
                current_user=mock_user,
                session=mock_session,
            )

    assert excinfo.value.status_code == 400


@pytest.mark.asyncio
async def test_upload_ocrd_rejects_invalid_pages_json():
    setup_paths()
    from api.endpoints.books_router import upload_pdf_ocrd
    import fitz

    doc = fitz.open()
    doc.new_page()
    pdf_bytes = doc.tobytes()
    doc.close()

    mock_file = AsyncMock()
    mock_file.filename = "book.pdf"
    mock_file.read = AsyncMock(side_effect=[pdf_bytes, b""])

    mock_user = MagicMock()
    mock_user.email = "editor@example.com"
    mock_session = AsyncMock()

    with patch("api.endpoints.books_router.BooksRepository", return_value=MagicMock()):
        with pytest.raises(HTTPException) as excinfo:
            await upload_pdf_ocrd(
                file=mock_file,
                pages="not json",
                current_user=mock_user,
                session=mock_session,
            )

    assert excinfo.value.status_code == 400


@pytest.mark.asyncio
async def test_upload_ocrd_returns_existing_book_on_duplicate_hash():
    setup_paths()
    from api.endpoints.books_router import upload_pdf_ocrd
    import fitz

    doc = fitz.open()
    doc.new_page()
    pdf_bytes = doc.tobytes()
    doc.close()

    mock_file = AsyncMock()
    mock_file.filename = "book.pdf"
    mock_file.read = AsyncMock(side_effect=[pdf_bytes, b""])

    mock_user = MagicMock()
    mock_user.email = "editor@example.com"
    mock_session = AsyncMock()

    existing_book = MagicMock()
    existing_book.id = "existingid123"
    mock_repo = MagicMock()
    mock_repo.find_by_hash = AsyncMock(return_value=existing_book)

    with patch("api.endpoints.books_router.BooksRepository", return_value=mock_repo):
        result = await upload_pdf_ocrd(
            file=mock_file,
            pages='[{"pageNumber": 1, "text": "a"}]',
            current_user=mock_user,
            session=mock_session,
        )

    assert result == {"bookId": "existingid123", "status": "existing"}


@pytest.mark.asyncio
async def test_upload_ocrd_creates_book_with_prefilled_pages_on_success():
    setup_paths()
    from api.endpoints.books_router import upload_pdf_ocrd
    from app.core.pipeline import PAGE_MILESTONE_SUCCEEDED, PIPELINE_STEP_CHUNKING
    import fitz

    doc = fitz.open()
    doc.new_page()
    doc.new_page()
    pdf_bytes = doc.tobytes()
    doc.close()

    mock_file = AsyncMock()
    mock_file.filename = "my book.pdf"
    mock_file.read = AsyncMock(side_effect=[pdf_bytes, b""])

    mock_user = MagicMock()
    mock_user.email = "editor@example.com"
    mock_session = AsyncMock()

    mock_repo = MagicMock()
    mock_repo.find_by_hash = AsyncMock(return_value=None)
    mock_repo.create = AsyncMock()

    with (
        patch("api.endpoints.books_router.BooksRepository", return_value=mock_repo),
        patch("api.endpoints.books_router.storage") as mock_storage,
        patch("api.endpoints.books_router.cache_service") as mock_cache,
    ):
        mock_storage.upload_file = AsyncMock()
        mock_cache.bump_namespace_version = AsyncMock()

        result = await upload_pdf_ocrd(
            file=mock_file,
            pages=(
                '[{"pageNumber": 1, "text": "first page", "isToc": false},'
                ' {"pageNumber": 2, "text": "second page", "isToc": true}]'
            ),
            current_user=mock_user,
            session=mock_session,
        )

    assert result["status"] == "uploaded"
    assert "bookId" in result

    create_kwargs = mock_repo.create.call_args.kwargs
    assert create_kwargs["source"] == "surya_local"
    assert create_kwargs["ocr_milestone"] == "complete"
    assert create_kwargs["pipeline_step"] == PIPELINE_STEP_CHUNKING
    assert create_kwargs["total_pages"] == 2

    added_pages = [
        call.args[0]
        for call in mock_session.add.call_args_list
    ] + [
        p for call in mock_session.add_all.call_args_list for p in call.args[0]
    ]
    assert len(added_pages) == 2
    by_number = {p.page_number: p for p in added_pages}
    assert by_number[1].text == "first page"
    assert by_number[1].is_toc is False
    assert by_number[2].text == "second page"
    assert by_number[2].is_toc is True
    assert all(p.ocr_milestone == PAGE_MILESTONE_SUCCEEDED for p in added_pages)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd services/backend && python -m pytest tests/api/endpoints/books_router_test.py -k upload_ocrd -v`
Expected: FAIL with `ImportError: cannot import name 'upload_pdf_ocrd'`

- [ ] **Step 3: Implement the endpoint**

In `services/backend/api/endpoints/books_router.py`, add `import json` to the existing `import json` line (it's already imported at the bottom of the import block — confirm, don't duplicate), add `Form` to the existing `fastapi` import group, add `OcrPageInput` to the existing `from app.models.schemas import (...)` block, then add the endpoint immediately after `upload_pdf` (after its closing `return {"bookId": book_id, "status": "uploaded"}` at line ~1693):

```python
@router.post("/upload-ocrd")
async def upload_pdf_ocrd(
    file: UploadFile = File(...),
    pages: str = Form(...),
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Upload a PDF whose OCR has already been done externally (e.g. the
    local Surya OCR client). Pages arrive pre-filled and the book enters
    the pipeline at chunking, the same shape DOCX uploads already use."""
    from pydantic import TypeAdapter, ValidationError

    try:
        raw_pages = json.loads(pages)
        pages_data = TypeAdapter(List[OcrPageInput]).validate_python(raw_pages)
    except (json.JSONDecodeError, ValidationError):
        raise HTTPException(
            status_code=400, detail=t("errors.invalid_pages_payload")
        )

    books_repo = BooksRepository(session)

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400, detail=t("errors.invalid_file_type", allowed=".pdf")
        )

    temp_path = settings.uploads_dir / f".upload_{uuid.uuid4().hex}.pdf"
    hasher = hashlib.sha256()
    total_bytes = 0
    try:
        with open(temp_path, "wb") as handle:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > settings.max_book_upload_bytes:
                    handle.close()
                    temp_path.unlink(missing_ok=True)
                    max_mb = settings.max_book_upload_bytes // (1024 * 1024)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File size exceeds maximum limit of {max_mb}MB",
                    )
                hasher.update(chunk)
                handle.write(chunk)

        content_hash = hasher.hexdigest()

        existing = await books_repo.find_by_hash(content_hash)
        if existing:
            temp_path.unlink(missing_ok=True)
            return {"bookId": str(existing.id), "status": "existing"}

        page_count = read_pdf_page_count(temp_path)
        expected_numbers = set(range(1, page_count + 1))
        got_numbers = {p.page_number for p in pages_data}
        if len(pages_data) != page_count or got_numbers != expected_numbers:
            temp_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=400,
                detail=t(
                    "errors.pages_count_mismatch",
                    total=page_count,
                    count=len(pages_data),
                ),
            )

        book_id = secrets.token_hex(6)
        remote_path = f"uploads/{book_id}.pdf"
        cover_url = None
        cover_temp_path = settings.uploads_dir / f".cover_{book_id}.jpg"

        if extract_pdf_cover(temp_path, cover_temp_path):
            try:
                remote_cover_path = f"covers/{book_id}.jpg"
                await storage.upload_file(cover_temp_path, remote_cover_path)
                cover_url = remote_cover_path
            finally:
                cover_temp_path.unlink(missing_ok=True)
        await storage.upload_file(temp_path, remote_path)
        temp_path.unlink(missing_ok=True)

    except HTTPException:
        raise
    except Exception:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise

    now = datetime.now(timezone.utc)
    ext = ".pdf"
    title_raw = file.filename[: file.filename.lower().rfind(ext)]

    await books_repo.create(
        id=book_id,
        content_hash=content_hash,
        title=normalize_uyghur_chars(title_raw),
        file_name=file.filename,
        file_type="pdf",
        author="",
        volume=None,
        total_pages=page_count,
        cover_url=cover_url,
        status="ocr_done",
        pipeline_step=PIPELINE_STEP_CHUNKING,
        upload_date=now,
        last_updated=now,
        created_by=current_user.email,
        updated_by=current_user.email,
        categories=[],
        visibility="private",
        source="surya_local",
        ocr_milestone="complete",
        chunking_milestone=PAGE_MILESTONE_IDLE,
        embedding_milestone=PAGE_MILESTONE_IDLE,
        spell_check_milestone=PAGE_MILESTONE_IDLE,
    )

    pages_by_number = {p.page_number: p for p in pages_data}
    session.add_all(
        [
            Page(
                book_id=book_id,
                page_number=n,
                text=pages_by_number[n].text,
                is_toc=pages_by_number[n].is_toc,
                pipeline_step=PIPELINE_STEP_CHUNKING,
                milestone=PAGE_MILESTONE_IDLE,
                status="ocr_done",
                ocr_milestone=PAGE_MILESTONE_SUCCEEDED,
                chunking_milestone=PAGE_MILESTONE_IDLE,
                embedding_milestone=PAGE_MILESTONE_IDLE,
                spell_check_milestone=PAGE_MILESTONE_IDLE,
            )
            for n in range(1, page_count + 1)
        ]
    )

    await session.commit()

    await cache_service.bump_namespace_version("books:list")
    await cache_service.bump_namespace_version("category")

    return {"bookId": book_id, "status": "uploaded"}
```

Then update the two import lines noted above:

```python
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
)
```

```python
from app.models.schemas import (
    Book,
    PaginatedBooks,
    ContentSearchHit,
    PaginatedContentHits,
    ExtractionResult,
    OcrPageInput,
    PageTocUpdate,
    to_camel,
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd services/backend && python -m pytest tests/api/endpoints/books_router_test.py -k upload_ocrd -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full books router test file to check for regressions**

Run: `cd services/backend && python -m pytest tests/api/endpoints/books_router_test.py -v`
Expected: PASS (all tests, including the pre-existing ones)

- [ ] **Step 6: Regenerate the OpenAPI spec** (this project checks it via `scripts/check_openapi.py` — see `docs/main` sync conventions)

Run: `python scripts/generate_openapi.py` (from repo root; skip if the script requires a running backend and none is available locally — note this in the commit message instead)

- [ ] **Step 7: Commit**

```bash
git add services/backend/api/endpoints/books_router.py \
        services/backend/tests/api/endpoints/books_router_test.py
git add -A openapi.json 2>/dev/null || true
git commit -m "feat(api): add POST /books/upload-ocrd for pre-OCR'd PDF ingestion"
```

---

## Task 3: Client — scaffold `clients/surya-ocr/`

**Files:**
- Create: `clients/surya-ocr/requirements.txt`
- Create: `clients/surya-ocr/pytest.ini`
- Create: `clients/surya-ocr/README.md`
- Create: `clients/surya-ocr/engine/__init__.py`
- Create: `clients/surya-ocr/kitabim_client/__init__.py`
- Create: `clients/surya-ocr/preview/__init__.py`

**Interfaces:**
- Produces: the directory/package skeleton every later task writes into. No code logic in this task.

- [ ] **Step 1: Create the directory structure and empty package markers**

```bash
mkdir -p clients/surya-ocr/engine clients/surya-ocr/kitabim_client clients/surya-ocr/preview
mkdir -p clients/surya-ocr/tests/engine clients/surya-ocr/tests/kitabim_client clients/surya-ocr/tests/preview
touch clients/surya-ocr/engine/__init__.py
touch clients/surya-ocr/kitabim_client/__init__.py
touch clients/surya-ocr/preview/__init__.py
```

- [ ] **Step 2: Write `requirements.txt`**

```
surya-ocr==0.22.1
pymupdf
pillow
beautifulsoup4
fastapi
uvicorn
httpx
pytest
pytest-asyncio
```

- [ ] **Step 3: Write `pytest.ini`**

```ini
[pytest]
pythonpath = .
asyncio_mode = auto
asyncio_default_fixture_loop_scope = function
```

- [ ] **Step 4: Write `README.md`**

```markdown
# Surya OCR Client

Standalone desktop tool: runs Surya OCR locally on your own hardware (no
Docker, full GPU/CPU access), lets you preview and redo pages before
committing, then pushes finished text to Kitabim over its public API.
Kitabim's own OCR stage (Gemini, in `services/worker`) is unaffected —
this tool only ever talks to Kitabim's HTTP API as an authenticated
editor/admin user.

## Setup

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

## Usage

    python cli.py ocr /path/to/book.pdf          # OCR + open local preview
    python cli.py preview <workdir>               # reopen a previous session
    python cli.py push <workdir> --base-url https://api.kitabim.ai
    python cli.py correct <book_id> --base-url https://api.kitabim.ai

See `docs/superpowers/specs/2026-08-30-surya-ocr-client-design.md` in the
main kitabim-ai repo for the full design.
```

- [ ] **Step 5: Verify pytest collects (and finds zero tests, which is expected)**

Run: `cd clients/surya-ocr && python -m pytest --collect-only`
Expected: `no tests ran` (no errors)

- [ ] **Step 6: Commit**

```bash
git add clients/surya-ocr/
git commit -m "chore(surya-ocr-client): scaffold standalone client package"
```

---

## Task 4: Client — vendor `engine/text_cleanup.py`

**Files:**
- Create: `clients/surya-ocr/engine/text_cleanup.py`
- Test: `clients/surya-ocr/tests/engine/test_text_cleanup.py`

**Interfaces:**
- Produces: `normalize_uyghur_chars`, `clean_uyghur_text`, `is_toc_page`, `is_degenerate_ocr_output` — all pure functions, `str -> str` / `str -> bool`. Consumed by Task 5 (`engine/recognize.py`).

This is a vendored copy of four functions from `packages/backend-core/app/utils/text.py` (stdlib-only: `re`, `unicodedata`, `collections.Counter` — no backend-core dependency to inherit). Copy them verbatim; do not "improve" them here — any behavior change should happen in the source of truth (`packages/backend-core`) first, so the two don't silently diverge in ways nobody notices.

- [ ] **Step 1: Write the failing tests**

Create `clients/surya-ocr/tests/engine/test_text_cleanup.py`:

```python
from engine.text_cleanup import (
    normalize_uyghur_chars,
    clean_uyghur_text,
    is_toc_page,
    is_degenerate_ocr_output,
)


def test_normalize_uyghur_chars_removes_zero_width_chars():
    assert normalize_uyghur_chars("سا‌لام") == "سالام"


def test_clean_uyghur_text_strips_header_footer_markers():
    result = clean_uyghur_text("بۇ مەزمۇن.[Footer] 3")
    assert "[Footer]" not in result
    assert "3" not in result


def test_clean_uyghur_text_empty_input():
    assert clean_uyghur_text("") == ""


def test_is_toc_page_detects_munderije_keyword():
    assert is_toc_page("مۇندەرىجە\nباب بىر") is True


def test_is_toc_page_false_for_plain_paragraph():
    assert is_toc_page("بۇ ئادەتتىكى بىر پارچە تېكىست.") is False


def test_is_degenerate_ocr_output_flags_repeated_word():
    text = " ".join(["مۇزىكا"] * 300)
    assert is_degenerate_ocr_output(text) is True


def test_is_degenerate_ocr_output_false_for_normal_text():
    assert is_degenerate_ocr_output("بۇ ئادەتتىكى بىر پارچە تېكىست.") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd clients/surya-ocr && python -m pytest tests/engine/test_text_cleanup.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.text_cleanup'`

- [ ] **Step 3: Write the vendored implementation**

Create `clients/surya-ocr/engine/text_cleanup.py` — copy verbatim from `packages/backend-core/app/utils/text.py`, keeping only the four functions this client needs (`normalize_uyghur_chars`, `clean_uyghur_text`, `is_toc_page`, `is_degenerate_ocr_output`) plus their private helpers/module-level constants:

```python
"""Vendored from packages/backend-core/app/utils/text.py (kitabim-ai main
repo). Copied, not imported, so this client stays free of backend-core's
FastAPI/SQLAlchemy/Neo4j dependency chain. Keep in sync manually if the
source functions change — the source of truth is the main repo."""

import re
import unicodedata
from collections import Counter

_PRES_FORM_MAP: dict[int, str] = {}
for _cp in range(0xFB50, 0xFE00):
    _nf = unicodedata.normalize("NFKC", chr(_cp))
    if _nf != chr(_cp):
        _PRES_FORM_MAP[_cp] = _nf
for _cp in range(0xFE70, 0xFF00):
    _nf = unicodedata.normalize("NFKC", chr(_cp))
    if _nf != chr(_cp):
        _PRES_FORM_MAP[_cp] = _nf


def normalize_uyghur_chars(text: str) -> str:
    if not text:
        return ""

    text = "".join(_PRES_FORM_MAP.get(ord(c), c) for c in text)

    return (
        text.replace("ئ", "ئ")
        .replace("‌", "")
        .replace("‍", "")
        .replace("​", "")
        .replace("ـ", "")
    )


_OCR_MARKER_RE = re.compile(r"\s*\[(?:Header|Footer)\].*", re.IGNORECASE)


def clean_uyghur_text(text: str) -> str:
    if not text:
        return ""

    text = normalize_uyghur_chars(text)

    text = "\n".join(_OCR_MARKER_RE.sub("", line) for line in text.splitlines())

    text = re.sub(r"(\w)[-—–_]\s*\n\s*(\w)", r"\1\2", text)
    text = re.sub(r"(\w)[-—–_]\s*\n\s*", r"\1", text)
    text = re.sub(r"ـ+\s*\n\s*", "", text)

    blocks = re.split(r"\n\s*\n", text)
    cleaned_blocks = []

    dot_leader_pattern = re.compile(r"(?:[\.·•∙⋅․﹒｡]\s*){3,}|…{2,}")
    list_marker_pattern = re.compile(r"^\s*([-—–*•]|\d+[.)])\s+")
    header_prefixes = ("[Header]", "[Footer]", "#", "|")

    for block in blocks:
        if not block.strip():
            continue

        lines = [line.rstrip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue

        result_block = ""
        for idx, line in enumerate(lines):
            if idx < len(lines) - 1:
                next_line = lines[idx + 1]
                is_ending = re.search(r"[.؟!:؛»\"”)\]}﴾﴿…]\s*$", line)

                raw_next = next_line.lstrip()
                is_list_marker = raw_next and raw_next[0] in "-—–*•"
                is_digit_marker = (
                    raw_next
                    and raw_next[0].isdigit()
                    and (len(raw_next) > 1 and raw_next[1] in ". )")
                )

                is_new_item = is_ending and (is_list_marker or is_digit_marker)

                raw_line = line.lstrip()
                is_markdown_list = bool(list_marker_pattern.match(raw_line))
                is_markdown_header = raw_line.startswith(header_prefixes)
                is_toc_line = bool(dot_leader_pattern.search(line))

                if (
                    is_markdown_list
                    or is_markdown_header
                    or is_toc_line
                    or is_ending
                    or is_new_item
                    or is_list_marker
                    or is_digit_marker
                ):
                    result_block += line + "\n"
                else:
                    result_block += line + " "
            else:
                result_block += line

        cleaned_blocks.append(result_block)

    return "\n\n".join(cleaned_blocks)


def is_toc_page(text: str) -> bool:
    if not text:
        return False

    if "مۇندەرىجە" in text:
        return True

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not lines:
        return False

    pipe_table_pattern = re.compile(r"^\|.*\|\s*\d+\s*\|?$")
    pipe_count = sum(1 for line in lines if pipe_table_pattern.match(line))
    if pipe_count >= 5 and (pipe_count / len(lines)) >= 0.5:
        return True

    dot_leader_pattern = re.compile(r"(\.{6,}|_{6,}|-{6,}|·{6,})")

    dot_digit_count = 0
    edge_digits = []

    for line in lines:
        has_dots = bool(dot_leader_pattern.search(line))
        digit_match = re.search(r"(^\d+)|(\d+$)", line)

        if has_dots and digit_match:
            dot_digit_count += 1
            edge_digits.append(int(digit_match.group()))
        elif digit_match:
            edge_digits.append(int(digit_match.group()))

    if len(edge_digits) >= 5 and dot_digit_count >= 3:
        non_decreasing = sum(
            1
            for i in range(len(edge_digits) - 1)
            if edge_digits[i + 1] >= edge_digits[i]
        )
        is_increasing = (non_decreasing / (len(edge_digits) - 1)) >= 0.8

        if is_increasing and dot_digit_count >= (len(lines) * 0.3):
            return True

    if dot_digit_count >= 5 and (dot_digit_count / len(lines)) >= 0.5:
        return True

    return False


_MAX_SANE_OCR_CHARS = 10000


def is_degenerate_ocr_output(text: str) -> bool:
    if not text:
        return False
    if len(text) > _MAX_SANE_OCR_CHARS:
        return True

    words = [w for w in text.split() if any(ch.isalnum() for ch in w)]
    if len(words) < 50:
        return False
    _, most_common_count = Counter(words).most_common(1)[0]
    return most_common_count >= 50 and most_common_count / len(words) >= 0.3
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd clients/surya-ocr && python -m pytest tests/engine/test_text_cleanup.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add clients/surya-ocr/engine/text_cleanup.py clients/surya-ocr/tests/engine/test_text_cleanup.py
git commit -m "feat(surya-ocr-client): vendor Uyghur text-cleanup helpers"
```

---

## Task 5: Client — vendor `engine/recognize.py`

**Files:**
- Create: `clients/surya-ocr/engine/recognize.py`
- Test: `clients/surya-ocr/tests/engine/test_recognize.py`

**Interfaces:**
- Consumes: `clean_uyghur_text`, `is_degenerate_ocr_output` from Task 4 (`engine.text_cleanup`).
- Produces: `LowConfidenceOcrError`, `get_recognition_predictor()`, `ocr_page_with_surya(page, recognition_predictor, timeout=None, *, max_parallel_pages=1, min_confidence=0.3) -> str`. Consumed by Task 9 (`cli.py`) and Task 8 (`preview/server.py`'s redo action).

This is a vendored, adapted copy of `packages/backend-core/app/services/surya_service.py` (validated on `poc/easy-ocr-v2`, not present on `main`). Two adaptations from the original: (1) `from app.core.config import settings` becomes two local module constants, since the client has no `app.core.config`; (2) the `correction_pairs` parameter is dropped — those pairs come from `AutoCorrectRulesRepository`, a database table this standalone client has no access to, and Kitabim's own `auto_correct_scanner` already applies the same corrections post-ingestion regardless of which engine produced the text (see `docs/main/OCR_DESIGN.md`), so nothing is lost by dropping it here.

- [ ] **Step 1: Write the failing tests**

Create `clients/surya-ocr/tests/engine/test_recognize.py` (adapted from the reference test suite validated on `poc/easy-ocr-v2` — same test names/shapes, `correction_pairs` tests dropped since that parameter doesn't exist in this vendored version, and the `settings.ocr_max_retries`/`settings.ocr_page_zoom_factor` patches become direct patches of this module's own constants):

```python
import io

import pytest
from unittest.mock import MagicMock, patch

from PIL import Image

import engine.recognize as svc


@pytest.fixture(autouse=True)
def reset_singleton():
    svc._recognition_predictor = None
    yield
    svc._recognition_predictor = None


def _fake_png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (10, 10)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_get_recognition_predictor_constructs_once_and_caches():
    with patch("engine.recognize.RecognitionPredictor") as mock_cls:
        mock_cls.return_value = "predictor-instance"
        p1 = await svc.get_recognition_predictor()
        p2 = await svc.get_recognition_predictor()
    assert p1 == "predictor-instance"
    assert p1 is p2
    mock_cls.assert_called_once_with()


def test_recognize_page_calls_predictor_full_page_and_returns_first_result():
    mock_predictor = MagicMock()
    mock_result = MagicMock()
    mock_predictor.return_value = [mock_result]

    result = svc.recognize_page(mock_predictor, image="fake-image")

    mock_predictor.assert_called_once_with(["fake-image"], full_page=True)
    assert result is mock_result


def test_label_sets_are_disjoint():
    assert not (svc.FOOTNOTE_LABELS & svc.DISCARD_LABELS)


def test_is_page_blank_true_for_uniform_pixels():
    pix = MagicMock()
    pix.samples = bytes([200] * 3000)
    assert svc.is_page_blank(pix) is True


def test_is_page_blank_false_for_varied_pixels():
    pix = MagicMock()
    pix.samples = bytes(([10, 250] * 1500))
    assert svc.is_page_blank(pix) is False


def _block(label, html, position=0, skipped=False, error=False, confidence=0.9):
    b = MagicMock()
    b.label = label
    b.html = html
    b.reading_order = position
    b.skipped = skipped
    b.error = error
    b.confidence = confidence
    return b


def test_process_page_sync_renders_each_block_type_and_appends_footnotes_last():
    img = Image.new("RGB", (200, 200))
    mock_predictor = MagicMock()
    mock_result = MagicMock()
    mock_result.blocks = [
        _block("SectionHeader", "<h1>چوڭ ماۋزۇ</h1>", position=0),
        _block("Text", "<p>بۇ ئادەتتىكى تېكىست.</p>", position=1),
        _block("TableOfContents", "<ol><li>3 ..... باب بىر</li></ol>", position=2),
        _block("Footnote", "<p>پايدىلانما 12</p>", position=3),
        _block("Picture", "", position=4, skipped=True),
    ]

    with patch("engine.recognize.recognize_page", return_value=mock_result):
        markdown, mean_conf = svc._process_page_sync(img, mock_predictor)

    blocks = markdown.split("\n\n")
    assert blocks[0] == "# چوڭ ماۋزۇ"
    assert blocks[1] == "بۇ ئادەتتىكى تېكىست."
    assert blocks[2] == "| باب بىر | 3 |"
    assert blocks[3] == "پايدىلانما 12"
    assert mean_conf == 0.9


def test_process_page_sync_skips_discarded_and_errored_blocks():
    img = Image.new("RGB", (200, 200))
    mock_predictor = MagicMock()
    mock_result = MagicMock()
    mock_result.blocks = [
        _block("PageHeader", "<p>running header</p>", position=0),
        _block("PageFooter", "<p>3</p>", position=1),
        _block("Text", "<p>real content</p>", position=2, error=True),
        _block("Text", "<p>good content</p>", position=3),
    ]

    with patch("engine.recognize.recognize_page", return_value=mock_result):
        markdown, _ = svc._process_page_sync(img, mock_predictor)

    assert markdown == "good content"


@pytest.mark.asyncio
async def test_ocr_page_with_surya_happy_path():
    mock_page = MagicMock()
    mock_pix = MagicMock()
    mock_pix.samples = bytes(([10, 250] * 1500))
    mock_pix.tobytes.return_value = _fake_png_bytes()
    mock_page.get_pixmap.return_value = mock_pix

    with (
        patch("engine.recognize._process_page_sync", return_value=("متن", 0.9)),
        patch("engine.recognize.clean_uyghur_text", side_effect=lambda t: t),
    ):
        result = await svc.ocr_page_with_surya(mock_page, MagicMock(), min_confidence=0.3)

    assert result == "متن"


@pytest.mark.asyncio
async def test_ocr_page_with_surya_blank_page_returns_empty_without_processing():
    mock_page = MagicMock()
    mock_pix = MagicMock()
    mock_pix.samples = bytes([128] * 3000)
    mock_page.get_pixmap.return_value = mock_pix

    with patch("engine.recognize._process_page_sync") as mock_process:
        result = await svc.ocr_page_with_surya(mock_page, MagicMock())

    assert result == ""
    mock_process.assert_not_called()


@pytest.mark.asyncio
async def test_ocr_page_with_surya_retries_on_low_confidence():
    mock_page = MagicMock()
    mock_pix = MagicMock()
    mock_pix.samples = bytes(([10, 250] * 1500))
    mock_pix.tobytes.return_value = _fake_png_bytes()
    mock_page.get_pixmap.return_value = mock_pix

    with (
        patch(
            "engine.recognize._process_page_sync",
            return_value=("low conf text", 0.1),
        ),
        patch("engine.recognize.clean_uyghur_text", side_effect=lambda t: t),
        patch("engine.recognize.OCR_MAX_RETRIES", 2),
    ):
        with pytest.raises(svc.LowConfidenceOcrError):
            await svc.ocr_page_with_surya(mock_page, MagicMock(), min_confidence=0.5)

    assert mock_page.get_pixmap.call_count == 2


@pytest.mark.asyncio
async def test_ocr_page_with_surya_retries_on_degenerate_repetition_loop():
    mock_page = MagicMock()
    mock_pix = MagicMock()
    mock_pix.samples = bytes(([10, 250] * 1500))
    mock_pix.tobytes.return_value = _fake_png_bytes()
    mock_page.get_pixmap.return_value = mock_pix

    degenerate_text = " ".join(["مۇزىكا"] * 300)

    with (
        patch(
            "engine.recognize._process_page_sync",
            return_value=(degenerate_text, 0.95),
        ),
        patch("engine.recognize.clean_uyghur_text", side_effect=lambda t: t),
        patch("engine.recognize.OCR_MAX_RETRIES", 2),
    ):
        with pytest.raises(svc.LowConfidenceOcrError):
            await svc.ocr_page_with_surya(mock_page, MagicMock(), min_confidence=0.3)

    assert mock_page.get_pixmap.call_count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd clients/surya-ocr && python -m pytest tests/engine/test_recognize.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.recognize'`

- [ ] **Step 3: Write the vendored implementation**

Create `clients/surya-ocr/engine/recognize.py`:

```python
"""Vendored/adapted from packages/backend-core/app/services/surya_service.py
(validated on the poc/easy-ocr-v2 branch of the main kitabim-ai repo, not
present on main). Two changes from the original: no app.core.config
dependency (two local constants instead), and no `correction_pairs`
parameter (that comes from a DB table this standalone client can't reach;
Kitabim's own auto_correct_scanner already applies the same corrections
post-ingestion regardless of OCR engine)."""

from __future__ import annotations

import asyncio
import io
import logging
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import TYPE_CHECKING, List, Optional, Tuple
import re

import fitz
import numpy as np
from bs4 import BeautifulSoup
from PIL import Image
from surya.recognition import RecognitionPredictor

from engine.text_cleanup import clean_uyghur_text, is_degenerate_ocr_output

if TYPE_CHECKING:
    from surya.recognition.schema import PageOCRResult

logger = logging.getLogger("surya_ocr_client.engine.recognize")

# Local equivalents of packages/backend-core's OCR_MAX_RETRIES /
# OCR_PAGE_ZOOM_FACTOR env-configured settings (defaults match main's).
OCR_MAX_RETRIES = 4
OCR_PAGE_ZOOM_FACTOR = 1.5

FOOTNOTE_LABELS = frozenset({"Footnote"})
DISCARD_LABELS = frozenset({"PageHeader", "PageFooter"})


class LowConfidenceOcrError(Exception):
    """Raised when the recognizer's mean confidence falls below the
    configured threshold on a non-blank page - triggers the varied-input
    retry, same handling path as an exception from the recognizer itself."""


_recognition_predictor: Optional["RecognitionPredictor"] = None
_recognition_predictor_lock = asyncio.Lock()
_executor: Optional[ThreadPoolExecutor] = None


async def get_recognition_predictor() -> "RecognitionPredictor":
    global _recognition_predictor
    if _recognition_predictor is not None:
        return _recognition_predictor
    async with _recognition_predictor_lock:
        if _recognition_predictor is None:
            loop = asyncio.get_running_loop()
            _recognition_predictor = await loop.run_in_executor(
                None, RecognitionPredictor
            )
    return _recognition_predictor


def recognize_page(
    predictor: "RecognitionPredictor", image: "Image.Image"
) -> "PageOCRResult":
    return predictor([image], full_page=True)[0]


def _get_executor(max_workers: int) -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(
            max_workers=max(1, max_workers), thread_name_prefix="surya_ocr"
        )
    return _executor


_BLANK_PAGE_VARIANCE_THRESHOLD = 25.0


def is_page_blank(pix: "fitz.Pixmap") -> bool:
    arr = np.frombuffer(pix.samples, dtype=np.uint8)
    if arr.size == 0:
        return True
    return float(np.var(arr)) < _BLANK_PAGE_VARIANCE_THRESHOLD


_HEADING_TAG_RE = re.compile(r"^<h([1-6])\b[^>]*>", re.IGNORECASE)
_DOT_LEADER_RE = re.compile(r"[.·•∙⋅․﹒｡\-—–_]{2,}|…{2,}")
_ROW_NUMBER_RE = re.compile(r"\d{1,4}")


def _html_to_text(html: str) -> str:
    return BeautifulSoup(html, "html.parser").get_text(separator=" ", strip=True)


def _format_table_row(item_text: str) -> str:
    number_match = _ROW_NUMBER_RE.search(item_text)
    if not number_match:
        return item_text.strip()
    value = number_match.group()
    title = item_text[: number_match.start()] + " " + item_text[number_match.end() :]
    title = _DOT_LEADER_RE.sub(" ", title)
    title = " ".join(title.split())
    if not title:
        return item_text.strip()
    return f"| {title} | {value} |"


def _html_rows_to_markdown(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    items = soup.find_all(["tr", "li"])
    if not items:
        text = soup.get_text(separator=" ", strip=True)
        return _format_table_row(text) if text else ""
    rows = [
        _format_table_row(item_text)
        for item in items
        if (item_text := item.get_text(separator=" ", strip=True))
    ]
    return "\n".join(rows)


def _block_html_to_markdown(html: str) -> str:
    heading_match = _HEADING_TAG_RE.match(html.strip())
    if heading_match:
        level = min(int(heading_match.group(1)), 6)
        return f"{'#' * level} {_html_to_text(html)}"
    if "<li" in html or "<tr" in html:
        return _html_rows_to_markdown(html)
    return _html_to_text(html)


def _process_page_sync(
    image: "Image.Image",
    recognition_predictor: "RecognitionPredictor",
) -> Tuple[str, float]:
    result = recognize_page(recognition_predictor, image)

    blocks: List[str] = []
    footnotes: List[str] = []
    confidences: List[float] = []

    for block in sorted(result.blocks, key=lambda b: b.reading_order):
        if block.confidence is not None:
            confidences.append(block.confidence)

        if block.skipped or block.error or block.label in DISCARD_LABELS:
            continue

        html = (block.html or "").strip()
        if not html:
            continue

        text = _block_html_to_markdown(html)
        if not text.strip():
            continue

        if block.label in FOOTNOTE_LABELS:
            footnotes.append(text)
        else:
            blocks.append(text)

    blocks.extend(footnotes)
    markdown = "\n\n".join(blocks)
    mean_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return markdown, mean_confidence


async def ocr_page_with_surya(
    page: "fitz.Page",
    recognition_predictor: "RecognitionPredictor",
    timeout: float | None = None,
    *,
    max_parallel_pages: int = 1,
    min_confidence: float = 0.3,
) -> str:
    executor = _get_executor(max_parallel_pages)
    loop = asyncio.get_running_loop()

    last_exc: Exception | None = None
    for attempt in range(OCR_MAX_RETRIES):
        zoom = OCR_PAGE_ZOOM_FACTOR + (attempt * 0.5)
        try:
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            if is_page_blank(pix):
                return ""

            image = Image.open(io.BytesIO(pix.tobytes("png")))

            process_fn = partial(_process_page_sync, image, recognition_predictor)
            coro = loop.run_in_executor(executor, process_fn)
            markdown, mean_confidence = await (
                asyncio.wait_for(coro, timeout=timeout) if timeout else coro
            )

            if not markdown.strip():
                raise LowConfidenceOcrError(
                    f"No text recognized on a non-blank page (attempt {attempt + 1})"
                )

            if mean_confidence < min_confidence:
                raise LowConfidenceOcrError(
                    f"Mean OCR confidence {mean_confidence:.2f} below "
                    f"threshold {min_confidence} (attempt {attempt + 1})"
                )

            cleaned = clean_uyghur_text(markdown)
            if is_degenerate_ocr_output(cleaned):
                raise LowConfidenceOcrError(
                    f"OCR output looks like a runaway repetition/reasoning-leak "
                    f"loop ({len(cleaned)} chars, attempt {attempt + 1})"
                )
            return cleaned

        except Exception as exc:
            last_exc = exc
            if attempt < OCR_MAX_RETRIES - 1:
                logger.warning(
                    "OCR attempt failed, retrying with adjusted render: attempt=%s error=%s",
                    attempt + 1,
                    exc,
                )
                continue
            raise
    raise last_exc  # pragma: no cover
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd clients/surya-ocr && python -m pytest tests/engine/test_recognize.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add clients/surya-ocr/engine/recognize.py clients/surya-ocr/tests/engine/test_recognize.py
git commit -m "feat(surya-ocr-client): vendor Surya recognition engine"
```

---

## Task 6: Client — `engine/workdir.py` (local on-disk state)

**Files:**
- Create: `clients/surya-ocr/engine/workdir.py`
- Test: `clients/surya-ocr/tests/engine/test_workdir.py`

**Interfaces:**
- Produces: `PageState` dataclass, `OcrWorkDir` class (see File Structure's interface block above). Consumed by Task 8 (`preview/server.py`) and Task 9 (`cli.py`).

On-disk layout: `<workdir>/book.json` (`{"source_pdf": str, "book_id": str|null, "total_pages": int}`), `<workdir>/pages.json` (list of `PageState` dicts), `<workdir>/pages/{page_number:04d}.png` (cached rendered page images, written by whoever renders them — this module doesn't render, it only tells callers where the file should live via `image_path()`).

- [ ] **Step 1: Write the failing tests**

Create `clients/surya-ocr/tests/engine/test_workdir.py`:

```python
from pathlib import Path

import pytest

from engine.workdir import OcrWorkDir, PageState


def test_create_writes_book_json_and_empty_pages(tmp_path: Path):
    wd = OcrWorkDir.create(tmp_path / "work", source_pdf=Path("book.pdf"), total_pages=3)

    assert wd.total_pages == 3
    assert wd.book_id is None
    assert wd.all_pages() == []
    assert (tmp_path / "work" / "book.json").exists()


def test_set_page_then_get_page_round_trips(tmp_path: Path):
    wd = OcrWorkDir.create(tmp_path / "work", source_pdf=Path("book.pdf"), total_pages=2)

    wd.set_page(1, text="hello", is_toc=False, confidence=0.9, status="ocrd")
    page = wd.get_page(1)

    assert page == PageState(
        page_number=1, text="hello", is_toc=False, confidence=0.9, status="ocrd", error=None
    )


def test_set_page_records_error_on_failed_status(tmp_path: Path):
    wd = OcrWorkDir.create(tmp_path / "work", source_pdf=Path("book.pdf"), total_pages=1)

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
    wd = OcrWorkDir.create(tmp_path / "work", source_pdf=Path("book.pdf"), total_pages=1)
    assert wd.image_path(7) == tmp_path / "work" / "pages" / "0007.png"


def test_get_page_missing_raises_key_error(tmp_path: Path):
    wd = OcrWorkDir.create(tmp_path / "work", source_pdf=Path("book.pdf"), total_pages=1)
    with pytest.raises(KeyError):
        wd.get_page(1)


def test_all_pages_sorted_by_page_number(tmp_path: Path):
    wd = OcrWorkDir.create(tmp_path / "work", source_pdf=Path("book.pdf"), total_pages=2)
    wd.set_page(2, text="b", is_toc=False, confidence=0.9, status="ocrd")
    wd.set_page(1, text="a", is_toc=False, confidence=0.9, status="ocrd")

    numbers = [p.page_number for p in wd.all_pages()]
    assert numbers == [1, 2]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd clients/surya-ocr && python -m pytest tests/engine/test_workdir.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.workdir'`

- [ ] **Step 3: Write the implementation**

Create `clients/surya-ocr/engine/workdir.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd clients/surya-ocr && python -m pytest tests/engine/test_workdir.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add clients/surya-ocr/engine/workdir.py clients/surya-ocr/tests/engine/test_workdir.py
git commit -m "feat(surya-ocr-client): add local work-directory state store"
```

---

## Task 7: Client — `kitabim_client/auth.py` (lazy browser OAuth login)

**Files:**
- Create: `clients/surya-ocr/kitabim_client/auth.py`
- Test: `clients/surya-ocr/tests/kitabim_client/test_auth.py`

**Interfaces:**
- Produces: `AuthError`, `get_valid_token(base_url: str, config_path: Path, provider: str = "google") -> str`. Consumed by Task 8 (`kitabim_client/api.py`).

Login flow: reads a cached token from `config_path` (a small JSON file, e.g. `~/.config/surya-ocr-client/token.json`) if present and not expired (decoded from the JWT's own `exp` claim — no signature verification needed locally, since the backend re-validates every request regardless; this decode is only for local "should I bother re-logging-in" UX). If missing/expired, opens the system browser to Kitabim's existing "mobile redirect flow" (`GET /auth/{provider}/login?redirect_uri=...`, see `docs/superpowers/specs/2026-08-30-surya-ocr-client-design.md`), runs a one-shot local HTTP server to catch the token off the redirect fragment via a tiny JS shim page, caches it, and returns it.

- [ ] **Step 1: Write the failing tests**

Create `clients/surya-ocr/tests/kitabim_client/test_auth.py`:

```python
import base64
import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from kitabim_client import auth


def _fake_jwt(exp: float) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).rstrip(b"=").decode()
    return f"{header}.{payload}.sig"


def test_jwt_exp_decodes_expiry_claim():
    token = _fake_jwt(exp=1234567890.0)
    assert auth._jwt_exp(token) == 1234567890.0


def test_jwt_exp_returns_none_for_malformed_token():
    assert auth._jwt_exp("not-a-jwt") is None


def test_get_valid_token_returns_cached_token_when_not_expired(tmp_path: Path):
    config_path = tmp_path / "token.json"
    token = _fake_jwt(exp=time.time() + 3600)
    config_path.write_text(json.dumps({"access_token": token}))

    with patch("kitabim_client.auth._login") as mock_login:
        result = auth.get_valid_token("http://localhost:8000", config_path)

    assert result == token
    mock_login.assert_not_called()


def test_get_valid_token_relogs_in_when_cached_token_expired(tmp_path: Path):
    config_path = tmp_path / "token.json"
    old_token = _fake_jwt(exp=time.time() - 10)
    config_path.write_text(json.dumps({"access_token": old_token}))

    new_token = _fake_jwt(exp=time.time() + 3600)
    with patch("kitabim_client.auth._login", return_value=new_token) as mock_login:
        result = auth.get_valid_token("http://localhost:8000", config_path)

    assert result == new_token
    mock_login.assert_called_once()
    assert json.loads(config_path.read_text())["access_token"] == new_token


def test_get_valid_token_logs_in_when_no_cache_exists(tmp_path: Path):
    config_path = tmp_path / "token.json"
    new_token = _fake_jwt(exp=time.time() + 3600)

    with patch("kitabim_client.auth._login", return_value=new_token) as mock_login:
        result = auth.get_valid_token("http://localhost:8000", config_path)

    assert result == new_token
    mock_login.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd clients/surya-ocr && python -m pytest tests/kitabim_client/test_auth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'kitabim_client.auth'`

- [ ] **Step 3: Write the implementation**

Create `clients/surya-ocr/kitabim_client/auth.py`:

```python
from __future__ import annotations

import base64
import json
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode, urlparse, parse_qs

_CALLBACK_HTML = b"""<!doctype html>
<html><body>
<p>Logging in to Kitabim...</p>
<script>
  var hash = window.location.hash.substring(1);
  fetch('/oauth-callback/token?' + hash).then(function () {
    document.body.innerHTML = '<p>Login complete. You can close this tab.</p>';
  });
</script>
</body></html>"""


class AuthError(Exception):
    """Raised when browser-based login fails or times out."""


def _jwt_exp(token: str) -> Optional[float]:
    """Decode (not verify - only used for local re-login UX) the `exp`
    claim from a JWT's payload segment."""
    try:
        payload_b64 = token.split(".")[1]
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        return float(payload["exp"])
    except Exception:
        return None


def _make_handler(result_holder: dict, done_event: threading.Event):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/oauth-callback":
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(_CALLBACK_HTML)
            elif parsed.path == "/oauth-callback/token":
                params = parse_qs(parsed.query)
                token = params.get("access_token", [None])[0]
                if token:
                    result_holder["token"] = token
                self.send_response(200)
                self.end_headers()
                done_event.set()
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass  # keep the CLI output quiet

    return Handler


def _login(base_url: str, provider: str, timeout: float = 120.0) -> str:
    done_event = threading.Event()
    result_holder: dict = {}
    handler_cls = _make_handler(result_holder, done_event)

    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    port = server.server_address[1]

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    redirect_uri = f"http://127.0.0.1:{port}/oauth-callback"
    login_url = f"{base_url}/auth/{provider}/login?" + urlencode(
        {"redirect_uri": redirect_uri}
    )
    print(f"Opening browser to log in: {login_url}")
    webbrowser.open(login_url)

    got_it = done_event.wait(timeout=timeout)
    server.shutdown()
    thread.join(timeout=5)

    if not got_it or "token" not in result_holder:
        raise AuthError("Login timed out or was cancelled")

    return result_holder["token"]


def get_valid_token(
    base_url: str, config_path: Path, provider: str = "google"
) -> str:
    if config_path.exists():
        cached = json.loads(config_path.read_text())
        token = cached.get("access_token")
        exp = _jwt_exp(token) if token else None
        if token and exp and exp > time.time() + 30:
            return token

    token = _login(base_url, provider)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps({"access_token": token}))
    return token
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd clients/surya-ocr && python -m pytest tests/kitabim_client/test_auth.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add clients/surya-ocr/kitabim_client/auth.py clients/surya-ocr/tests/kitabim_client/test_auth.py
git commit -m "feat(surya-ocr-client): add lazy browser-based OAuth login"
```

---

## Task 8: Client — `kitabim_client/api.py` (Kitabim HTTP API client)

**Files:**
- Create: `clients/surya-ocr/kitabim_client/api.py`
- Test: `clients/surya-ocr/tests/kitabim_client/test_api.py`

**Interfaces:**
- Consumes: `get_valid_token` from Task 7 (`kitabim_client.auth`), `PageState` from Task 6 (`engine.workdir`).
- Produces: `KitabimAPIError`, `KitabimClient` (see interfaces block). Consumed by Task 8's own CLI/preview server callers (Tasks 8/9... i.e. Task 9's `cli.py` and Task 8's `preview/server.py`).

- [ ] **Step 1: Write the failing tests**

Create `clients/surya-ocr/tests/kitabim_client/test_api.py`:

```python
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from engine.workdir import PageState
from kitabim_client.api import KitabimAPIError, KitabimClient


def _client(tmp_path: Path) -> KitabimClient:
    with patch("kitabim_client.api.get_valid_token", return_value="tok123"):
        return KitabimClient(
            base_url="http://localhost:8000", config_path=tmp_path / "token.json"
        )


def test_push_new_book_posts_multipart_with_pages_json(tmp_path: Path):
    client = _client(tmp_path)
    pdf_path = tmp_path / "book.pdf"
    pdf_path.write_bytes(b"%PDF-fake")
    pages = [
        PageState(page_number=1, text="hi", is_toc=False, confidence=0.9, status="reviewed"),
    ]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"bookId": "abc123", "status": "uploaded"}

    with patch("kitabim_client.api.httpx.post", return_value=mock_response) as mock_post:
        result = client.push_new_book(pdf_path, pages)

    assert result == {"bookId": "abc123", "status": "uploaded"}
    call = mock_post.call_args
    assert call.args[0] == "http://localhost:8000/books/upload-ocrd"
    assert call.kwargs["headers"]["Authorization"] == "Bearer tok123"
    assert "pages" in call.kwargs["data"]


def test_push_page_correction_calls_update_then_toc(tmp_path: Path):
    client = _client(tmp_path)
    page = PageState(page_number=5, text="corrected", is_toc=True, confidence=0.9, status="reviewed")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "page_updated"}

    with patch("kitabim_client.api.httpx.post", return_value=mock_response) as mock_post:
        client.push_page_correction("book123", page)

    urls_called = [c.args[0] for c in mock_post.call_args_list]
    assert urls_called == [
        "http://localhost:8000/books/book123/pages/5/update",
        "http://localhost:8000/books/book123/pages/5/toc",
    ]


def test_download_book_pdf_writes_response_bytes_to_dest(tmp_path: Path):
    client = _client(tmp_path)
    dest = tmp_path / "downloaded.pdf"

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"%PDF-content"

    with patch("kitabim_client.api.httpx.get", return_value=mock_response):
        result = client.download_book_pdf("book123", dest)

    assert result == dest
    assert dest.read_bytes() == b"%PDF-content"


def test_get_book_pages_loops_pagination_until_short_page(tmp_path: Path):
    client = _client(tmp_path)

    page1_response = MagicMock()
    page1_response.status_code = 200
    page1_response.json.return_value = [{"pageNumber": i} for i in range(1, 101)]

    page2_response = MagicMock()
    page2_response.status_code = 200
    page2_response.json.return_value = [{"pageNumber": 101}]

    with patch(
        "kitabim_client.api.httpx.get", side_effect=[page1_response, page2_response]
    ) as mock_get:
        result = client.get_book_pages("book123")

    assert len(result) == 101
    assert mock_get.call_count == 2


def test_error_response_raises_kitabim_api_error(tmp_path: Path):
    client = _client(tmp_path)

    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.text = "Book not found"

    with patch("kitabim_client.api.httpx.get", return_value=mock_response):
        with pytest.raises(KitabimAPIError):
            client.download_book_pdf("missing", tmp_path / "x.pdf")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd clients/surya-ocr && python -m pytest tests/kitabim_client/test_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'kitabim_client.api'`

- [ ] **Step 3: Write the implementation**

Create `clients/surya-ocr/kitabim_client/api.py`:

```python
from __future__ import annotations

import json
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
        self, base_url: str, config_path: Path, provider: str = "google"
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.config_path = config_path
        self.provider = provider

    def _headers(self) -> dict:
        token = get_valid_token(self.base_url, self.config_path, self.provider)
        return {"Authorization": f"Bearer {token}"}

    def _check(self, response: httpx.Response) -> dict:
        if response.status_code >= 400:
            raise KitabimAPIError(
                f"{response.status_code} from Kitabim API: {response.text}"
            )
        return response.json()

    def push_new_book(self, pdf_path: Path, pages: list["PageState"]) -> dict:
        pages_json = json.dumps(
            [
                {"pageNumber": p.page_number, "text": p.text, "isToc": p.is_toc}
                for p in pages
            ],
            ensure_ascii=False,
        )
        with open(pdf_path, "rb") as f:
            response = httpx.post(
                f"{self.base_url}/books/upload-ocrd",
                headers=self._headers(),
                files={"file": (pdf_path.name, f, "application/pdf")},
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd clients/surya-ocr && python -m pytest tests/kitabim_client/test_api.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add clients/surya-ocr/kitabim_client/api.py clients/surya-ocr/tests/kitabim_client/test_api.py
git commit -m "feat(surya-ocr-client): add Kitabim API client (push/download/list)"
```

---

## Task 9: Client — `preview/server.py` (local FastAPI preview UI)

**Files:**
- Create: `clients/surya-ocr/preview/server.py`
- Test: `clients/surya-ocr/tests/preview/test_server.py`

**Interfaces:**
- Consumes: `OcrWorkDir`, `PageState` from Task 6; `ocr_page_with_surya`, `get_recognition_predictor` from Task 5; `KitabimClient` from Task 8.
- Produces: `create_app(workdir, client) -> FastAPI`, `serve(workdir, client, port=8765, open_browser=True) -> None`. Consumed by Task 10 (`cli.py`).

- [ ] **Step 1: Write the failing tests**

Create `clients/surya-ocr/tests/preview/test_server.py` (uses FastAPI's `TestClient`, which drives the app in-process — no real network/browser needed):

```python
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from engine.workdir import OcrWorkDir
from preview.server import create_app


def _workdir(tmp_path: Path, book_id=None) -> OcrWorkDir:
    wd = OcrWorkDir.create(
        tmp_path / "work", source_pdf=tmp_path / "book.pdf", total_pages=2, book_id=book_id
    )
    wd.set_page(1, text="page one", is_toc=False, confidence=0.9, status="ocrd")
    wd.set_page(2, text="page two", is_toc=True, confidence=0.8, status="ocrd")
    wd.image_path(1).parent.mkdir(exist_ok=True)
    wd.image_path(1).write_bytes(b"\x89PNG\r\n fake")
    wd.image_path(2).write_bytes(b"\x89PNG\r\n fake2")
    wd.save()
    return wd


def test_list_pages_returns_all_pages_in_order(tmp_path: Path):
    wd = _workdir(tmp_path)
    app = create_app(wd, client=None)
    client = TestClient(app)

    response = client.get("/api/pages")

    assert response.status_code == 200
    body = response.json()
    assert [p["pageNumber"] for p in body] == [1, 2]
    assert body[0]["text"] == "page one"


def test_get_page_image_returns_png_bytes(tmp_path: Path):
    wd = _workdir(tmp_path)
    app = create_app(wd, client=None)
    client = TestClient(app)

    response = client.get("/api/pages/1/image")

    assert response.status_code == 200
    assert response.content == b"\x89PNG\r\n fake"


def test_redo_pages_reruns_ocr_on_selected_pages_only(tmp_path: Path):
    wd = _workdir(tmp_path)
    app = create_app(wd, client=None)
    client = TestClient(app)

    with (
        patch("preview.server.get_recognition_predictor", AsyncMock(return_value="predictor")),
        patch("preview.server.ocr_page_with_surya", AsyncMock(return_value="re-ocr'd text")),
        patch("preview.server.fitz.open") as mock_fitz_open,
    ):
        mock_doc = mock_fitz_open.return_value
        mock_doc.load_page.return_value = "fake-fitz-page"

        response = client.post("/api/pages/redo", json={"pageNumbers": [2]})

    assert response.status_code == 200
    body = response.json()
    assert body[0]["pageNumber"] == 1 and body[0]["text"] == "page one"  # untouched
    assert body[1]["pageNumber"] == 2 and body[1]["text"] == "re-ocr'd text"
    assert wd.get_page(1).text == "page one"
    assert wd.get_page(2).text == "re-ocr'd text"


def test_redo_pages_flags_failed_page_instead_of_crashing(tmp_path: Path):
    wd = _workdir(tmp_path)
    app = create_app(wd, client=None)
    client = TestClient(app)

    from engine.recognize import LowConfidenceOcrError

    with (
        patch("preview.server.get_recognition_predictor", AsyncMock(return_value="predictor")),
        patch(
            "preview.server.ocr_page_with_surya",
            AsyncMock(side_effect=LowConfidenceOcrError("confidence too low")),
        ),
        patch("preview.server.fitz.open") as mock_fitz_open,
    ):
        mock_doc = mock_fitz_open.return_value
        mock_doc.load_page.return_value = "fake-fitz-page"

        response = client.post("/api/pages/redo", json={"pageNumbers": [2]})

    assert response.status_code == 200
    body = response.json()
    failed_page = next(p for p in body if p["pageNumber"] == 2)
    assert failed_page["status"] == "failed"
    assert "confidence too low" in failed_page["error"]
    assert wd.get_page(2).status == "failed"


def test_push_new_book_calls_client_push_new_book(tmp_path: Path):
    wd = _workdir(tmp_path)  # book_id=None -> new-book mode
    (tmp_path / "book.pdf").write_bytes(b"%PDF-fake")
    mock_client = AsyncMock()
    mock_client.push_new_book = lambda pdf_path, pages: {"bookId": "new1", "status": "uploaded"}

    app = create_app(wd, client=mock_client)
    test_client = TestClient(app)

    response = test_client.post("/api/push")

    assert response.status_code == 200
    assert response.json() == {"bookId": "new1", "status": "uploaded"}


def test_push_corrections_calls_client_push_page_correction_per_page(tmp_path: Path):
    wd = _workdir(tmp_path, book_id="existingbook")  # correction mode
    calls = []
    mock_client = AsyncMock()
    mock_client.push_page_correction = lambda book_id, page: calls.append(
        (book_id, page.page_number)
    )

    app = create_app(wd, client=mock_client)
    test_client = TestClient(app)

    response = test_client.post("/api/push")

    assert response.status_code == 200
    assert calls == [("existingbook", 1), ("existingbook", 2)]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd clients/surya-ocr && python -m pytest tests/preview/test_server.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'preview.server'`

- [ ] **Step 3: Write the implementation**

Create `clients/surya-ocr/preview/server.py`:

```python
from __future__ import annotations

import webbrowser

import fitz
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from engine.recognize import (
    LowConfidenceOcrError,
    get_recognition_predictor,
    ocr_page_with_surya,
)
from engine.workdir import OcrWorkDir

_PAGE_HTML = """<!doctype html>
<html><head><title>Surya OCR Preview</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 1rem; }
  .page { display: flex; gap: 1rem; border-bottom: 1px solid #ccc; padding: 0.75rem 0; }
  .page img { max-width: 300px; }
  .page textarea { flex: 1; min-height: 200px; }
  button { margin: 0.25rem; }
</style>
</head><body>
<h1>Surya OCR Preview</h1>
<div>
  <button onclick="redoSelected()">Redo selected pages</button>
  <button onclick="redoAll()">Redo whole book</button>
  <button onclick="push()">Push to Kitabim</button>
</div>
<div id="pages"></div>
<script>
async function loadPages() {
  const res = await fetch('/api/pages');
  const pages = await res.json();
  const container = document.getElementById('pages');
  container.innerHTML = '';
  for (const p of pages) {
    const div = document.createElement('div');
    div.className = 'page';
    div.innerHTML = `
      <input type="checkbox" class="select" value="${p.pageNumber}">
      <img src="/api/pages/${p.pageNumber}/image">
      <textarea data-page="${p.pageNumber}">${p.text}</textarea>
    `;
    container.appendChild(div);
  }
}
function selectedPageNumbers() {
  return Array.from(document.querySelectorAll('.select:checked')).map(c => parseInt(c.value));
}
function allPageNumbers() {
  return Array.from(document.querySelectorAll('.select')).map(c => parseInt(c.value));
}
async function redoSelected() {
  await fetch('/api/pages/redo', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({pageNumbers: selectedPageNumbers()})
  });
  loadPages();
}
async function redoAll() {
  await fetch('/api/pages/redo', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({pageNumbers: allPageNumbers()})
  });
  loadPages();
}
async function push() {
  const res = await fetch('/api/push', {method: 'POST'});
  const body = await res.json();
  alert('Push result: ' + JSON.stringify(body));
}
loadPages();
</script>
</body></html>"""


class RedoRequest(BaseModel):
    pageNumbers: list[int]


def create_app(workdir: OcrWorkDir, client) -> FastAPI:
    app = FastAPI()

    @app.get("/", response_class=HTMLResponse)
    def index():
        return _PAGE_HTML

    @app.get("/api/pages")
    def list_pages():
        return [
            {
                "pageNumber": p.page_number,
                "text": p.text,
                "isToc": p.is_toc,
                "confidence": p.confidence,
                "status": p.status,
            }
            for p in workdir.all_pages()
        ]

    @app.get("/api/pages/{page_number}/image")
    def get_page_image(page_number: int):
        return Response(
            content=workdir.image_path(page_number).read_bytes(),
            media_type="image/png",
        )

    @app.post("/api/pages/redo")
    async def redo_pages(body: RedoRequest):
        doc = fitz.open(workdir.source_pdf)
        predictor = await get_recognition_predictor()
        for page_number in body.pageNumbers:
            fitz_page = doc.load_page(page_number - 1)
            try:
                text = await ocr_page_with_surya(fitz_page, predictor)
                workdir.set_page(
                    page_number, text=text, is_toc=False, confidence=1.0, status="ocrd"
                )
            except LowConfidenceOcrError as exc:
                # Never silently push a page that failed OCR - flag it and
                # keep going, so one bad page doesn't abort the whole batch.
                try:
                    previous_text = workdir.get_page(page_number).text
                except KeyError:
                    previous_text = ""
                workdir.set_page(
                    page_number,
                    text=previous_text,
                    is_toc=False,
                    confidence=0.0,
                    status="failed",
                    error=str(exc),
                )
        workdir.save()
        return [
            {
                "pageNumber": p.page_number,
                "text": p.text,
                "status": p.status,
                "error": p.error,
            }
            for p in workdir.all_pages()
        ]

    @app.post("/api/push")
    def push():
        if workdir.book_id is None:
            return client.push_new_book(workdir.source_pdf, workdir.all_pages())
        results = []
        for page in workdir.all_pages():
            results.append(client.push_page_correction(workdir.book_id, page))
        return {"status": "corrections_pushed", "count": len(results)}

    return app


def serve(
    workdir: OcrWorkDir, client, port: int = 8765, open_browser: bool = True
) -> None:
    app = create_app(workdir, client)
    if open_browser:
        webbrowser.open(f"http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd clients/surya-ocr && python -m pytest tests/preview/test_server.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add clients/surya-ocr/preview/server.py clients/surya-ocr/tests/preview/test_server.py
git commit -m "feat(surya-ocr-client): add local preview UI (list/redo/push)"
```

---

## Task 10: Client — `cli.py`

**Files:**
- Create: `clients/surya-ocr/cli.py`
- Test: `clients/surya-ocr/tests/test_cli.py`

**Interfaces:**
- Consumes: everything from Tasks 5-9 (`engine.recognize`, `engine.workdir`, `kitabim_client.api`, `preview.server`).
- Produces: the `python cli.py {ocr,preview,push,correct}` command surface described in the spec.

- [ ] **Step 1: Write the failing tests**

Create `clients/surya-ocr/tests/test_cli.py` (tests the argument-parsing and command-dispatch logic directly by calling the `cmd_*` functions, not by shelling out — consistent with how the rest of this plan tests things: fast, no subprocess):

```python
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import cli


@pytest.mark.asyncio
async def test_cmd_ocr_renders_and_ocrs_every_page_then_serves(tmp_path: Path):
    pdf_path = tmp_path / "book.pdf"
    pdf_path.write_bytes(b"%PDF-fake")
    out_dir = tmp_path / "out"

    mock_doc = MagicMock()
    mock_doc.__len__.return_value = 2
    mock_doc.load_page.return_value = "fake-fitz-page"
    mock_pix = MagicMock()
    mock_pix.tobytes.return_value = b"\x89PNG fake"

    with (
        patch("cli.fitz.open", return_value=mock_doc),
        patch("cli.get_recognition_predictor", AsyncMock(return_value="predictor")),
        patch(
            "cli.ocr_page_with_surya",
            AsyncMock(side_effect=["text one", "text two"]),
        ),
        patch("cli.render_page_png", return_value=b"\x89PNG fake"),
        patch("cli.serve") as mock_serve,
    ):
        await cli.cmd_ocr(pdf_path, out_dir, open_preview=True)

    from engine.workdir import OcrWorkDir

    wd = OcrWorkDir.load(out_dir)
    assert wd.total_pages == 2
    assert wd.get_page(1).text == "text one"
    assert wd.get_page(2).text == "text two"
    mock_serve.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_ocr_flags_failed_page_and_continues(tmp_path: Path):
    pdf_path = tmp_path / "book.pdf"
    pdf_path.write_bytes(b"%PDF-fake")
    out_dir = tmp_path / "out"

    mock_doc = MagicMock()
    mock_doc.__len__.return_value = 2
    mock_doc.load_page.return_value = "fake-fitz-page"

    from engine.recognize import LowConfidenceOcrError

    with (
        patch("cli.fitz.open", return_value=mock_doc),
        patch("cli.get_recognition_predictor", AsyncMock(return_value="predictor")),
        patch(
            "cli.ocr_page_with_surya",
            AsyncMock(side_effect=[LowConfidenceOcrError("bad page"), "text two"]),
        ),
        patch("cli.render_page_png", return_value=b"\x89PNG fake"),
        patch("cli.serve") as mock_serve,
    ):
        await cli.cmd_ocr(pdf_path, out_dir, open_preview=True)

    from engine.workdir import OcrWorkDir

    wd = OcrWorkDir.load(out_dir)
    assert wd.get_page(1).status == "failed"
    assert "bad page" in wd.get_page(1).error
    assert wd.get_page(2).text == "text two"
    mock_serve.assert_called_once()  # one bad page doesn't abort the whole run


@pytest.mark.asyncio
async def test_cmd_correct_seeds_workdir_from_existing_book_pages(tmp_path: Path):
    out_dir = tmp_path / "out"
    mock_client = MagicMock()
    mock_client.download_book_pdf.return_value = tmp_path / "downloaded.pdf"
    mock_client.get_book_pages.return_value = [
        {"pageNumber": 1, "text": "existing one", "isToc": False},
        {"pageNumber": 2, "text": "existing two", "isToc": True},
    ]
    (tmp_path / "downloaded.pdf").write_bytes(b"%PDF-fake")

    mock_doc = MagicMock()
    mock_doc.__len__.return_value = 2

    with (
        patch("cli.KitabimClient", return_value=mock_client),
        patch("cli.fitz.open", return_value=mock_doc),
        patch("cli.render_page_png", return_value=b"\x89PNG fake"),
        patch("cli.serve") as mock_serve,
    ):
        await cli.cmd_correct(
            "book123", out_dir, base_url="http://localhost:8000", open_preview=True
        )

    from engine.workdir import OcrWorkDir

    wd = OcrWorkDir.load(out_dir)
    assert wd.book_id == "book123"
    assert wd.get_page(1).text == "existing one"
    assert wd.get_page(2).is_toc is True
    mock_serve.assert_called_once()


def test_build_parser_ocr_command():
    parser = cli.build_parser()
    args = parser.parse_args(["ocr", "book.pdf", "--out", "workdir"])
    assert args.command == "ocr"
    assert args.pdf == "book.pdf"
    assert args.out == "workdir"


def test_build_parser_correct_command():
    parser = cli.build_parser()
    args = parser.parse_args(["correct", "book123", "--base-url", "http://x"])
    assert args.command == "correct"
    assert args.book_id == "book123"
    assert args.base_url == "http://x"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd clients/surya-ocr && python -m pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cli'`

- [ ] **Step 3: Write the implementation**

Create `clients/surya-ocr/cli.py`:

```python
from __future__ import annotations

import argparse
import asyncio
import io
from pathlib import Path

import fitz
from PIL import Image

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


def render_page_png(doc: "fitz.Document", page_number: int, zoom: float = RENDER_ZOOM) -> bytes:
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
                page_number, text="", is_toc=False, confidence=0.0,
                status="failed", error=str(exc),
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

    ocr_parser = sub.add_parser("ocr", help="Render + OCR a new PDF, then open the preview UI")
    ocr_parser.add_argument("pdf")
    ocr_parser.add_argument("--out", required=True)
    ocr_parser.add_argument("--no-preview", action="store_true")

    preview_parser = sub.add_parser("preview", help="Reopen the preview UI for an existing work directory")
    preview_parser.add_argument("workdir")
    preview_parser.add_argument("--base-url")

    push_parser = sub.add_parser("push", help="Push a work directory's results to Kitabim without opening the UI")
    push_parser.add_argument("workdir")
    push_parser.add_argument("--base-url", required=True)

    correct_parser = sub.add_parser("correct", help="Download an existing book and open it for correction")
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd clients/surya-ocr && python -m pytest tests/test_cli.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Run the full client test suite to check for regressions**

Run: `cd clients/surya-ocr && python -m pytest -v`
Expected: PASS (all tests across every task in this plan)

- [ ] **Step 6: Commit**

```bash
git add clients/surya-ocr/cli.py clients/surya-ocr/tests/test_cli.py
git commit -m "feat(surya-ocr-client): add CLI (ocr/preview/push/correct commands)"
```

---

## Final Verification

- [ ] Run the full backend test suite for the touched files: `cd services/backend && python -m pytest tests/api/endpoints/books_router_test.py -v` and `cd packages/backend-core && python -m pytest tests/app/models/schemas_test.py -v` — both green.
- [ ] Run the full client test suite: `cd clients/surya-ocr && python -m pytest -v` — all green.
- [ ] Manually smoke-test `python cli.py ocr <a real small PDF> --out /tmp/smoketest` once `surya-ocr` and its model weights are actually installed locally (this plan's automated tests all mock the Surya model — they don't prove real OCR quality, only that the plumbing is correct). Confirm the preview UI opens at `http://127.0.0.1:8765` and shows page images next to text.
- [ ] Flag the two `ug.json` strings added in Task 1 for the user's review (per project memory on Uyghur translation quality) before considering this plan fully done.
