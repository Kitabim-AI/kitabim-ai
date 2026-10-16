# Per-Page LLM Spell Check in Edit Mode — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move per-page LLM spell check into page edit mode as a non-persisting preview: corrected text loads into the textarea with changed words highlighted, and the editor decides whether to Save.

**Architecture:** A new synchronous `POST .../llm-spell-check/preview` endpoint reuses `correct_page_text()` and writes nothing. The frontend snapshots the pre-check text, swaps in the corrected text, and renders a word-level diff in a highlight layer behind the textarea. Save passes `llm_spell_checked: true` to the existing `/update` endpoint, which marks the page as LLM-checked. The old per-page enqueue endpoint and view-mode button are removed; the book-level flow is untouched.

**Tech Stack:** FastAPI, SQLAlchemy async, pytest (backend); React 19, TypeScript, Vitest + Testing Library (frontend).

**Spec:** `docs/superpowers/specs/2026-10-15-llm-spell-check-edit-mode-design.md`

## Global Constraints

- No `print()` — use `log_json(logger, level, "message", key=value)`.
- No hardcoded user-visible strings — backend uses `t("errors.key")`; frontend uses `t('…')` from `useI18n`.
- All endpoints need an auth dependency. The preview endpoint uses `require_editor`.
- **Do not machine-translate Uyghur.** New `ug.json` keys get the English text as a placeholder and are listed in the final hand-off for the user to translate.
- Book-level LLM spell check (`/reprocess/llm-spell-check`), `llm_spell_check_job`, the batch poller, and `LLM_SPELL_CHECK_PROMPT` must not change.
- Backend tests: `./venv/bin/pytest` from the repo root. Frontend tests: `npx vitest run <path>` from `apps/frontend/`.
- Invoke the matching project skill before each task's code (`/api-developer` + `/api-unit-tester` for backend tasks, `/ui-developer` + `/ui-unit-tester` for frontend tasks), per `CLAUDE.md`.

---

### Task 1: Backend preview endpoint

**Files:**
- Modify: `services/backend/api/endpoints/books_router.py` (add import near line 64; add request model + endpoint right after `trigger_llm_spell_check_page`, which ends around line 2452)
- Modify: `services/backend/locales/en.json`, `services/backend/locales/ug.json` (`errors` block, next to `llm_spell_check_enqueue_failed`)
- Test: `services/backend/tests/api/endpoints/books_router_test.py`

**Interfaces:**
- Consumes: `correct_page_text(page_text: str, prev_page_text: Optional[str], next_page_text: Optional[str], config_repo: Optional[SystemConfigsRepository] = None, model_name: Optional[str] = None) -> str` from `app.services.llm_spell_check_service`. It raises `ValueError` when the guardrail rejects the output.
- Produces: `POST /api/books/{book_id}/pages/{page_num}/llm-spell-check/preview`, body `{"text": str}`, response `{"corrected_text": str}`. Python handler: `preview_llm_spell_check_page(book_id, page_num, request: LlmSpellCheckPreviewRequest, current_user, session)`.
- Error keys: `errors.llm_spell_check_empty_text` (400), `errors.page_not_found` (404), `errors.llm_spell_check_invalid_output` (422), `errors.llm_spell_check_enqueue_failed` (502, existing key reused: "Failed to start LLM spell check. Please try again.").

- [ ] **Step 1: Write the failing tests**

Append to `services/backend/tests/api/endpoints/books_router_test.py`:

```python
def _preview_page(text="old", page_id=7):
    page = MagicMock()
    page.id = page_id
    page.text = text
    page.llm_spell_check_status = "idle"
    return page


@pytest.mark.asyncio
async def test_preview_llm_spell_check_returns_corrected_text_without_writes():
    setup_paths()
    from api.endpoints.books_router import (  # type: ignore[import]
        preview_llm_spell_check_page,
        LlmSpellCheckPreviewRequest,
    )

    mock_session = AsyncMock()
    mock_user = MagicMock()
    mock_user.email = "editor@example.com"

    page = _preview_page(text="saved text")
    prev_page = _preview_page(text="previous page")
    next_page = _preview_page(text="next page")

    async def find_one(book_id, page_num):
        return {4: prev_page, 5: page, 6: next_page}.get(page_num)

    mock_repo = MagicMock()
    mock_repo.find_one = AsyncMock(side_effect=find_one)

    with (
        patch("api.endpoints.books_router.PagesRepository", return_value=mock_repo),
        patch("api.endpoints.books_router.SystemConfigsRepository"),
        patch(
            "api.endpoints.books_router.correct_page_text",
            new_callable=AsyncMock,
            return_value="corrected text",
        ) as mock_correct,
    ):
        result = await preview_llm_spell_check_page(
            book_id="book-1",
            page_num=5,
            request=LlmSpellCheckPreviewRequest(text="unsaved edits"),
            current_user=mock_user,
            session=mock_session,
        )

    assert result == {"corrected_text": "corrected text"}
    args = mock_correct.call_args.args
    assert args[0] == "unsaved edits"  # textarea text, not the saved page text
    assert args[1] == "previous page"
    assert args[2] == "next page"
    # Nothing persisted
    assert page.text == "saved text"
    assert page.llm_spell_check_status == "idle"
    mock_session.commit.assert_not_called()
    mock_session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_preview_llm_spell_check_handles_missing_neighbors():
    setup_paths()
    from api.endpoints.books_router import (  # type: ignore[import]
        preview_llm_spell_check_page,
        LlmSpellCheckPreviewRequest,
    )

    page = _preview_page()

    async def find_one(book_id, page_num):
        return page if page_num == 1 else None

    mock_repo = MagicMock()
    mock_repo.find_one = AsyncMock(side_effect=find_one)

    with (
        patch("api.endpoints.books_router.PagesRepository", return_value=mock_repo),
        patch("api.endpoints.books_router.SystemConfigsRepository"),
        patch(
            "api.endpoints.books_router.correct_page_text",
            new_callable=AsyncMock,
            return_value="x",
        ) as mock_correct,
    ):
        await preview_llm_spell_check_page(
            book_id="book-1",
            page_num=1,
            request=LlmSpellCheckPreviewRequest(text="text"),
            current_user=MagicMock(),
            session=AsyncMock(),
        )

    args = mock_correct.call_args.args
    assert args[1] is None
    assert args[2] is None


@pytest.mark.asyncio
async def test_preview_llm_spell_check_400_on_empty_text():
    setup_paths()
    from api.endpoints.books_router import (  # type: ignore[import]
        preview_llm_spell_check_page,
        LlmSpellCheckPreviewRequest,
    )

    with pytest.raises(HTTPException) as excinfo:
        await preview_llm_spell_check_page(
            book_id="book-1",
            page_num=1,
            request=LlmSpellCheckPreviewRequest(text="   \n "),
            current_user=MagicMock(),
            session=AsyncMock(),
        )

    assert excinfo.value.status_code == 400


@pytest.mark.asyncio
async def test_preview_llm_spell_check_404_when_page_missing():
    setup_paths()
    from api.endpoints.books_router import (  # type: ignore[import]
        preview_llm_spell_check_page,
        LlmSpellCheckPreviewRequest,
    )

    mock_repo = MagicMock()
    mock_repo.find_one = AsyncMock(return_value=None)

    with patch("api.endpoints.books_router.PagesRepository", return_value=mock_repo):
        with pytest.raises(HTTPException) as excinfo:
            await preview_llm_spell_check_page(
                book_id="book-1",
                page_num=999,
                request=LlmSpellCheckPreviewRequest(text="text"),
                current_user=MagicMock(),
                session=AsyncMock(),
            )

    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_preview_llm_spell_check_422_when_guardrail_rejects():
    setup_paths()
    from api.endpoints.books_router import (  # type: ignore[import]
        preview_llm_spell_check_page,
        LlmSpellCheckPreviewRequest,
    )

    mock_repo = MagicMock()
    mock_repo.find_one = AsyncMock(return_value=_preview_page())

    with (
        patch("api.endpoints.books_router.PagesRepository", return_value=mock_repo),
        patch("api.endpoints.books_router.SystemConfigsRepository"),
        patch(
            "api.endpoints.books_router.correct_page_text",
            new_callable=AsyncMock,
            side_effect=ValueError("LLM spell check returned empty output"),
        ),
    ):
        with pytest.raises(HTTPException) as excinfo:
            await preview_llm_spell_check_page(
                book_id="book-1",
                page_num=2,
                request=LlmSpellCheckPreviewRequest(text="text"),
                current_user=MagicMock(),
                session=AsyncMock(),
            )

    assert excinfo.value.status_code == 422


@pytest.mark.asyncio
async def test_preview_llm_spell_check_502_when_llm_call_fails():
    setup_paths()
    from api.endpoints.books_router import (  # type: ignore[import]
        preview_llm_spell_check_page,
        LlmSpellCheckPreviewRequest,
    )

    mock_repo = MagicMock()
    mock_repo.find_one = AsyncMock(return_value=_preview_page())

    with (
        patch("api.endpoints.books_router.PagesRepository", return_value=mock_repo),
        patch("api.endpoints.books_router.SystemConfigsRepository"),
        patch(
            "api.endpoints.books_router.correct_page_text",
            new_callable=AsyncMock,
            side_effect=RuntimeError("circuit open"),
        ),
    ):
        with pytest.raises(HTTPException) as excinfo:
            await preview_llm_spell_check_page(
                book_id="book-1",
                page_num=2,
                request=LlmSpellCheckPreviewRequest(text="text"),
                current_user=MagicMock(),
                session=AsyncMock(),
            )

    assert excinfo.value.status_code == 502


def test_preview_llm_spell_check_requires_editor():
    setup_paths()
    from api.endpoints import books_router  # type: ignore[import]
    from auth.dependencies import require_editor  # type: ignore[import]

    route = next(
        r
        for r in books_router.router.routes
        if getattr(r, "path", "").endswith("/pages/{page_num}/llm-spell-check/preview")
    )
    dependency_calls = [d.call for d in route.dependant.dependencies]
    assert require_editor in dependency_calls
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./venv/bin/pytest services/backend/tests/api/endpoints/books_router_test.py -k preview_llm_spell_check -v`
Expected: FAIL with `ImportError: cannot import name 'preview_llm_spell_check_page'`.

- [ ] **Step 3: Add the locale keys**

In `services/backend/locales/en.json`, inside `"errors"`, directly after the `"llm_spell_check_enqueue_failed"` line, add:

```json
    "llm_spell_check_empty_text": "There is no text on this page to check.",
    "llm_spell_check_invalid_output": "The AI check returned an unusable result. The text was not changed. Please try again.",
```

In `services/backend/locales/ug.json`, at the same position, add the same two keys with the **English** values above. These are placeholders for the user to translate; do not machine-translate them.

- [ ] **Step 4: Implement the endpoint**

In `services/backend/api/endpoints/books_router.py`, add this import after the `submit_batch_llm_spell_check` import (line 64):

```python
from app.services.llm_spell_check_service import correct_page_text
```

Add after the end of `trigger_llm_spell_check_page`. Task 3 deletes that function; this code must not depend on it.

```python
class LlmSpellCheckPreviewRequest(BaseModel):
    text: str


@router.post("/{book_id}/pages/{page_num}/llm-spell-check/preview")
async def preview_llm_spell_check_page(
    book_id: str,
    page_num: int,
    request: LlmSpellCheckPreviewRequest,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Run the LLM spell check on the editor's current (possibly unsaved)
    page text and return the corrected text WITHOUT persisting anything.
    The editor reviews the highlighted changes in edit mode and decides
    whether to save via POST .../update."""
    if not request.text or not request.text.strip():
        raise HTTPException(
            status_code=400, detail=t("errors.llm_spell_check_empty_text")
        )

    pages_repo = PagesRepository(session)
    page = await pages_repo.find_one(book_id, page_num)
    if not page:
        raise HTTPException(status_code=404, detail=t("errors.page_not_found"))

    prev_page = await pages_repo.find_one(book_id, page_num - 1)
    next_page = await pages_repo.find_one(book_id, page_num + 1)

    try:
        corrected = await correct_page_text(
            request.text,
            prev_page.text if prev_page else None,
            next_page.text if next_page else None,
            config_repo=SystemConfigsRepository(session),
        )
    except ValueError as exc:
        log_json(
            logger,
            logging.WARNING,
            "llm spell check preview rejected by guardrail",
            book_id=book_id,
            page=page_num,
            error=str(exc),
        )
        raise HTTPException(
            status_code=422, detail=t("errors.llm_spell_check_invalid_output")
        )
    except Exception as exc:
        log_json(
            logger,
            logging.ERROR,
            "llm spell check preview failed",
            book_id=book_id,
            page=page_num,
            error=str(exc),
        )
        raise HTTPException(
            status_code=502, detail=t("errors.llm_spell_check_enqueue_failed")
        )

    log_json(
        logger,
        logging.INFO,
        "llm spell check preview generated",
        book_id=book_id,
        page=page_num,
        user=current_user.email,
    )
    return {"corrected_text": corrected}
```

`BaseModel` is already imported at module level (line ~1129, `from pydantic import BaseModel, ConfigDict, field_validator`), which is above the new class, so no new import is needed.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `./venv/bin/pytest services/backend/tests/api/endpoints/books_router_test.py -k preview_llm_spell_check -v`
Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add services/backend/api/endpoints/books_router.py services/backend/locales/en.json services/backend/locales/ug.json services/backend/tests/api/endpoints/books_router_test.py
git commit -m "feat(api): add non-persisting per-page LLM spell check preview endpoint"
```

---

### Task 2: `/update` marks the page LLM-checked

**Files:**
- Modify: `services/backend/api/endpoints/books_router.py` — `update_page_text` (starts around line 2589)
- Test: `services/backend/tests/api/endpoints/books_router_test.py`

**Interfaces:**
- Produces: `POST /api/books/{book_id}/pages/{page_num}/update` accepts optional `"llm_spell_checked": bool` in its JSON payload. When true, it sets `page.llm_spell_check_status = PAGE_MILESTONE_SUCCEEDED` (`"succeeded"`) and `page.llm_spell_check_at = <utc now>`.

- [ ] **Step 1: Write the failing tests**

Append to `services/backend/tests/api/endpoints/books_router_test.py`:

```python
async def _call_update_page_text(payload, page):
    from api.endpoints.books_router import update_page_text  # type: ignore[import]

    mock_pages_repo = MagicMock()
    mock_pages_repo.find_one = AsyncMock(return_value=page)
    mock_books_repo = MagicMock()
    mock_books_repo.update_one = AsyncMock()
    mock_configs_repo = MagicMock()
    mock_configs_repo.get_value = AsyncMock(return_value="gemini-embedding-2")
    mock_cache = MagicMock()
    mock_cache.delete = AsyncMock()
    mock_cache.delete_pattern = AsyncMock()
    mock_user = MagicMock()
    mock_user.email = "editor@example.com"

    with (
        patch("api.endpoints.books_router.PagesRepository", return_value=mock_pages_repo),
        patch("api.endpoints.books_router.BooksRepository", return_value=mock_books_repo),
        patch("api.endpoints.books_router.SystemConfigsRepository", return_value=mock_configs_repo),
        patch("api.endpoints.books_router.cache_service", mock_cache),
        patch(
            "app.services.book_milestone_service.BookMilestoneService.update_book_milestones",
            new_callable=AsyncMock,
        ),
    ):
        # Empty text takes the no-chunking branch, so no embedding calls are made.
        return await update_page_text(
            book_id="book-1",
            page_num=3,
            payload=payload,
            current_user=mock_user,
            session=AsyncMock(),
        )


@pytest.mark.asyncio
async def test_update_page_text_marks_llm_checked_when_flag_true():
    setup_paths()
    page = MagicMock()
    page.text = "old"
    page.llm_spell_check_status = "idle"
    page.llm_spell_check_at = None

    await _call_update_page_text({"text": "", "llm_spell_checked": True}, page)

    assert page.llm_spell_check_status == "succeeded"
    assert page.llm_spell_check_at is not None


@pytest.mark.asyncio
async def test_update_page_text_leaves_llm_status_without_flag():
    setup_paths()
    page = MagicMock()
    page.text = "old"
    page.llm_spell_check_status = "idle"
    page.llm_spell_check_at = None

    await _call_update_page_text({"text": ""}, page)

    assert page.llm_spell_check_status == "idle"
    assert page.llm_spell_check_at is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./venv/bin/pytest services/backend/tests/api/endpoints/books_router_test.py -k update_page_text -v`
Expected: `test_update_page_text_marks_llm_checked_when_flag_true` FAILS (status still `"idle"`); the other test passes.

- [ ] **Step 3: Implement**

In `update_page_text`, directly after the line `page.updated_by = current_user.email`, add:

```python
    # Editor reviewed an LLM spell-check preview in edit mode before saving —
    # mark the page so a non-forced book-level LLM run skips it.
    if payload.get("llm_spell_checked") is True:
        page.llm_spell_check_status = PAGE_MILESTONE_SUCCEEDED
        page.llm_spell_check_at = datetime.now(timezone.utc)
```

(`PAGE_MILESTONE_SUCCEEDED` is already imported in this module.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./venv/bin/pytest services/backend/tests/api/endpoints/books_router_test.py -k update_page_text -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add services/backend/api/endpoints/books_router.py services/backend/tests/api/endpoints/books_router_test.py
git commit -m "feat(api): mark page LLM-checked when saved after edit-mode preview"
```

---

### Task 3: Remove the old per-page enqueue endpoint

**Files:**
- Modify: `services/backend/api/endpoints/books_router.py` — delete `trigger_llm_spell_check_page` (the `@router.post("/{book_id}/pages/{page_num}/llm-spell-check")` function, around lines 2381–2452)
- Modify: `services/backend/locales/en.json`, `services/backend/locales/ug.json` — delete the `"llm_spell_check_already_running"` line
- Modify: `services/backend/tests/api/endpoints/books_router_test.py` — delete the three `test_trigger_llm_spell_check_page_*` tests

**Interfaces:**
- Produces: `POST /api/books/{book_id}/pages/{page_num}/llm-spell-check` no longer exists.

- [ ] **Step 1: Delete the three tests**

Remove these functions and their `@pytest.mark.asyncio` decorators from `books_router_test.py`:
`test_trigger_llm_spell_check_page_enqueues_and_returns_started`, `test_trigger_llm_spell_check_page_409_when_already_running`, `test_trigger_llm_spell_check_page_404_when_not_found`.

- [ ] **Step 2: Delete the endpoint**

Delete the entire `trigger_llm_spell_check_page` function, from its `@router.post("/{book_id}/pages/{page_num}/llm-spell-check")` decorator through its final `return {"status": "llm_spell_check_started"}`. Keep the Task 1 preview endpoint and `LlmSpellCheckPreviewRequest`.

- [ ] **Step 3: Delete the orphaned locale key**

Run: `grep -rn "llm_spell_check_already_running" services packages`
Expected: only the two locale JSON lines. Delete the `"llm_spell_check_already_running": …` line from both `services/backend/locales/en.json` and `services/backend/locales/ug.json`. Then validate both files:

Run: `python3 -m json.tool services/backend/locales/en.json > /dev/null && python3 -m json.tool services/backend/locales/ug.json > /dev/null && echo ok`
Expected: `ok`

- [ ] **Step 4: Run the full router test file and lint**

Run: `./venv/bin/pytest services/backend/tests/api/endpoints/books_router_test.py -v`
Expected: all pass, and no test references `trigger_llm_spell_check_page`.

Run: `./venv/bin/ruff check services/backend/api/endpoints/books_router.py`
Expected: no new unused-import warnings (`time`, `settings`, `PAGE_MILESTONE_IN_PROGRESS` are still used by the book-level endpoint; remove any import that ruff flags as unused).

- [ ] **Step 5: Commit**

```bash
git add services/backend/api/endpoints/books_router.py services/backend/locales/en.json services/backend/locales/ug.json services/backend/tests/api/endpoints/books_router_test.py
git commit -m "refactor(api): remove per-page LLM spell check enqueue endpoint"
```

---

### Task 4: Word-level diff helper

**Files:**
- Create: `apps/frontend/src/utils/wordDiff.ts`
- Test: `apps/frontend/src/tests/utils/wordDiff.test.ts`

**Interfaces:**
- Produces:
  ```ts
  export interface ChangedRange { start: number; end: number; }
  export const diffChangedWordRanges: (baseline: string, current: string) => ChangedRange[];
  ```
  The function returns character ranges in `current` for words (whitespace-separated tokens) that were inserted or changed relative to `baseline`, sorted ascending. A word deleted from `baseline` produces no range.

- [ ] **Step 1: Write the failing tests**

Create `apps/frontend/src/tests/utils/wordDiff.test.ts`:

```ts
import { describe, expect, test } from 'vitest';
import { diffChangedWordRanges } from '@/src/utils/wordDiff';

const rangeOf = (text: string, word: string, from = 0) => {
  const start = text.indexOf(word, from);
  return { start, end: start + word.length };
};

describe('diffChangedWordRanges', () => {
  test('identical text has no changes', () => {
    expect(diffChangedWordRanges('مەن كىتاب ئوقۇدۇم', 'مەن كىتاب ئوقۇدۇم')).toEqual([]);
  });

  test('single substituted Uyghur word', () => {
    const current = 'مەن كىتاپ ئوقۇدۇم';
    expect(diffChangedWordRanges('مەن كىتاب ئوقۇدۇم', current)).toEqual([rangeOf(current, 'كىتاپ')]);
  });

  test('multiple substitutions across line breaks', () => {
    const baseline = 'a b\nc d\n\ne f';
    const current = 'a x\nc d\n\ny f';
    expect(diffChangedWordRanges(baseline, current)).toEqual([
      rangeOf(current, 'x'),
      rangeOf(current, 'y'),
    ]);
  });

  test('inserted word is highlighted', () => {
    const current = 'one two new three';
    expect(diffChangedWordRanges('one two three', current)).toEqual([rangeOf(current, 'new')]);
  });

  test('deleted word produces no range', () => {
    expect(diffChangedWordRanges('one two three', 'one three')).toEqual([]);
  });

  test('punctuation attached to a word counts as part of the token', () => {
    const current = 'سۆز كىتاپ.';
    expect(diffChangedWordRanges('سۆز كىتاب.', current)).toEqual([rangeOf(current, 'كىتاپ.')]);
  });

  test('repeated words: only the changed occurrence is highlighted', () => {
    const baseline = 'bir bir bir';
    const current = 'bir iki bir';
    expect(diffChangedWordRanges(baseline, current)).toEqual([rangeOf(current, 'iki')]);
  });

  test('whitespace-only differences are not changes', () => {
    expect(diffChangedWordRanges('a  b', 'a b')).toEqual([]);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `apps/frontend/`): `npx vitest run src/tests/utils/wordDiff.test.ts`
Expected: FAIL, because the module `@/src/utils/wordDiff` can't be resolved.

- [ ] **Step 3: Implement**

Create `apps/frontend/src/utils/wordDiff.ts`:

```ts
export interface ChangedRange {
  start: number;
  end: number;
}

interface Token {
  text: string;
  start: number;
  end: number;
}

const tokenize = (s: string): Token[] => {
  const tokens: Token[] = [];
  const re = /\S+/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(s)) !== null) {
    tokens.push({ text: m[0], start: m.index, end: m.index + m[0].length });
  }
  return tokens;
};

/**
 * Character ranges in `current` of words that were inserted or changed
 * relative to `baseline` (word-level LCS). Deleted words have no position in
 * `current` and are not reported.
 */
export const diffChangedWordRanges = (baseline: string, current: string): ChangedRange[] => {
  if (baseline === current) return [];
  const a = tokenize(baseline);
  const b = tokenize(current);

  // Trim the common prefix/suffix so the LCS table only covers the changed middle.
  let pre = 0;
  while (pre < a.length && pre < b.length && a[pre].text === b[pre].text) pre++;
  let suf = 0;
  while (
    suf < a.length - pre &&
    suf < b.length - pre &&
    a[a.length - 1 - suf].text === b[b.length - 1 - suf].text
  ) suf++;
  const a2 = a.slice(pre, a.length - suf);
  const b2 = b.slice(pre, b.length - suf);

  const cols = b2.length + 1;
  const dp = new Uint32Array((a2.length + 1) * cols);
  for (let i = a2.length - 1; i >= 0; i--) {
    for (let j = b2.length - 1; j >= 0; j--) {
      dp[i * cols + j] = a2[i].text === b2[j].text
        ? dp[(i + 1) * cols + j + 1] + 1
        : Math.max(dp[(i + 1) * cols + j], dp[i * cols + j + 1]);
    }
  }

  const ranges: ChangedRange[] = [];
  let i = 0;
  let j = 0;
  while (i < a2.length && j < b2.length) {
    if (a2[i].text === b2[j].text) {
      i++;
      j++;
    } else if (dp[(i + 1) * cols + j] >= dp[i * cols + j + 1]) {
      i++;
    } else {
      ranges.push({ start: b2[j].start, end: b2[j].end });
      j++;
    }
  }
  for (; j < b2.length; j++) ranges.push({ start: b2[j].start, end: b2[j].end });
  return ranges;
};
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npx vitest run src/tests/utils/wordDiff.test.ts`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/frontend/src/utils/wordDiff.ts apps/frontend/src/tests/utils/wordDiff.test.ts
git commit -m "feat(frontend): add word-level diff helper for LLM spell check highlights"
```

---

### Task 5: PersistenceService — preview call, save flag, remove old trigger

**Files:**
- Modify: `apps/frontend/src/services/persistenceService.ts` — replace `triggerLlmSpellCheckPage` (around line 297) and change `updatePage` (around line 378)
- Test: `apps/frontend/src/tests/services/persistenceService.test.ts`

**Interfaces:**
- Produces:
  ```ts
  PersistenceService.previewLlmSpellCheck(bookId: string, pageNum: number, text: string, signal?: AbortSignal): Promise<string>
  // throws Error(detail) using the backend's translated `detail` when present
  PersistenceService.updatePage(bookId: string, pageNum: number, text: string, llmSpellChecked: boolean = false): Promise<void>
  ```
- Removes: `PersistenceService.triggerLlmSpellCheckPage`.

- [ ] **Step 1: Write the failing tests**

In `apps/frontend/src/tests/services/persistenceService.test.ts`, replace the two `triggerLlmSpellCheckPage` tests with:

```ts
  test('previewLlmSpellCheck posts text and returns corrected_text', async () => {
    vi.mocked(authFetch).mockResolvedValue({
      ok: true,
      json: async () => ({ corrected_text: 'fixed' }),
    } as any);
    const controller = new AbortController();

    const result = await PersistenceService.previewLlmSpellCheck('book-1', 5, 'draft', controller.signal);

    expect(result).toBe('fixed');
    expect(authFetch).toHaveBeenCalledWith(
      '/api/books/book-1/pages/5/llm-spell-check/preview',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: 'draft' }),
        signal: controller.signal,
      }
    );
  });

  test('previewLlmSpellCheck throws the backend detail on error', async () => {
    vi.mocked(authFetch).mockResolvedValue({
      ok: false,
      status: 422,
      json: async () => ({ detail: 'translated guardrail error' }),
    } as any);

    await expect(
      PersistenceService.previewLlmSpellCheck('book-1', 5, 'draft')
    ).rejects.toThrow('translated guardrail error');
  });

  test('updatePage sends llm_spell_checked flag', async () => {
    vi.mocked(authFetch).mockResolvedValue({ ok: true } as Response);

    await PersistenceService.updatePage('book-1', 2, 'text', true);

    expect(authFetch).toHaveBeenCalledWith(
      '/api/books/book-1/pages/2/update',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: 'text', llm_spell_checked: true }),
      }
    );
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx vitest run src/tests/services/persistenceService.test.ts`
Expected: FAIL, because `previewLlmSpellCheck is not a function` and the `updatePage` body doesn't match.

- [ ] **Step 3: Implement**

In `persistenceService.ts`, replace the whole `triggerLlmSpellCheckPage` method with:

```ts
  async previewLlmSpellCheck(bookId: string, pageNum: number, text: string, signal?: AbortSignal): Promise<string> {
    const response = await authFetch(`${API_BASE}/books/${bookId}/pages/${pageNum}/llm-spell-check/preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
      signal,
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to run LLM spell check");
    }
    const data = await response.json();
    return data.corrected_text;
  },
```

Replace `updatePage` with:

```ts
  async updatePage(bookId: string, pageNum: number, text: string, llmSpellChecked: boolean = false): Promise<void> {
    const response = await authFetch(`${API_BASE}/books/${bookId}/pages/${pageNum}/update`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, llm_spell_checked: llmSpellChecked })
    });
    if (!response.ok) {
      throw new Error("Failed to update page text");
    }
  },
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npx vitest run src/tests/services/persistenceService.test.ts`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add apps/frontend/src/services/persistenceService.ts apps/frontend/src/tests/services/persistenceService.test.ts
git commit -m "feat(frontend): add LLM spell check preview call and save flag"
```

---

### Task 6: `useLlmSpellCheckPreview` hook

**Files:**
- Create: `apps/frontend/src/hooks/useLlmSpellCheckPreview.ts`
- Test: `apps/frontend/src/tests/hooks/useLlmSpellCheckPreview.test.tsx`

**Interfaces:**
- Consumes: `PersistenceService.previewLlmSpellCheck` (Task 5).
- Produces:
  ```ts
  export interface LlmSpellCheckPreview {
    baselineText: string | null; // text before the latest successful check; null = no check this session
    isChecking: boolean;
    error: string | null;
    runCheck: () => Promise<void>;
    reset: () => void; // aborts any in-flight request and clears all state
  }
  export const useLlmSpellCheckPreview: (
    bookId: string | undefined,
    pageNumber: number,
    tempText: string,
    onTempTextChange: (text: string) => void,
  ) => LlmSpellCheckPreview;
  ```

- [ ] **Step 1: Write the failing tests**

Create `apps/frontend/src/tests/hooks/useLlmSpellCheckPreview.test.tsx`:

```tsx
import { act, renderHook } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import { useLlmSpellCheckPreview } from '@/src/hooks/useLlmSpellCheckPreview';
import { PersistenceService } from '@/src/services/persistenceService';

vi.mock('@/src/services/persistenceService', () => ({
  PersistenceService: { previewLlmSpellCheck: vi.fn() },
}));

beforeEach(() => vi.clearAllMocks());

test('successful check snapshots baseline and replaces text', async () => {
  vi.mocked(PersistenceService.previewLlmSpellCheck).mockResolvedValue('fixed text');
  const onChange = vi.fn();
  const { result } = renderHook(() => useLlmSpellCheckPreview('book-1', 3, 'draft text', onChange));

  await act(async () => { await result.current.runCheck(); });

  expect(PersistenceService.previewLlmSpellCheck).toHaveBeenCalledWith('book-1', 3, 'draft text', expect.any(AbortSignal));
  expect(onChange).toHaveBeenCalledWith('fixed text');
  expect(result.current.baselineText).toBe('draft text');
  expect(result.current.isChecking).toBe(false);
  expect(result.current.error).toBeNull();
});

test('failed check sets error and leaves text and baseline alone', async () => {
  vi.mocked(PersistenceService.previewLlmSpellCheck).mockRejectedValue(new Error('boom'));
  const onChange = vi.fn();
  const { result } = renderHook(() => useLlmSpellCheckPreview('book-1', 3, 'draft', onChange));

  await act(async () => { await result.current.runCheck(); });

  expect(onChange).not.toHaveBeenCalled();
  expect(result.current.baselineText).toBeNull();
  expect(result.current.error).toBe('boom');
  expect(result.current.isChecking).toBe(false);
});

test('reset during an in-flight check aborts it and ignores the result', async () => {
  let resolve!: (v: string) => void;
  vi.mocked(PersistenceService.previewLlmSpellCheck).mockImplementation(
    () => new Promise<string>((r) => { resolve = r; })
  );
  const onChange = vi.fn();
  const { result } = renderHook(() => useLlmSpellCheckPreview('book-1', 3, 'draft', onChange));

  let pending!: Promise<void>;
  act(() => { pending = result.current.runCheck(); });
  expect(result.current.isChecking).toBe(true);

  const signal = vi.mocked(PersistenceService.previewLlmSpellCheck).mock.calls[0][3] as AbortSignal;
  act(() => { result.current.reset(); });
  expect(signal.aborted).toBe(true);

  await act(async () => { resolve('late result'); await pending; });

  expect(onChange).not.toHaveBeenCalled();
  expect(result.current.baselineText).toBeNull();
  expect(result.current.isChecking).toBe(false);
});

test('runCheck is a no-op without a bookId', async () => {
  const { result } = renderHook(() => useLlmSpellCheckPreview(undefined, 3, 'draft', vi.fn()));
  await act(async () => { await result.current.runCheck(); });
  expect(PersistenceService.previewLlmSpellCheck).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx vitest run src/tests/hooks/useLlmSpellCheckPreview.test.tsx`
Expected: FAIL, because the module can't be resolved.

- [ ] **Step 3: Implement**

Create `apps/frontend/src/hooks/useLlmSpellCheckPreview.ts`:

```ts
import { useCallback, useEffect, useRef, useState } from 'react';
import { PersistenceService } from '../services/persistenceService';

export interface LlmSpellCheckPreview {
  baselineText: string | null;
  isChecking: boolean;
  error: string | null;
  runCheck: () => Promise<void>;
  reset: () => void;
}

/**
 * Edit-mode LLM spell check: sends the editor's current text to the
 * non-persisting preview endpoint, swaps the corrected text into the editor,
 * and remembers the pre-check text so changed words can be highlighted.
 */
export const useLlmSpellCheckPreview = (
  bookId: string | undefined,
  pageNumber: number,
  tempText: string,
  onTempTextChange: (text: string) => void,
): LlmSpellCheckPreview => {
  const [baselineText, setBaselineText] = useState<string | null>(null);
  const [isChecking, setIsChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setBaselineText(null);
    setIsChecking(false);
    setError(null);
  }, []);

  useEffect(() => () => abortRef.current?.abort(), []);

  const runCheck = useCallback(async () => {
    if (!bookId || abortRef.current) return;
    const snapshot = tempText;
    const controller = new AbortController();
    abortRef.current = controller;
    setIsChecking(true);
    setError(null);
    try {
      const corrected = await PersistenceService.previewLlmSpellCheck(bookId, pageNumber, snapshot, controller.signal);
      if (controller.signal.aborted) return;
      setBaselineText(snapshot);
      onTempTextChange(corrected);
    } catch (err) {
      if (controller.signal.aborted) return;
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
        setIsChecking(false);
      }
    }
  }, [bookId, pageNumber, tempText, onTempTextChange]);

  return { baselineText, isChecking, error, runCheck, reset };
};
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npx vitest run src/tests/hooks/useLlmSpellCheckPreview.test.tsx`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/frontend/src/hooks/useLlmSpellCheckPreview.ts apps/frontend/src/tests/hooks/useLlmSpellCheckPreview.test.tsx
git commit -m "feat(frontend): add edit-mode LLM spell check preview hook"
```

---

### Task 7: PageItem — AI check button, highlight layer, remove view-mode button

**Files:**
- Create: `apps/frontend/src/components/reader/ChangedWordsLayer.tsx`
- Modify: `apps/frontend/src/components/reader/PageItem.tsx`
- Modify: `apps/frontend/src/locales/en.json`, `apps/frontend/src/locales/ug.json` (the `"reader"` block, after `"llmSpellCheckTitle"`)
- Test: `apps/frontend/src/tests/components/reader/PageItem.test.tsx`

**Interfaces:**
- Consumes: `diffChangedWordRanges`, `ChangedRange` (Task 4); `useLlmSpellCheckPreview` (Task 6).
- Produces:
  - `PageItemProps.onSave: (llmSpellChecked: boolean) => void` (was `() => void`).
  - The `PageItemProps.onLlmSpellCheck` prop is removed.
  - `ChangedWordsLayer` props: `{ text: string; ranges: ChangedRange[]; className?: string; style?: React.CSSProperties }`, forwardRef to a `<div>`. Each highlighted word renders as `<mark data-testid="llm-changed-word">`.
  - i18n keys: `reader.llmSpellCheckChanged` (`{{count}}`), `reader.llmSpellCheckNoChanges`. The existing `reader.llmSpellCheck` / `reader.llmSpellCheckTitle` are reused for the button.

- [ ] **Step 1: Write the failing tests**

In `apps/frontend/src/tests/components/reader/PageItem.test.tsx`:

(a) Add this mock below the existing `vi.mock('@/src/hooks/useAuth', …)` block, and add the import:

```tsx
import { PersistenceService } from '@/src/services/persistenceService';

vi.mock('@/src/services/persistenceService', () => ({
  PersistenceService: { previewLlmSpellCheck: vi.fn() },
}));
```

(b) Delete the three old tests: `PageItem shows LLM spell check button for admin users`, `PageItem hides LLM spell check button when onLlmSpellCheck is not provided`, and `PageItem disables LLM spell check button while llmSpellCheckStatus is in_progress`.

(c) In the existing `PageItem calls onSave and onCancel when buttons are clicked` test, change `expect(onSave).toHaveBeenCalledTimes(1);` to `expect(onSave).toHaveBeenCalledWith(false);`.

(d) Append:

```tsx
const EditingHarness: React.FC<{ initial: string; onSave?: (c: boolean) => void; onCancel?: () => void }> = ({
  initial, onSave = vi.fn(), onCancel = vi.fn(),
}) => {
  const [text, setText] = React.useState(initial);
  return (
    <I18nContext.Provider value={i18nValue}>
      <PageItem
        page={mockPage}
        isActive
        isEditing
        fontSize={18}
        bookId="book-1"
        onSetActive={vi.fn()}
        onEdit={vi.fn()}
        onReprocess={vi.fn()}
        tempText={text}
        onTempTextChange={setText}
        onSave={onSave}
        onCancel={onCancel}
        isLoading={false}
      />
    </I18nContext.Provider>
  );
};

test('PageItem does not show the LLM check button in view mode', () => {
  renderPageItem({ isEditing: false, bookId: 'book-1' });
  expect(screen.queryByTitle('reader.llmSpellCheckTitle')).not.toBeInTheDocument();
});

test('AI check replaces textarea text and highlights changed words', async () => {
  vi.mocked(PersistenceService.previewLlmSpellCheck).mockResolvedValue('Sample page text for test');
  render(<EditingHarness initial="Sample page content for test" />);

  fireEvent.click(screen.getByTitle('reader.llmSpellCheckTitle'));

  const marks = await screen.findAllByTestId('llm-changed-word');
  expect(marks).toHaveLength(1);
  expect(marks[0]).toHaveTextContent('text');
  expect(screen.getByRole('textbox')).toHaveValue('Sample page text for test');
  expect(screen.getByText('reader.llmSpellCheckChanged')).toBeInTheDocument();
});

test('AI check with no changes shows the no-changes message', async () => {
  vi.mocked(PersistenceService.previewLlmSpellCheck).mockResolvedValue('Sample page content for test');
  render(<EditingHarness initial="Sample page content for test" />);

  fireEvent.click(screen.getByTitle('reader.llmSpellCheckTitle'));

  expect(await screen.findByText('reader.llmSpellCheckNoChanges')).toBeInTheDocument();
  expect(screen.queryByTestId('llm-changed-word')).not.toBeInTheDocument();
});

test('AI check failure shows the error and keeps the text', async () => {
  vi.mocked(PersistenceService.previewLlmSpellCheck).mockRejectedValue(new Error('translated error'));
  render(<EditingHarness initial="Sample page content for test" />);

  fireEvent.click(screen.getByTitle('reader.llmSpellCheckTitle'));

  expect(await screen.findByText('translated error')).toBeInTheDocument();
  expect(screen.getByRole('textbox')).toHaveValue('Sample page content for test');
});

test('Save after AI check reports llmSpellChecked=true', async () => {
  vi.mocked(PersistenceService.previewLlmSpellCheck).mockResolvedValue('Sample page text for test');
  const onSave = vi.fn();
  render(<EditingHarness initial="Sample page content for test" onSave={onSave} />);

  fireEvent.click(screen.getByTitle('reader.llmSpellCheckTitle'));
  await screen.findAllByTestId('llm-changed-word');
  fireEvent.click(screen.getByText('common.save'));

  expect(onSave).toHaveBeenCalledWith(true);
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx vitest run src/tests/components/reader/PageItem.test.tsx`
Expected: the new AI-check tests FAIL (no button with title `reader.llmSpellCheckTitle` in edit mode), and the `onSave` test fails because it's called with no argument.

- [ ] **Step 3: Add the locale keys**

In `apps/frontend/src/locales/en.json`, in the `"reader"` block directly after `"llmSpellCheckTitle": "Run LLM-based spell check on this page",` add:

```json
    "llmSpellCheckChanged": "{{count}} word(s) changed — review the highlighted words, then Save or Cancel",
    "llmSpellCheckNoChanges": "No changes suggested",
```

In `apps/frontend/src/locales/ug.json`, add the same two keys after `"llmSpellCheckTitle"` with the **English** values as placeholders. Do not machine-translate them.

- [ ] **Step 4: Create `ChangedWordsLayer`**

Create `apps/frontend/src/components/reader/ChangedWordsLayer.tsx`:

```tsx
import React from 'react';
import { ChangedRange } from '../../utils/wordDiff';

interface ChangedWordsLayerProps {
  text: string;
  ranges: ChangedRange[];
  className?: string;
  style?: React.CSSProperties;
}

/**
 * Renders `text` invisibly, with a background behind each changed word, so it
 * can sit underneath a transparent textarea with identical typography and
 * show which words an LLM spell check changed.
 */
export const ChangedWordsLayer = React.forwardRef<HTMLDivElement, ChangedWordsLayerProps>(
  ({ text, ranges, className = '', style }, ref) => {
    const segments: React.ReactNode[] = [];
    let last = 0;
    ranges.forEach((r, idx) => {
      if (r.start > last) segments.push(<span key={`t${idx}`}>{text.slice(last, r.start)}</span>);
      segments.push(
        <mark
          key={`m${idx}`}
          data-testid="llm-changed-word"
          className="bg-amber-300/70 dark:bg-amber-500/40 text-transparent rounded-sm"
        >
          {text.slice(r.start, r.end)}
        </mark>
      );
      last = r.end;
    });
    if (last < text.length) segments.push(<span key="tail">{text.slice(last)}</span>);

    return (
      <div
        ref={ref}
        aria-hidden="true"
        dir="rtl"
        className={`absolute inset-0 overflow-hidden whitespace-pre-wrap break-words text-transparent pointer-events-none select-none ${className}`}
        style={style}
      >
        {segments}
        {'\n'}
      </div>
    );
  }
);
ChangedWordsLayer.displayName = 'ChangedWordsLayer';
```

- [ ] **Step 5: Wire it into `PageItem.tsx`**

1. Imports: keep `Sparkles` in the `lucide-react` import (the new edit-mode button uses it). Add:
   ```tsx
   import { useLlmSpellCheckPreview } from '../../hooks/useLlmSpellCheckPreview';
   import { diffChangedWordRanges } from '../../utils/wordDiff';
   import { ChangedWordsLayer } from './ChangedWordsLayer';
   ```
2. In `PageItemProps`, delete `onLlmSpellCheck?: () => void;` and change `onSave: () => void;` to `onSave: (llmSpellChecked: boolean) => void;`. Remove `onLlmSpellCheck` from the destructured props.
3. Delete the whole `{onLlmSpellCheck && ( <button …Sparkles…> )}` block from the view-mode toolbar.
4. After the `contentStyle` `useMemo`, add:
   ```tsx
   const llmCheck = useLlmSpellCheckPreview(bookId, page.pageNumber, tempText, onTempTextChange);
   const { reset: resetLlmCheck } = llmCheck;
   React.useEffect(() => {
     if (!isEditing) resetLlmCheck();
   }, [isEditing, resetLlmCheck]);

   const toEditorText = React.useCallback(
     (s: string) => (contentFontClassName === 'reader-font-adobe' ? normalizeArabic(s) : s),
     [contentFontClassName]
   );
   const editorValue = toEditorText(tempText);
   const changedRanges = React.useMemo(
     () => (llmCheck.baselineText === null ? [] : diffChangedWordRanges(toEditorText(llmCheck.baselineText), editorValue)),
     [llmCheck.baselineText, editorValue, toEditorText]
   );
   const highlightLayerRef = React.useRef<HTMLDivElement>(null);
   const isHighlighting = llmCheck.baselineText !== null;
   ```
5. Replace the edit-mode textarea block (the `<div ref={containerRef} …>` with its `<textarea …/>`) with:
   ```tsx
          <div ref={containerRef} className="relative flex-1 flex flex-col min-h-[300px]">
            {isHighlighting && (
              <ChangedWordsLayer
                ref={highlightLayerRef}
                text={editorValue}
                ranges={changedRanges}
                className={`p-4 uyghur-text border-2 border-transparent rounded-xl bg-white dark:bg-slate-800 leading-relaxed ${contentFontClassName || ''}`}
                style={contentStyle}
              />
            )}
            <textarea
              ref={textareaRef}
              value={editorValue}
              onChange={(e) => onTempTextChange(contentFontClassName === 'reader-font-adobe' ? normalizeArabic(e.target.value) : e.target.value)}
              onScroll={(e) => {
                if (highlightLayerRef.current) highlightLayerRef.current.scrollTop = e.currentTarget.scrollTop;
              }}
              readOnly={llmCheck.isChecking}
              className={`flex-1 w-full h-full p-4 uyghur-text border-2 border-[#0369a1] dark:border-[#38bdf8] rounded-xl outline-none resize-none ${isHighlighting ? 'bg-transparent' : 'bg-white dark:bg-slate-800'} text-[#1a1a1a] dark:text-slate-100 relative z-10 custom-scrollbar leading-relaxed ${contentFontClassName || ''}`}
              style={contentStyle}
              dir="rtl"
            />
          </div>
   ```
6. Replace the Save/Cancel button row (`<div className="flex items-center gap-3">…</div>`) with:
   ```tsx
          <div className="flex items-center gap-3 flex-wrap">
            <button
              onClick={() => onSave(isHighlighting)}
              disabled={isSaving || llmCheck.isChecking}
              className="px-6 py-2 bg-[#0369a1] text-white rounded-xl text-sm hover:bg-[#0284c7] transition-all flex items-center gap-2 disabled:opacity-50"
            >
              {isSaving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
              {t('common.save')}
            </button>
            <button
              onClick={() => { resetLlmCheck(); onCancel(); }}
              disabled={isSaving}
              className="px-6 py-2 bg-slate-100 dark:bg-slate-800 text-slate-400 dark:text-slate-500 rounded-xl text-sm transition-all disabled:opacity-30"
            >
              {t('common.cancel')}
            </button>
            {bookId && (
              <button
                onClick={() => { void llmCheck.runCheck(); }}
                disabled={isSaving || llmCheck.isChecking || !tempText.trim()}
                title={t('reader.llmSpellCheckTitle')}
                className="px-4 py-2 bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8] hover:bg-[#0369a1] dark:hover:bg-[#38bdf8] hover:text-white dark:hover:text-slate-950 rounded-xl text-sm transition-all flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {llmCheck.isChecking ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
                {t('reader.llmSpellCheck')}
              </button>
            )}
            {llmCheck.error && (
              <span className="text-sm text-red-600 dark:text-red-400">{llmCheck.error}</span>
            )}
            {!llmCheck.error && isHighlighting && (
              <span className="text-sm text-slate-500 dark:text-slate-400">
                {changedRanges.length === 0
                  ? t('reader.llmSpellCheckNoChanges')
                  : t('reader.llmSpellCheckChanged', { count: changedRanges.length })}
              </span>
            )}
          </div>
   ```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `npx vitest run src/tests/components/reader/PageItem.test.tsx`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add apps/frontend/src/components/reader/ChangedWordsLayer.tsx apps/frontend/src/components/reader/PageItem.tsx apps/frontend/src/locales/en.json apps/frontend/src/locales/ug.json apps/frontend/src/tests/components/reader/PageItem.test.tsx
git commit -m "feat(reader): run LLM spell check in edit mode with changed-word highlights"
```

---

### Task 8: Wire the save flag through and remove the old per-page action

**Files:**
- Modify: `apps/frontend/src/components/reader/VirtualScrollReader.tsx` (prop types ~lines 33–37; destructuring ~68–72; `handlePageLlmSpellCheck` ~370; `handlePageSave` ~374; PageItem props ~439–442)
- Modify: `apps/frontend/src/components/reader/ReaderView.tsx` (`handleUpdatePage` ~381; VirtualScrollReader props ~672–676; PageItem props ~717–722)
- Modify: `apps/frontend/src/hooks/useBookActions.ts` (`handleLlmSpellCheckPage` ~122–147; `handleUpdatePage` ~215; return object ~609)
- Modify: `apps/frontend/src/locales/en.json`, `apps/frontend/src/locales/ug.json` — remove `common.llmSpellCheckPageStarted`, `common.llmSpellCheckPageError`, `modal.llmSpellCheckPage`
- Test: `apps/frontend/src/tests/components/reader/ReaderView.test.tsx`, `apps/frontend/src/tests/hooks/useBookActions.test.tsx`

**Interfaces:**
- Consumes: `PageItemProps.onSave: (llmSpellChecked: boolean) => void` (Task 7); `PersistenceService.updatePage(bookId, pageNum, text, llmSpellChecked)` (Task 5).
- Produces:
  - `VirtualScrollReaderProps.onSave?: (pageNum: number, text: string, llmSpellChecked: boolean) => void`; `onLlmSpellCheck` prop removed.
  - `bookActions.handleUpdatePage(bookId, pageNum, newText, setEditingPageNum, llmSpellChecked = false)`.
  - `bookActions.handleLlmSpellCheckPage` removed.

- [ ] **Step 1: Update the tests first**

In `apps/frontend/src/tests/components/reader/ReaderView.test.tsx`:
- In the mocked PageItem (line ~72), change `<button onClick={onSave}>save-{page.pageNumber}</button>` to `<button onClick={() => onSave(false)}>save-{page.pageNumber}</button>`.
- Line ~257: change the expectation to `toHaveBeenCalledWith('1', 1, 'Page 1 content', expect.any(Function), false)`.
- Line ~292: change the expectation to `toHaveBeenCalledWith('1', 1, 'Page 1 updated', expect.any(Function), false)`.

In `apps/frontend/src/tests/hooks/useBookActions.test.tsx`:
- Remove `triggerLlmSpellCheckPage: vi.fn(),` from the `PersistenceService` mock.
- Delete the tests `useBookActions triggers per-page LLM spell check without blanking page text` and `useBookActions surfaces an error notification when LLM spell check trigger fails`.
- Append:
  ```tsx
  test('handleUpdatePage forwards the llmSpellChecked flag', async () => {
    vi.mocked(PersistenceService.updatePage).mockResolvedValue(undefined);
    const { result } = createHook();

    await act(async () => {
      await result.current.handleUpdatePage('1', 1, 'New Text', vi.fn(), true);
    });

    expect(PersistenceService.updatePage).toHaveBeenCalledWith('1', 1, 'New Text', true);
  });
  ```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx vitest run src/tests/components/reader/ReaderView.test.tsx src/tests/hooks/useBookActions.test.tsx`
Expected: FAIL. The `handleUpdatePage` expectations lack the trailing `false`/`true`.

- [ ] **Step 3: `useBookActions.ts`**

- Delete the whole `handleLlmSpellCheckPage` function and its entry in the returned object.
- Change the `handleUpdatePage` signature and the persistence call:
  ```ts
  const handleUpdatePage = async (bookId: string, pageNum: number, newText: string, setEditingPageNum: any, llmSpellChecked: boolean = false) => {
    try {
      await PersistenceService.updatePage(bookId, pageNum, newText, llmSpellChecked);
  ```
  (The rest of the function is unchanged.)

- [ ] **Step 4: `VirtualScrollReader.tsx`**

- Prop type: change `onSave?: (pageNum: number, text: string) => void;` to `onSave?: (pageNum: number, text: string, llmSpellChecked: boolean) => void;`. Delete `onLlmSpellCheck?: (pageNum: number) => void;` and remove `onLlmSpellCheck,` from destructuring.
- Delete `handlePageLlmSpellCheck`.
- Replace `handlePageSave`:
  ```tsx
  const handlePageSave = useCallback((pageNum: number, text: string, llmSpellChecked: boolean) => {
    setPages(prev => {
      const existing = prev.get(pageNum);
      if (!existing) return prev;
      return new Map(prev).set(pageNum, { ...existing, text });
    });
    onSave?.(pageNum, text, llmSpellChecked);
  }, [onSave]);
  ```
- In the `<PageItem …>` props: delete the `onLlmSpellCheck=…` line and change `onSave={() => handlePageSave(pageNum, tempPageText)}` to `onSave={(llmSpellChecked) => handlePageSave(pageNum, tempPageText, llmSpellChecked)}`.

- [ ] **Step 5: `ReaderView.tsx`**

- Replace `handleUpdatePage`:
  ```tsx
  const handleUpdatePage = async (id: string, num: number, text: string, llmSpellChecked: boolean = false) => {
    setIsSaving(true);
    try {
      await bookActions.handleUpdatePage(id, num, text, setEditingPageNum, llmSpellChecked);
    } finally {
      setIsSaving(false);
    }
  };
  ```
- `<VirtualScrollReader …>`: delete the `onLlmSpellCheck=…` line and change `onSave` to:
  ```tsx
  onSave={(pageNum, text, llmSpellChecked) => {
    handleUpdatePage(selectedBook.id, pageNum, text, llmSpellChecked === true);
  }}
  ```
- `<PageItem …>` (non-virtual list): delete the `onLlmSpellCheck=…` line and change `onSave` to:
  ```tsx
  onSave={(llmSpellChecked) => {
    handleUpdatePage(selectedBook.id, page.pageNumber, tempPageText, llmSpellChecked === true);
    window.scrollTo(0, 0);
  }}
  ```
- If `isAdmin` is now unused in `ReaderView.tsx`, remove it (and its hook call if nothing else uses it). Check with: `grep -n "isAdmin" src/components/reader/ReaderView.tsx`.

- [ ] **Step 6: Remove orphaned frontend locale keys**

Run: `grep -rn "llmSpellCheckPageStarted\|llmSpellCheckPageError\|modal.llmSpellCheckPage\|llmSpellCheckPage\b" src --include=*.ts --include=*.tsx`
Expected: no matches. Then, from both `src/locales/en.json` and `src/locales/ug.json`, delete:
- `"llmSpellCheckPageStarted"` and `"llmSpellCheckPageError"` (in `common`, ~lines 58–59);
- the whole `"llmSpellCheckPage": { … }` object (in `modal`, ~line 893 in en / ~912 in ug).

Validate both files: `node -e "JSON.parse(require('fs').readFileSync('src/locales/en.json'));JSON.parse(require('fs').readFileSync('src/locales/ug.json'));console.log('ok')"`
Expected: `ok`

- [ ] **Step 7: Type-check and run the full frontend suite**

Run: `npx tsc --noEmit`
Expected: no errors. (Any remaining reference to `onLlmSpellCheck`, `handleLlmSpellCheckPage` or `triggerLlmSpellCheckPage` shows up here.)

Run: `npx vitest run`
Expected: whole suite green.

- [ ] **Step 8: Commit**

```bash
git add apps/frontend/src
git commit -m "refactor(reader): pass LLM-checked flag on save; drop view-mode per-page LLM action"
```

---

### Task 9: Docs, OpenAPI, manual verification

**Files:**
- Modify: `docs/main/SPELLCHECK_DESIGN.md` (line ~21 overview, line ~31 config table, lines ~395–399 failure table, line ~439 endpoint table, line ~447 auth note)
- Modify: `docs/main/BOOK_PROCESSING_DIAGRAM.md` (line ~87 mermaid node, line ~142 endpoint table)
- Modify: `docs/main/openapi.json` (regenerated)

- [ ] **Step 1: Update `SPELLCHECK_DESIGN.md`**

- Overview (line ~21): change "triggered exclusively by an admin action (per-page or per-book)" to say that it's triggered per-book by an admin (auto-applied), or per-page by an editor from page edit mode as a non-persisting preview that the editor saves or discards.
- Config table (line ~31): replace "Ignored entirely by the per-page trigger, which always uses the live path." with "Ignored by the edit-mode preview endpoint, which always calls Gemini synchronously."
- Failure table: delete the 409 "already in_progress" row (~399). Remove "or the per-page trigger" from the enqueue-failure row (~397). Add a row: "Edit-mode preview: guardrail rejects output → `422` (`errors.llm_spell_check_invalid_output`); Gemini call fails → `502` (`errors.llm_spell_check_enqueue_failed`); nothing is persisted in either case."
- Endpoint table (line ~439): replace the `POST …/pages/{page_num}/llm-spell-check` row with `POST /api/books/{book_id}/pages/{page_num}/llm-spell-check/preview` | `Depends(require_editor)` | "Runs the LLM correction on the editor's current text (body `{text}`), returns `{corrected_text}`, writes nothing. Changed words are highlighted in edit mode; saving through `POST …/update` with `llm_spell_checked: true` sets `llm_spell_check_status='succeeded'`."
- Auth note (line ~447): the per-page path is now editor-level; only the book-level trigger stays admin-only.

- [ ] **Step 2: Update `BOOK_PROCESSING_DIAGRAM.md`**

- Mermaid node (line ~87): remove the `or /{id}/pages/{n}/llm-spell-check (single page…)` part, so the node describes only the book-level trigger.
- Endpoint table (line ~142): replace the per-page row with the preview endpoint, role `editor`, described as "Non-persisting LLM correction preview for edit mode."

- [ ] **Step 3: Regenerate and check OpenAPI**

Run (repo root): `./venv/bin/python scripts/generate_openapi.py && ./venv/bin/python scripts/check_openapi.py`
Expected: the check passes. The diff of `docs/main/openapi.json` shows the preview path added and the old per-page path removed.

- [ ] **Step 4: Run the backend suite**

Run: `./venv/bin/pytest services/backend/tests -q`
Expected: all pass.

- [ ] **Step 5: Manual verification in the running app**

Run: `./deploy/local/rebuild-and-restart.sh backend && ./deploy/local/rebuild-and-restart.sh frontend`
Then at http://localhost:30080, as an editor, open a book page:
1. In view mode, there's no LLM button on the page toolbar.
2. Click Edit, then the AI check button. A spinner shows, and the textarea is read-only.
3. The text updates, changed words have an amber background aligned exactly under the words (check with both the default and the `reader-font-adobe` fonts, and on a long page that scrolls), and the "N word(s) changed" message shows.
4. Cancel. Reopen Edit and confirm the page text is the original (nothing persisted).
5. Repeat the check, then Save. In the DB, confirm the page's `llm_spell_check_status = 'succeeded'` and that `llm_spell_check_at` is set:
   `psql -h localhost -U <user> -d <db> -c "select llm_spell_check_status, llm_spell_check_at from pages where book_id='<id>' and page_number=<n>;"`

Fix any misalignment in `ChangedWordsLayer` classes (padding, border width, line-height) before continuing.

- [ ] **Step 6: Commit**

```bash
git add docs/main/SPELLCHECK_DESIGN.md docs/main/BOOK_PROCESSING_DIAGRAM.md docs/main/openapi.json
git commit -m "docs: per-page LLM spell check moved to edit-mode preview"
```

- [ ] **Step 7: Hand-off — Uyghur translations needed**

Tell the user that these `ug.json` keys currently hold English placeholders and need their Uyghur translations:
- `services/backend/locales/ug.json`: `errors.llm_spell_check_empty_text`, `errors.llm_spell_check_invalid_output`
- `apps/frontend/src/locales/ug.json`: `reader.llmSpellCheckChanged` (keep `{{count}}`), `reader.llmSpellCheckNoChanges`
