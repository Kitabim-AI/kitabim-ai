# Global Auto-Correction: Uyghur OCR Line-Break De-Hyphenation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate hyphenated word fragments introduced by OCR line breaks (e.g. `ئۇ-رۇقى` → `ئۇرۇقى`, `جەر-\nيانىدا` → `جەريانىدا`) across the local OCR desktop client, backend ingestion, worker spell-check pipeline, and existing production database, with strict preservation of legitimate compound words (e.g. `ئاز-ئازدىن`).

**Architecture:** A unified de-hyphenation algorithm that matches candidate hyphenated words and evaluates against the dictionary: replaces $(w_1 \text{ - } w_2)$ with $(w_1 + w_2)$ only when $w_1\text{-}w_2 \notin \text{words}$ and $w_1w_2 \in \text{words}$. Deployed across local OCR client text cleanup, backend API ingestion defense, worker spell-check self-healing, and an operational CLI backfill script for production.

**Tech Stack:** Python 3.11+, SQLAlchemy Async, PostgreSQL Trigram/GIN (`words` table), FastAPI, httpx, pytest.

---

## Global Constraints

- **LLM Prompts Language Rule**: ALL LLM system prompts in code MUST be written in English.
- **Microservices & Boundaries**: Shared business logic in `packages/backend-core/app/`; local desktop client in `clients/kitabim-ocr/` (standalone, non-containerized).
- **Data Safety**: Reset `chunking_milestone = 'idle'`, `embedding_milestone = 'idle'`, `is_indexed = false` whenever `pages.text` changes. Never delete persistent volumes or database state.
- **Orthographic Condition**: Never de-hyphenate if the hyphenated word exists in `words` (Category A preservation). Never de-hyphenate if the merged word does not exist in `words` (Category C safety).

---

### Task 1: Core De-Hyphenation Function in `backend-core`

**Files:**
- Modify: `packages/backend-core/app/utils/text.py`
- Test: `packages/backend-core/tests/app/utils/text_test.py`

**Interfaces:**
- Produces: `dehyphenate_uyghur_text(text: str, is_valid_word: Callable[[str], bool]) -> tuple[str, int]`
- Produces: `async def dehyphenate_uyghur_text_async(text: str, session: AsyncSession, word_cache: Optional[dict[str, bool]] = None) -> tuple[str, int]`

- [ ] **Step 1: Write the failing tests in `text_test.py`**

```python
def test_dehyphenate_uyghur_text():
    # Mock validator dictionary
    valid_words = {
        "ئۇرۇقى", "دورىلارنى", "قاتارلىق", "سوقۇپ", "بولىدۇ",
        "جەريانىدا", "ئېلىمىز",
        # Legitimate compound words in dictionary
        "ئاز-ئازدىن", "بىر-بىرىگە", "غەم-ئەندىشە",
    }
    def validator(w: str) -> bool:
        return w in valid_words

    # 1. Inline hyphens (Target Category B)
    text = "كاسىنە ئۇ-رۇقى ھەر بىرى 6 گرامدىن دو-رىلارنى بەرسۇن"
    cleaned, count = dehyphenate_uyghur_text(text, validator)
    assert cleaned == "كاسىنە ئۇرۇقى ھەر بىرى 6 گرامدىن دورىلارنى بەرسۇن"
    assert count == 2

    # 2. Line-break hyphens (Target Category B)
    text_nl = "تارىخىي تەرەققىياتى جەر-\nيانىدا شەكىللەندۈرگەن، جۈملىدىن ئې-\nلىمىز تېبابىتى"
    cleaned_nl, count_nl = dehyphenate_uyghur_text(text_nl, validator)
    assert cleaned_nl == "تارىخىي تەرەققىياتى جەريانىدا شەكىللەندۈرگەن، جۈملىدىن ئېلىمىز تېبابىتى"
    assert count_nl == 2

    # 3. Legitimate compound preservation (Category A)
    text_comp = "تاماقنى ئاز-ئازدىن بېرىپ، بىر-بىرىگە يېقىنلاشتۇرۇش لازىم"
    cleaned_comp, count_comp = dehyphenate_uyghur_text(text_comp, validator)
    assert cleaned_comp == text_comp
    assert count_comp == 0

    # 4. Unknown / non-dictionary preservation (Category C)
    text_unk = "ئاچچىق-تاتلىق ئانار سۈيى"
    cleaned_unk, count_unk = dehyphenate_uyghur_text(text_unk, validator)
    assert cleaned_unk == text_unk
    assert count_unk == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest packages/backend-core/tests/app/utils/text_test.py -k test_dehyphenate_uyghur_text`
Expected: FAIL with `ImportError: cannot import name 'dehyphenate_uyghur_text'`

- [ ] **Step 3: Implement `dehyphenate_uyghur_text` and `dehyphenate_uyghur_text_async` in `text.py`**

Add regex matching for Uyghur word chars + hyphens:
```python
_UYGHUR_WORD_PATTERN = r"[\u0621-\u064A\u0671-\u06D5\u06EE-\u06EF\uFB50-\uFDFF\uFE70-\uFEFF]+"
_DEHYPHEN_NL_RE = re.compile(rf"({_UYGHUR_WORD_PATTERN})[\t ]*-[\t ]*[\r\n]+[\t ]*({_UYGHUR_WORD_PATTERN})")
_DEHYPHEN_INLINE_RE = re.compile(rf"({_UYGHUR_WORD_PATTERN})-({_UYGHUR_WORD_PATTERN})")
```
Implement the logic:
1. Check `if '-' not in text: return text, 0`
2. First pass: line-break hyphens `_DEHYPHEN_NL_RE`
3. Second pass: inline hyphens `_DEHYPHEN_INLINE_RE`
4. Also implement the async DB-backed version `dehyphenate_uyghur_text_async(text, session, word_cache)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest packages/backend-core/tests/app/utils/text_test.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/backend-core/app/utils/text.py packages/backend-core/tests/app/utils/text_test.py
git commit -m "feat(backend-core): add Uyghur OCR de-hyphenation utility functions"
```

---

### Task 2: Ingestion Defense in Backend API & Dictionary Words Endpoint

**Files:**
- Modify: `services/backend/api/endpoints/books_router.py`
- Modify: `services/backend/api/endpoints/dictionary_router.py`
- Test: `services/backend/tests/api/test_books_router.py` (or appropriate router test)

**Interfaces:**
- Produces: `GET /api/dictionary/words-bundle` (returns gzipped plain text list of valid words for client caching)
- Modifies: `POST /books/{book_id}/pages/{page_num}/update` (dehyphenates page text)
- Modifies: `POST /books/upload-ocrd` (dehyphenates pages text in payload)

- [ ] **Step 1: Add `GET /api/dictionary/words-bundle` endpoint in `dictionary_router.py`**

Provides compressed words list stream to authenticated clients with `ETag` and `Cache-Control: public, max-age=604800` (7 days).

- [ ] **Step 2: Add de-hyphenation call to `update_page_text_endpoint` and `upload_ocrd` in `books_router.py`**

Prior to saving `new_text = normalize_uyghur_chars(new_text)`:
```python
new_text, _ = await dehyphenate_uyghur_text_async(new_text, session)
```

- [ ] **Step 3: Run backend router tests to verify no regressions**

Run: `pytest services/backend/tests/`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add services/backend/api/endpoints/books_router.py services/backend/api/endpoints/dictionary_router.py
git commit -m "feat(backend): add dictionary words-bundle endpoint and OCR ingestion de-hyphenation"
```

---

### Task 3: Worker Spell Check Pipeline Self-Healing

**Files:**
- Modify: `packages/backend-core/app/services/spell_check_service.py`
- Test: `packages/backend-core/tests/app/services/spell_check_service_test.py`

**Interfaces:**
- Integrates `dehyphenate_uyghur_text_async` into `run_spell_check_for_page(session, page, cache)`.

- [ ] **Step 1: Write test for spell check de-hyphenation in `spell_check_service_test.py`**

Verify that a page containing `ئۇ-رۇقى` has its `page.text` automatically rewritten to `ئۇرۇقى` during `run_spell_check_for_page`, and returns 0 spell issues because the corrected word is in the dictionary.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest packages/backend-core/tests/app/services/spell_check_service_test.py -k test_spell_check_dehyphenation`

- [ ] **Step 3: Integrate `dehyphenate_uyghur_text_async` into `run_spell_check_for_page`**

In `spell_check_service.py`:
Run `raw_text, dehyphen_count = await dehyphenate_uyghur_text_async(raw_text, session)` right alongside active auto-correct rules. If `dehyphen_count > 0`, set `text_changed = True`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest packages/backend-core/tests/app/services/spell_check_service_test.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/backend-core/app/services/spell_check_service.py packages/backend-core/tests/app/services/spell_check_service_test.py
git commit -m "feat(spell-check): integrate dynamic de-hyphenation in page spell-check pipeline"
```

---

### Task 4: Local OCR Client (`clients/kitabim-ocr`) De-Hyphenation & Dictionary Cache

**Files:**
- Create: `clients/kitabim-ocr/engine/dictionary.py`
- Modify: `clients/kitabim-ocr/engine/text_cleanup.py`
- Modify: `clients/kitabim-ocr/engine/recognize.py`
- Test: `clients/kitabim-ocr/tests/engine/test_text_cleanup.py`

**Interfaces:**
- `DictionaryManager.get_valid_words(client: Optional[KitabimClient]) -> set[str]`
- Updates `clean_uyghur_text(text: str, valid_words: Optional[set[str]] = None) -> str`

- [ ] **Step 1: Write test in `clients/kitabim-ocr/tests/engine/test_text_cleanup.py`**

Test that `clean_uyghur_text` dehyphenates when dictionary set is provided, and preserves compound words.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest clients/kitabim-ocr/tests/engine/test_text_cleanup.py -k test_clean_uyghur_text_dehyphenates`

- [ ] **Step 3: Implement `DictionaryManager` and wire into `clean_uyghur_text` & `recognize.py`**

- `engine/dictionary.py`: Downloads or loads `~/.cache/kitabim-ocr/words_dict.txt`.
- `engine/text_cleanup.py`: Adds de-hyphenation pass in `clean_uyghur_text`.
- `engine/recognize.py`: Passes cached dictionary set to `clean_uyghur_text`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest clients/kitabim-ocr/tests/engine/`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add clients/kitabim-ocr/engine/ clients/kitabim-ocr/tests/
git commit -m "feat(kitabim-ocr): add local dictionary caching and de-hyphenation in OCR engine"
```

---

### Task 5: Production Operational Backfill Script (`scripts/dehyphenate_books.py`)

**Files:**
- Create: `scripts/dehyphenate_books.py`
- Test: Run with `--dry-run` on local database and production database

**Interfaces:**
- CLI: `python scripts/dehyphenate_books.py [--dry-run] [--book-id <id>] [--all] [--limit <n>]`

- [ ] **Step 1: Write `scripts/dehyphenate_books.py`**

Features:
- Connects using `app.db.session`.
- Scans `pages` with `text LIKE '%-%'`.
- De-hyphenates using the verified condition.
- In `--dry-run` mode: outputs detailed summary table (book ID, page numbers, word replacements, counts) without modifying DB.
- In execution mode:
  - Updates `pages.text`.
  - Sets `chunking_milestone = 'idle'`, `embedding_milestone = 'idle'`, `is_indexed = false`.
  - Deletes stale `page_spell_issues` on the page.
  - Commits in safe batches per book.

- [ ] **Step 2: Test script with `--dry-run` locally**

Run: `python scripts/dehyphenate_books.py --dry-run --limit 5`
Verify clean execution and report.

- [ ] **Step 3: Commit**

```bash
git add scripts/dehyphenate_books.py
git commit -m "feat(scripts): add production-ready operational de-hyphenation backfill script"
```

---

## Plan Review Checklist
- [x] All requirements from spec covered.
- [x] Strict condition enforced (Category B dehyphenated, Category A compounds protected, Category C untouched).
- [x] Local OCR client covered (source of the issue).
- [x] Ingestion defense covered (API routes).
- [x] Pipeline covered (worker spell check).
- [x] Backfill covered (operational script).
- [x] Exact file paths and code provided.
