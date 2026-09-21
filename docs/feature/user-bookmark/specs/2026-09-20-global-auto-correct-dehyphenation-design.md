# Global Auto-Correction: Uyghur OCR Line-Break De-Hyphenation Design

**Date**: 2026-09-20  
**Branch**: `feature/user-bookmark`  
**Status**: Approved  

---

## 1. Background & Problem Statement

In printed Uyghur books, typesetters frequently break words across lines using hyphens (`-`). During OCR (both local Surya OCR in `clients/kitabim-ocr` and worker-based OCR), these hyphenated split words are captured into digital text as:
1. Inline hyphens: `word1-word2` (e.g. `ئۇ-رۇقى`, `دو-رىلارنى`, `قاتار-لىق`, `سو-قۇپ`, `بو-لىدۇ`)
2. Line-break hyphens: `word1-\nword2` (e.g. `جەر-\nيانىدا`, `ئې-\nلىمىز`, `ئە-\nسەرلەر`, `خاسلىق-\nقا`)

Because modern Uyghur orthography does not use hyphens inside words (except for legitimate compound words like `ئاز-ئازدىن`, `بىر-بىرىگە`, `غەم-ئەندىشە`), these OCR-retained hyphens corrupt full-text search, degrade chunk embeddings, and fragment words. Furthermore, the existing dictionary spell-checker tokenizes text by treating hyphens as non-word boundaries, creating 0 spell-check issues for these words and leaving them permanently broken in `pages.text`.

---

## 2. The Auto-Correction Rule & Condition

A global algorithmic correction rule is established with the following strict condition:

$$\text{Action: Replace } (word_1 \text{ [dash] } word_2) \rightarrow (word_1 + word_2)$$

### Condition:
1. **Target Pattern**: A candidate word with a dash `word1-word2` or `word1-\nword2`.
2. **Exclusion (Compound Safety)**: The hyphenated form (`word1-word2`) **must NOT exist** in the `words` dictionary table.
3. **Inclusion (Spelling Validity)**: The merged form (`word1word2`) **MUST exist** in the `words` dictionary table.

### Production Data Verification Results
Tested against 50 latest production books (18,570 pages with hyphens):
- **Category B (Target Matches)**: **3,528 distinct words, 6,194 occurrences** (4,993 inline, 1,201 newline). 100% of examined samples were genuine typographic line splits.
- **Category A (Protected Compounds)**: **25,636 compound words** exist in the dictionary with `-` (e.g. `ئاز-ئازدىن`, `غەم-ئەندىشە`, `بىر-بىرىگە`). All 4,511 occurrences were safely preserved.
- **Category C (Unknown / Non-dictionary terms)**: Neither form in dictionary (e.g. rare botanical terms, compound phrases without dictionary entries). Untouched. Zero regressions observed.

---

## 3. Architecture & End-to-End Flow

To prevent issues from continuing while fixing existing data, the solution covers all layers of the system:

```
[Local Hardware]
clients/kitabim-ocr/
  └── Text Cleanup Engine (text_cleanup.py)
        └── Local Dictionary Cache (~/.cache/kitabim-ocr/words_dict.txt)
              └── De-hyphenates text BEFORE user preview and API push

[HTTP API Ingestion Defense]
services/backend/api/endpoints/
  ├── POST /books/upload-ocrd
  └── POST /books/{book_id}/pages/{page_num}/update
        └── Backend dehyphenate_uyghur_text validation (against DB words table)

[Pipeline Self-Healing]
services/worker/ / spell_check_service.py
  └── run_spell_check_for_page
        └── Inline de-hyphenation pass before tokenization
              └── If text modified: updates page.text, resets chunking/embedding milestones

[Production Backfill]
scripts/dehyphenate_books.py
  └── Standalone operational script with --dry-run, --book-id, and --all flags
```

---

## 4. Detailed Component Design

### 4.1 Core De-Hyphenation Function
**Locations**:
- Shared backend library: `packages/backend-core/app/utils/text.py` (`dehyphenate_uyghur_text`)
- Local OCR client: `clients/kitabim-ocr/engine/text_cleanup.py` (`dehyphenate_uyghur_text`)

**Signatures**:
```python
# In backend-core (can query DB or use cached word set)
async def dehyphenate_uyghur_text(
    text: str,
    session: AsyncSession,
    word_cache: Optional[dict[str, bool]] = None,
) -> tuple[str, int]:
    """
    De-hyphenates line-broken words matching the condition:
    (w1-w2 not in words) and (w1w2 in words).
    Returns (cleaned_text, replacement_count).
    """

# In kitabim-ocr (uses local set of valid words)
def dehyphenate_uyghur_text(
    text: str,
    valid_words: set[str],
) -> tuple[str, int]:
    """Local in-memory de-hyphenation using loaded dictionary set."""
```

**Matching Logic**:
- Patterns:
  - `re.compile(rf'({uyghur_word})-({uyghur_word})')`
  - `re.compile(rf'({uyghur_word})[\t ]*-[\t ]*[\r\n]+[\t ]*({uyghur_word})')`
- For each match:
  - `cand_hyphen = f"{p1}-{p2}"`
  - `cand_merged = f"{p1}{p2}"`
  - If `cand_hyphen not in valid_words` and `cand_merged in valid_words`:
    - Substitute `cand_merged`.

### 4.2 Local OCR Client Dictionary Cache
- Endpoint: `GET /api/dictionary/words-bundle` in `services/backend/api/endpoints/dictionary_router.py`. Returns compressed plain text or JSON list of words.
- Local Storage: `clients/kitabim-ocr/engine/dictionary.py` manages `~/.cache/kitabim-ocr/words_dict.txt`.
- Loaded lazily as a Python `set` (~50MB RAM, <100ms load time).
- If offline and cache is missing, skips de-hyphenation gracefully without raising errors (backend ingestion defense acts as fallback).

### 4.3 Ingestion Defense in Backend
- In `services/backend/api/endpoints/books_router.py`:
  - `upload_ocrd_book`: When iterating through incoming `pages.json`, pass each page's text through `dehyphenate_uyghur_text`.
  - `update_page_text_endpoint`: Clean incoming text before saving and re-chunking.

### 4.4 Worker Spell Check Self-Healing
- In `packages/backend-core/app/services/spell_check_service.py` (`run_spell_check_for_page`):
  - Prior to tokenization, run `dehyphenate_uyghur_text`.
  - If replacements occurred, set `text_changed = True`, update `page.text`, and trigger milestone reset.

### 4.5 Production Backfill Script (`scripts/dehyphenate_books.py`)
- CLI features:
  - `--dry-run`: Scans pages, outputs summary table of matched words, frequencies, and affected pages.
  - `--book-id <id>`: Target a specific book.
  - `--all`: Process all books.
  - `--limit <n>`: Limit number of books.
- Database transaction safety:
  - For each changed page:
    - Update `pages.text`.
    - Set `chunking_milestone = 'idle'`, `embedding_milestone = 'idle'`, `is_indexed = false`.
    - Delete stale `page_spell_issues` for that page (character offsets are shifted).
    - Commit per book or batch of 50 pages to prevent lock contention.

---

## 5. Testing & Verification Plan

1. **Unit Tests**:
   - Test `dehyphenate_uyghur_text` in `packages/backend-core/tests/app/utils/text_test.py`:
     - Inline hyphens (`ئۇ-رۇقى` $\rightarrow$ `ئۇرۇقى`)
     - Newline hyphens (`جەر-\nيانىدا` $\rightarrow$ `جەريانىدا`)
     - Compound preservation (`ئاز-ئازدىن` $\rightarrow$ `ئاز-ئازدىن`)
     - Unknown term preservation (`ئاچچىق-تاتلىق` $\rightarrow$ `ئاچچىق-تاتلىق`)
   - Test client text cleanup in `clients/kitabim-ocr/tests/engine/test_text_cleanup.py`.
2. **Integration Tests**:
   - Verify `update_page_text_endpoint` properly applies de-hyphenation.
   - Verify `run_spell_check_for_page` applies de-hyphenation and updates `page.text`.
3. **Production Dry-Run**:
   - Run `scripts/dehyphenate_books.py --dry-run` on production to verify expected counts and review sample outputs before any commit.
