# Kitabim AI internal data inventory for Surya OCR fine-tuning (Uyghur, Arabic script)

Scope: what the kitabim-ai codebase and the local dev database could supply as (page image, ground-truth text) pairs, text corpora, lexicons, and confusion statistics for fine-tuning or evaluating Surya OCR. Researched 2026-10-31 on branch `feature/surya-ocr-fine-tuning` (HEAD `e15a26a8`, plus staged and unstaged changes).

How to read the sources: every source below is a repo path, relative to `/Users/Omarjan/Projects/kitabim-ai`, with line numbers. Counts labelled "DB" come from read-only queries against the local Postgres (`postgresql://kitabim:kitabim@127.0.0.1:5432/kitabim-ai`, from `.env:9`). Each query ran with `default_transaction_read_only=on`, which was confirmed with `show transaction_read_only` → `on`. Nothing was written to the database or to the repo, except this notes file.

---

## 1. Books, pages, page text, chunks, and edit or revision history

### Takeaway
About 236.7k OCR'd pages from 633 books are available as pseudo-ground-truth. Nearly all of the text came from Gemini Vision OCR (currently `gemini-3.7-flash`). The pages have no human-verified flag and no revision history. The text is paragraph-reflowed, not line-preserving, so it cannot be used as line-level ground truth without alignment. The only (before, after) text pairs the schema supports are `pages.prev_text` → `pages.text` from the LLM spell-check, and that column is empty locally.

### Cited Findings
- **`books` table.** ORM model at [packages/backend-core/app/db/models.py:44-160](packages/backend-core/app/db/models.py). Relevant columns:
  - `id` (String(64), an MD5-derived short id)
  - `content_hash`, `title`, `author`, `total_pages`, `status`
  - `file_name`, `file_type` (`pdf` or `docx`)
  - `source` (`upload`, `gcs_sync`, or `surya_local`)
  - `created_by`, `updated_by`, `content_page_offset`, `categories[]`
- **`pages` table.** ORM model at [models.py:162-272](packages/backend-core/app/db/models.py). Relevant columns:
  - `book_id`, `page_number` (unique together), `content_page_number`
  - `text`, `status`, `is_toc`
  - `ocr_milestone`, `spell_check_milestone`, `llm_spell_check_status`, `llm_spell_check_at`
  - `prev_text`, `updated_by`, `last_updated`, `error`, `retry_count`
  - There is no `is_verified` column, no `edited_by` column, and no page-revision or audit table among the ~31 tables (full table list at models.py lines 44-1401).
- **`prev_text` holds only one level of history.** It was added by migration [092_add_llm_spell_check_constraints_and_diff.sql](packages/backend-core/migrations/092_add_llm_spell_check_constraints_and_diff.sql) "to store original text before LLM correction". It is written only by `apply_llm_correction` in [packages/backend-core/app/services/llm_spell_check_service.py:95-140](packages/backend-core/app/services/llm_spell_check_service.py) (`page.prev_text = page.text; page.text = cleaned`). Each later LLM run overwrites it.
- **Human edits leave no trace of the old text.** The editor save path, `POST /books/{book_id}/pages/{page_num}/update` in [services/backend/api/endpoints/books_router.py:2588-2700](services/backend/api/endpoints/books_router.py), overwrites `page.text` and sets `page.updated_by = current_user.email`. It does **not** save the old text to `prev_text`. It also deletes the page's `page_spell_issues` rows and re-chunks the page synchronously.
- **`updated_by` cannot identify human-corrected pages.** Many non-human paths also set it:
  - reprocess endpoints (books_router.py lines 1910-2290 pass `updated_by=current_user.email`)
  - TOC toggles (`pages_repository.py:383-391`)
  - `set_llm_spell_check_status` (`pages_repository.py:397-414`)
  - worker system strings
- **DB distribution of `pages.updated_by`:**
  - `batch_finalizer` 127,806
  - NULL 87,841
  - `contact@kitabim.ai` 12,890
  - `batch_service` 6,739
  - `omarjan.us@gmail.com` 496
  - four UUID-like ids 402 / 72 / 7 / 1
  - `manual_reset` 281, `batch_chunker` 208, `raffypamir@gmail.com` 1
  - 148,891 of the 148,903 non-null rows have `last_updated` in June 2026, which points to bulk operations rather than page-by-page editing.
- **DB counts:**
  - books: 633
  - pages: 236,744; 236,742 with `ocr_milestone='succeeded'`; 235,949 with non-empty text
  - total page text: about 330 MB; average page about 1,465 chars and about 12 newline-separated lines/paragraphs
  - pages with `llm_spell_check_status='succeeded'`: 0; pages with `prev_text`: 0; `batch_llm_spell_check_jobs`: 0
  - chunks: 526,168
- **Books by source (DB):**

  | source / file_type | Books | Pages |
  |---|---|---|
  | `upload` / pdf | 322 | 118,872 |
  | `gcs_sync` / pdf | 306 | 116,183 |
  | `upload` / docx | 4 | 1,420 |
  | NULL / pdf | 1 | 269 |
  | `surya_local` | 0 | — |

  The Surya client upload path sets `source="surya_local"` and `ocr_milestone="complete"` ([books_router.py:1747-1874](services/backend/api/endpoints/books_router.py)). Pages arrive as `OcrPageInput{page_number, text, is_toc}` ([packages/backend-core/app/models/schemas.py:65-77](packages/backend-core/app/models/schemas.py)).
- **The engine for all existing text is Gemini Vision.** [docs/main/OCR_DESIGN.md](docs/main/OCR_DESIGN.md), "Overview": "OCR renders each PDF page to an image (PyMuPDF) and transcribes it with Gemini Vision — there is no local/offline OCR engine." Settings in DB `system_configs`:
  - `ocr_gemini_model=gemini-3.7-flash`
  - `ocr_batch_enabled=true`, `ocr_max_retry_count=10`
  - `ocr_engine=surya`, `ocr_surya_min_confidence=0.3`, `ocr_surya_max_parallel_pages=1`. These last three keys exist in the DB, but grep finds no reference to them in `packages/` or `services/` on this branch. They look like leftovers from a PoC branch.
- **The Gemini prompt tells the model to reflow paragraphs.** `OCR_PROMPT` at [packages/backend-core/app/core/prompts.py:1-38](packages/backend-core/app/core/prompts.py) says "Paragraphs: Keep text continuous within paragraphs. Do NOT insert artificial line breaks to match the page width unless the text is a poem." It also asks for `[Header]`/`[Footer]` line prefixes and pipe tables for TOC pages. Its `<character_accuracy>` section explicitly names confusions:
  - waw-family vowels و/ۇ/ۆ/ۈ/ۋ
  - ڭ/ك, ر/ز, ە/ھ, ف/ق, ع/ح vs غ/خ
  - dropped ى in suffixes such as -غانىدى
  - truncated -ىي nisba endings

  A `{frequent_corrections}` block is filled from active `auto_correct_rules` (OCR_DESIGN.md "Overview").
- **The OCR'd page image is rendered at a low zoom.** Production renders each page to JPEG at `OCR_PAGE_ZOOM_FACTOR` (default 1.5×, i.e. about 108 dpi for a 72-dpi PDF page space) — [packages/backend-core/app/core/config.py:71](packages/backend-core/app/core/config.py) and [packages/backend-core/app/services/ocr_service.py:32-35](packages/backend-core/app/services/ocr_service.py).
- **Observed text shape (DB samples):**
  - Paragraphs are single long lines separated by blank lines, matching the prompt.
  - Many pages still contain `[Footer]` markers: 200,073 pages match `[Footer]` or `[Header]`.
  - Footnotes appear after `---` with ①② markers.
  - Inside a paragraph, line-end hyphenation has already been resolved by Gemini, since the text is reflowed.
  - The remaining `-⏎` hits are mostly cross-page hyphens, where a page ends with a split word, e.g. `…ئەپچىلەم بىلەن مەسلە - ⏎⏎[Footer] 35` and `…ئىككى ئاتقا يۈك - ⏎⏎[Footer] 363`.
- **DB hyphen counts (pages with non-empty text):**
  - hyphen immediately before newline (`-\n`): 7,298 pages
  - spaced hyphen before newline: 5,608
  - glued in-word Arabic-script hyphen `X-Y`: 47,075
  - spaced inline ` - `: 110,995. These are mostly ordinal dates like `1358 – يىلى`, and dashes.
- **Pages can be fetched over the API.**
  - `GET /books/{book_id}/pages/{page_num}` and `GET /books/{book_id}/pages` ([books_router.py:1471, 1511](services/backend/api/endpoints/books_router.py))
  - PDF download via `POST /{book_id}/download-ticket` then `GET /{book_id}/download` ([books_router.py:3222, 3265](services/backend/api/endpoints/books_router.py))

### Inferences
- **Using Gemini text as pseudo-ground-truth.** The text is high quality, judging by the targeted prompt and the low unknown-word rate the spell-check found, but it has three problems:
  - it is paragraph-level, not line-level, so line-level Surya training needs text-line detection plus alignment (forced alignment or matching OCR lines to the reflowed paragraph);
  - it contains page furniture markers (`[Footer]`, `---`, ①) that must be stripped or mapped;
  - Gemini may silently "normalize" spelling, especially because the prompt injects auto-correction rules, so the text is sometimes what the page should say rather than what is printed.
- **Telling human-corrected pages apart is only approximate.** The best heuristic is `updated_by` matching a real user email/UUID, `last_updated` after the bulk June run, and no worker system string. That is roughly 13.9k pages (DB: `contact@kitabim.ai`, `omarjan.us@gmail.com`, `raffypamir@gmail.com` or UUID values), across only 128 distinct books for the two main emails. Even then, `updated_by` may come from a reprocess click rather than a text edit.
- **Cross-page hyphen tails** (`word -` at the end of a page) are a real-world example of the hyphenation the user wants handled.

### Gaps
- It is unknown whether the local DB is a full copy of production. 633 books / 236k pages suggests a prod-like snapshot, but this could not be verified. Prod counts may differ.
- There is no way to tell which pages a human actually proofread. No such flag exists.
- Pages OCR'd by an older Gemini model (before the `gemini-3.7-flash` switch in commit `187c1e8f`, 2026-08-26) are not distinguishable per page. There is no per-page model or engine column.

---

## 2. Lexical resources and confusion pairs (wrong → right)

### Takeaway
Kitabim has a 1.46M-word Uyghur wordlist (`words`), several smaller dictionaries, and three sources of OCR confusion data:
1. 294 curated `auto_correct_rules` (wrong → right word pairs, all active);
2. 5,259 applied corrections in `page_spell_issues` that can be joined to those rules;
3. 677,904 open unknown-word occurrences, each with dictionary-validated candidates.

All three agree that the waw-family vowels dominate the confusions (و/ۇ/ۆ), followed by dropped ى/ي, then ك/ڭ/گ, ن/ڭ, ر/ز, ە/ھ, و/ۋ. No ي/ئې confusion is modelled anywhere.

### Cited Findings

**Lexicon tables (DB row counts, ORM locations):**

| Table | Rows | Columns and notes | Model location |
|---|---|---|---|
| `words` | 1,463,208 | `id`, `word` (unique). The spell-check dictionary, renamed from the old `dictionary` table by migration 058. 1,437,572 rows are pure Arabic-script; 25,636 contain `-`. | [models.py:809-817](packages/backend-core/app/db/models.py) |
| `dictionary` | 20,299 | `word`, `definition`, `audio` | [models.py:820-830](packages/backend-core/app/db/models.py) |
| `history_dictionary` | 6,436 | `term`, `transliteration`, `definition`, `letter_group`, `category`, `significance_score`, `is_ai_generated`, `facts` JSON, `aliases` JSON. Staging table `history_dictionary_staging` sits beside it. | [models.py:1040-1116](packages/backend-core/app/db/models.py) |
| `names_dictionary` | 7,074 | Person names | models.py:1119-1128 |
| `synonyms` | 68,023 | Headword plus `synonyms[]` | models.py:1025-1037 |
| `english_uyghur_dictionary` | 8,124 | English–Uyghur pairs | models.py:1131-1141 |
| `proverbs` | 20,465 | `text`, `volume`, `page_number` | models.py:670-685 |
| `quran` | 6,236 | `text_ar`, `text_en`, `text_ug` | models.py:688-712 |

- **Wordlist export already exists.** `GET /api/dictionary/words-bundle` ([services/backend/api/endpoints/dictionary_router.py:151](services/backend/api/endpoints/dictionary_router.py)) returns one word per line, about 1.5M words. The OCR client caches it at `~/.cache/kitabim-ocr/words_dict.txt` ([clients/kitabim-ocr/engine/dictionary.py:12-60](clients/kitabim-ocr/engine/dictionary.py)).
- **`auto_correct_rules`.** Model at [models.py:874-908](packages/backend-core/app/db/models.py): `misspelled_word` (unique), `corrected_word`, `is_active`, `description`, `created_by`. DB: 294 rows, all active.
  - Editors create rules when they accept a spell-check correction with "auto-correction" ticked ([services/backend/api/endpoints/spell_check_router.py:~362-420](services/backend/api/endpoints/spell_check_router.py), which upserts `AutoCorrectRule(misspelled_word=…, corrected_word=…)`).
  - Admins can also add rules directly ([services/backend/api/endpoints/auto_correct_rules_router.py:213](services/backend/api/endpoints/auto_correct_rules_router.py)).
  - Samples: خوشخۇي→خۇشخۇي, قولوم→قولۇم, ئوزۇندىن→ئۇزۇندىن, مۆندەرىجە→مۇندەرىجە, دەروىشگە→دەرۋىشكە, ئورددا→ئوردا, قەتئىنەزەر→قەتئىينەزەر.
- **`page_spell_issues`.** Model at [models.py:833-871](packages/backend-core/app/db/models.py): `page_id`, `word`, `char_offset`, `char_end`, `ocr_corrections[]` (candidates), `status` (open / corrected / ignored / processing).
  - DB status counts: open 677,904; corrected 5,259; ignored 29.
  - 108,999 distinct words across 193,747 distinct pages.
  - The table does **not** store which candidate was chosen. A corrected page's issue rows are deleted on later edits ([books_router.py:2588-2700](services/backend/api/endpoints/books_router.py)).
  - When a rule is applied, `auto_correct_service.py:173` marks the issue `corrected`, so joining `status='corrected'` to `auto_correct_rules` on `word = misspelled_word` recovers the pair for those cases.
- **How the candidates are generated.** `ocr_corrections` comes from a fixed list of confusable pairs, `_OCR_PAIRS` at [packages/backend-core/app/services/spell_check_service.py:120-141](packages/backend-core/app/services/spell_check_service.py):
  - ك↔ڭ, و↔ۇ, ۆ↔ۇ, ە↔ھ, ن→ڭ, گ↔ك, ۋ↔و, ر↔ز, ق↔ف, ع↔غ, ح↔خ
  - applied as single and double substitutions;
  - plus single vowel insertions from `_VOWEL_INSERTIONS` (ې ى و ۈ ي ا ە ۇ ۆ), lines 180-210;
  - kept only if the result exists in `words`.

  Confidence weights for the strategies are at lines 218-226.
- **Character-level confusion counts.** Computed by difflib over the DB rows:

  | Edit (OCR → correct) | Curated rules (294 pairs) | Applied corrections (5,239 occurrences joined to rules) | Open issues, single-candidate (97,334 distinct pairs / 555,502 occurrences) |
  |---|---|---|---|
  | و→ۇ | 150 | 816 | 126,437 |
  | ۆ→ۇ | 30 | 1,502 | 15,586 |
  | ∅→ى (insertion) | 26 | 2,202 | 174,508 |
  | ۇ→و | 24 | 116 | 36,011 |
  | ە→ھ | 11 | — | 8,294 |
  | ∅→ي (insertion) | 10 | 89 | 32,979 |
  | و→ۆ | 9 | 404 | 5,716 |
  | ك→ڭ | 7 | — | 26,288 |
  | گ→ك | 5 | — | 10,569 |
  | و→ۋ | 4 | — | 7,763 |
  | ۆ→ۈ | 3 | — | — |
  | ۇ→ۆ | — | 108 | — |
  | ۇ→ۈ | — | 108 | — |
  | ن→ڭ | — | — | 15,518 |
  | ر→ز | — | — | 14,253 |
  | ∅→ە | — | — | 13,467 |
  | ز→ر | — | — | 12,481 |
  | ك→گ | — | — | 11,297 |
  | ن→ك | — | — | 10,637 |
  | ∅→ا | — | — | 10,425 |
  | ∅→ۇ | — | — | 7,225 |
  | گ→ڭ | — | — | 7,221 |
  | ۆ→و | — | 4 | 4,184 |
  | ڭ→ك | — | — | 2,716 |

  A dash means that edit was not among the top edits reported for that source. In the open-issue column, each occurrence is counted against the first candidate only. Those open-issue candidates are **unverified** hypotheses, and they are limited to edits `_OCR_PAIRS` and `_VOWEL_INSERTIONS` can generate. The ي/ئې, ز/ژ and ئو/ئۇ/ئۆ/ئۈ cases beyond و/ۇ/ۆ/ۈ are not in `_OCR_PAIRS` at all.
- **The removed Surya client rules show further confusions.** The client's `_ORTHOGRAPHY_CORRECTIONS` (Surya-specific), deleted in commit `e15a26a8` (`git show e15a26a8^:clients/kitabim-ocr/engine/text_cleanup.py`, lines 42-77), captured Surya errors not seen in Gemini text:
  - final ب where Uyghur has پ, in loanwords مەكتەب→مەكتەپ, تەلەب→تەلەپ, كەسىب→كەسىپ, ئەدەب→ئەدەپ, غېرىب→غېرىپ, ئەجەب→ئەجەپ, مەنسەب→مەنسەپ;
  - لالىزار→لالەزار;
  - the question mark ؟ after interrogative مۇ read as م (`…مۇم` → `…مۇ؟`).

### Inferences
- **Weighting a synthetic-noise or evaluation set.** The open-issue distribution, taken as an upper bound and restricted to `_OCR_PAIRS`, together with the applied-rule distribution, gives a realistic prior. Weight insertions of ى/ي (dropped short vowels) and و↔ۇ highest, then ۆ/ۇ, ك/ڭ/گ, ن/ڭ, ر/ز, ە/ھ.
- **Most of these errors are Gemini's.** The confusion data comes almost entirely from Gemini-OCR'd text, not Surya. Surya's own error profile (Arabic-letter bias: ب for پ, ه for ە, م for ؟) differs and must be measured separately.
- **`words` doubles as a lexicon.** It can serve as a constraint for decoding, as a filter for synthetic-text sampling, and as the validator for de-hyphenation (the "p1p2 in words and p1-p2 not in words" rule; see section 4). Its 25,636 hyphenated entries also cover real compounds such as ئاز-ئازدىن.

### Gaps
- No record of which spell-check candidate an editor picked when no rule was created.
- No ي/ئې, ز/ژ or ئې-specific statistics exist anywhere. These would need a new measurement.
- `words` provenance is undocumented here (origin and whether it was itself built from OCR output). `scripts/import_dictionary.py` exists but was not inspected.

---

## 3. Where page images and PDFs live, resolution, and how to fetch an (image, text) pair

### Takeaway
Kitabim stores **no per-page images**, only the source PDFs. Pages are rendered on the fly with PyMuPDF. PDFs live at `uploads/{book_id}.pdf` in the GCS data bucket:
- `ai-kitabim-prod-data-bkt` (prod)
- `ai-kitabim-dev-data-bkt` (dev)

They are mostly scanned image-only PDFs at roughly 280-300 dpi. To build a pair, download the PDF, render page `page_number` at the target zoom, and take `pages.text` for `(book_id, page_number)`.

### Cited Findings
- **Storage settings.** [packages/backend-core/app/core/config.py:40-46](packages/backend-core/app/core/config.py) defines `STORAGE_BACKEND`, `GCS_DATA_BUCKET`, `GCS_MEDIA_BUCKET`, and `uploads_dir = DATA_DIR/uploads`.
  - [deploy/gcp/.env.template:25-27](deploy/gcp/.env.template): `STORAGE_BACKEND=gcs`, `GCS_DATA_BUCKET=ai-kitabim-prod-data-bkt`, `GCS_MEDIA_BUCKET=ai-kitabim-prod-media-bkt`.
  - Local `.env:69-71`: `ai-kitabim-dev-data-bkt` / `ai-kitabim-dev-media-bkt`.
  - Providers: [packages/backend-core/app/services/storage_service.py:17-178](packages/backend-core/app/services/storage_service.py) (filesystem and GCS dual-bucket).
- **PDF path and fallbacks.** The OCR job downloads the PDF from `uploads/{book_id}.pdf`, falling back to `uploads/{file_name}` and then `uploads/{title}.pdf` ([docs/main/OCR_DESIGN.md](docs/main/OCR_DESIGN.md), "OcrJob" step 5). The upload paths write `remote_path = f"uploads/{book_id}.pdf"` ([books_router.py:~1831](services/backend/api/endpoints/books_router.py)).
- **Batch-mode audit copies may contain rendered images.** In batch mode, each request JSONL, which holds base64 JPEG page renders plus the prompt, is uploaded as an audit copy to `batch_ocr/inputs/{job_id}.jsonl` ([packages/backend-core/app/services/batch_ocr_service.py:133](packages/backend-core/app/services/batch_ocr_service.py)). Result locations are recorded in `batch_ocr_jobs.gcs_output_uri` (line 653). Locally `batch_ocr_jobs` has 0 rows.
- **Local copies.** `data/uploads/` holds 3 PDFs (50 MB). One is a real book: `960af8ffa115.pdf`, «تاختا كۆۋرۈك», 263 pages, embedded DeviceGray JPEG pages of 1576×2360 px, about 300 dpi, no text layer.
- **Test fixtures:**
  - [tests/fixtures/](tests/fixtures/): `test_book_1_ocr.pdf` (5 pp), `test_book_4_ocr.pdf` (11 pp, JPX gray, about 150 dpi), `test_book_5_ocr.pdf` (5 pp), `test_book_2_doc.docx`, and `test_book_3_txt.pdf` (20 pp, **born-digital with a text layer**, Arabic/Uyghur bilingual title page).
  - [clients/kitabim-ocr/fixtures/](clients/kitabim-ocr/fixtures/): `test_book.pdf` (15 pp, 1-bit CCITT, about 283 dpi) and `test_book_ocr.pdf`.
- **The bleed-through fixture.** `tests/fixtures/bleed-through.png` is newly staged (`git status`: `A`). It is 1004×1428 RGBA (811 KB): a scanned page crop with verso show-through, used to tune `suppress_bleed_through`. No test file references it by name yet (grep). The staged tests in `clients/kitabim-ocr/tests/engine/test_recognize.py` (+83 lines) use synthetic numpy arrays.
- **Page geometry.** Sampled books' PDF page widths are 378-571 pt, i.e. small-format books. The client's `get_adaptive_page_zoom` raises zoom for pages under 500 pt wide so the page is at least 1500 px wide, clamped to [2.0, 4.0] ([clients/kitabim-ocr/engine/recognize.py:92-112](clients/kitabim-ocr/engine/recognize.py)).

### Inferences
- The source scans are around 300 dpi, much higher than the 1.5× (about 108 dpi) render Gemini saw. Training images can be re-rendered from the PDF's native image resolution, e.g. by extracting the embedded image directly instead of rendering it.
- Born-digital PDFs with a text layer (like `test_book_3_txt.pdf`) would give exact line-level ground truth, including line boxes via `page.get_text("dict")`. The DB has no flag for which books have a text layer; it would need a scan over the PDFs.

### Gaps
- GCS bucket contents, sizes and access were not inspected. No credentials were used.
- DPI distribution across the full corpus is unknown. Only 4 PDFs were sampled.

---

## 4. kitabim-ocr client: how it calls Surya, line handling, de-hyphenation, confusable cleanup

### Takeaway
The client runs Surya's `RecognitionPredictor` in full-page mode, rendering at about 2.5× adaptive zoom. Around it sit heuristics: bleed-through suppression, phantom-block filtering, vertical-marginalia removal, re-OCR of looping blocks, verse grouping, and ghost-text filtering. It keeps Surya's per-print-line breaks.

As of HEAD `e15a26a8` the client has **no de-hyphenation and no confusable-letter correction**. Both were removed together with the Savitr engine. `engine/line_ends.py` and `engine/dictionary.py` remain in the tree but are now unused, and `ocr_page(valid_words=…)` is a dead parameter.

### Cited Findings
- **The Surya call.** [clients/kitabim-ocr/engine/recognize.py:120-146](clients/kitabim-ocr/engine/recognize.py): a lazy singleton `surya.recognition.RecognitionPredictor()`, then `predictor([image], full_page=True)[0]`. The module header says it was vendored from `surya_service.py` on the `poc/easy-ocr-v2` branch.
- **Rendering pipeline.** `ocr_page` (lines 837-925):
  - zoom = adaptive zoom + 0.5 per retry;
  - blank-page check (pixel variance < 25);
  - `suppress_bleed_through` and `enhance_dots_and_contrast` (UnsharpMask radius 1.5, 150%), each controlled by a config flag;
  - `LowConfidenceOcrError` if mean block confidence < 0.3, then the result goes through `clean_uyghur_text` and `is_degenerate_ocr_output`.
  - Default zoom is 2.5 (comment at lines 54-59: "mean confidence ~0.75-0.78 -> ~0.97-0.98 … model+zoom verified together").
- **Line and block handling.** `_process_page_sync` (lines 643-834):
  - drops `PageHeader` blocks, page-number-only `PageFooter` blocks, and vertical side marginalia (h ≥ 1.8w, in the outer 18% of the page; lines 483-507);
  - drops phantom bleed-through blocks by ink contrast against the page's 75th-percentile block contrast (lines 374-461);
  - re-OCRs looping blocks in block mode via `LayoutResult`/`LayoutBox` (lines 545-640);
  - groups vertically adjacent single-line `Text` blocks (≤ 85 chars, gap ≤ 0.45 × line height) into stanzas, **one printed line per output line, never reflowed** (lines 706-830);
  - puts footnotes last; joins blocks with `\n\n`.
- **Surya keeps print-line breaks.** [docs/superpowers/specs/2026-09-10-ocr-line-merge-heuristic-design.md](docs/superpowers/specs/2026-09-10-ocr-line-merge-heuristic-design.md) says Surya's recognizer uses a fixed prompt, "OCR this block image to HTML.", and "reliably preserves per-print-line breaks within a block". It also says `BlockOCRResult` exposes only block-level polygons, not per-line boxes.
- **Current cleanup.** `clean_uyghur_text` ([clients/kitabim-ocr/engine/text_cleanup.py:262-289](clients/kitabim-ocr/engine/text_cleanup.py)):
  - NFKC-maps Arabic presentation forms;
  - normalizes ة/ہ→ە and ے→ې, and the ئ variants;
  - removes ZWNJ, ZWJ, ZWSP and tatweel (lines 21-38);
  - strips `[Header]`/`[Footer]` markers and isolated page numbers;
  - keeps lines as OCR'd.

  Hallucination filters: `is_hallucinated_arabic_block` (Uyghur-vowel ratio < 0.08 plus Arabic particles or ة/ه; lines 430-454), `is_hallucinated_ghost_text` (syllable-repeat loops, low diversity; lines 457-507, **new in the staged diff**), `is_block_repetition_loop`, and `is_degenerate_ocr_output`.
- **What is staged now (`git diff --cached`):**
  - `is_hallucinated_ghost_text` is added and applied to every block type except Table/TOC;
  - `_PHANTOM_CHECK_LABELS` expands to SectionHeader, Title, Caption, Footnote and List-item;
  - `suppress_bleed_through` adds a faint-pixel fraction gate and a speckle mask (BoxBlur, then MinFilter(3) ≥ 115) that lifts thin contour speckles while keeping solid dots, with white point clamped to [175, 200];
  - the block ink-contrast crop is inset and the percentile floor raised to 0.5.
- **What is unstaged now (`git diff`).** It tunes `suppress_bleed_through`: faint-fraction gate 0.025 → 0.014, and blur radius scales with image width (`max(1, min(2, width/1000))`).
- **The removed de-hyphenation (`f2f233a2` / `e5f29e5a`, deleted in `e15a26a8`).** `dehyphenate_uyghur_text` and `spaced_hyphen_candidates` (`git show e15a26a8^:clients/kitabim-ocr/engine/text_cleanup.py`, around lines 290-420) worked like this:
  - A glued hyphen (`p1-p2`) or a line-end hyphen (`p1-\np2`, `p1 -\np2`) was joined when `p1p2 ∈ words` and `p1-p2 ∉ words`.
  - A spaced inline hyphen (`p1 - p2`) was joined only if `engine/line_ends.read_line_end_words` showed `p1` ending a printed line with a hyphen.
  - `read_line_end_words` ([clients/kitabim-ocr/engine/line_ends.py](clients/kitabim-ocr/engine/line_ends.py)) runs the Surya `DetectionPredictor` to get text lines, skips lines narrower than 25% of the widest, and re-recognizes the left 60% of each line (the line end in RTL). It collects words whose trailing characters include a hyphen and maps Arabic ه → ە.
  - The module docstring explains why: full-page Surya "reflows each block into running text, so a line-end hyphen ('ھەز-' / 'رىتى') comes back as 'ھەز - رىتى'".
- **The removed confusable fixes.** `correct_uyghur_ocr_orthography` (see section 2) was also removed in `e15a26a8`.
- **The client and backend auto-correction.** The client explicitly relies on the backend `auto_correct_scanner` to apply `auto_correct_rules` after ingestion (recognize.py docstring, lines 1-7).
- **Existing tests:** `clients/kitabim-ocr/tests/engine/` contains `test_recognize.py`, `test_text_cleanup.py`, `test_line_ends.py` (still exercising the orphaned `read_line_end_words`), `test_dictionary.py`, `test_queue.py`, `test_config.py` and `test_workdir.py`.

### Inferences
- **The hyphen problem a fine-tune could fix.** The real failure is full-page Surya turning `ھەز-⏎رىتى` into `ھەز - رىتى`. Fine-tuning on line-level crops, where the hyphen stays glued to the line-end word, could remove the need for the line-end re-recognition trick. Alternatively, ground truth can keep a canonical form (e.g. `p1-` at line end) for later dictionary-based joining.
- **Hand-written filters as a symptom list.** Each filter (Arabic hallucination, ghost text, loops, bleed-through) records a Surya failure mode on Uyghur scans. These failure modes are useful as negative or edge-case categories in an evaluation set: bleed-through pages, verse pages, footnote pages, TOC pages, and small-format pages.

### Gaps
- Surya version and model checkpoint are not pinned in this notes pass. `clients/kitabim-ocr/requirements.txt` was not opened.
- No measured Surya error statistics on Kitabim pages exist in the repo.

---

## 5. Existing evaluation sets, gold pages, CER/WER tooling, PoC reports

### Takeaway
No OCR gold set, CER/WER script, or OCR PoC report exists on this branch. The only OCR comparison tool is `scripts/compare_ocr.py`, which compares Gemini to the old EasyOCR service with `difflib.SequenceMatcher.ratio()`. Several OCR PoC branches exist (paddleocr, paddle-ocr-spike, chandra-ocr, easy-ocr, easy-ocr-v2, local-ocr, ocr-registry-v1), but none of them contains an OCR eval or report file.

### Cited Findings
- `docs/poc/` contains only `voice-to-text`.
- No file under `scripts/`, `docs/`, `clients/`, `services/` or `packages/` mentions CER, "character error rate", jiwer or levenshtein (grep).
- [scripts/compare_ocr.py](scripts/compare_ocr.py) (header lines 1-40, ratio at line 117-118) renders one PDF page and sends it to Gemini and to an EasyOCR microservice. It prints similarity and a unified diff. [scripts/debug_ocr.py](scripts/debug_ocr.py) also exists.
- For branches `feature/paddleocr-poc`, `origin/feature/paddle-ocr-spike`, `feature/chandra-ocr-poc`, `poc/easy-ocr-v2`, `feature/local-ocr-poc` and `experimental/ocr-registry-v1`, `git ls-tree` filtered for docs/poc, report, eval, cer, gold or ground shows only RAG/ADK evaluation files. No OCR evaluation artifacts.
- Design specs relevant to the Surya client:
  - [docs/superpowers/specs/2026-08-30-surya-ocr-client-design.md](docs/superpowers/specs/2026-08-30-surya-ocr-client-design.md)
  - [2026-08-30-surya-ocr-client-landing-page-design.md](docs/superpowers/specs/2026-08-30-surya-ocr-client-landing-page-design.md)
  - [2026-09-10-ocr-line-merge-heuristic-design.md](docs/superpowers/specs/2026-09-10-ocr-line-merge-heuristic-design.md)
- **The only quantitative Surya claim in code.** Mean block confidence rose from about 0.75-0.78 to about 0.97-0.98 when switching from EasyOCR to Surya at zoom 2.5 "on the same real pages" (recognize.py:54-59). This is model self-confidence, not accuracy.
- **Gemini quality signal.** 677,904 unknown-word occurrences across 193,747 pages, roughly 2.9 per page, against about 1,465 chars per page. An unknown word is one not in `words` and at least 4 characters long (`_MIN_WORD_LEN = 4`, spell_check_service.py:83). Some of these are valid words missing from the lexicon (names, loanwords), so this is a ceiling on Gemini word errors, not a measurement.

### Inferences
- A Surya fine-tuning effort must build its own evaluation set. Candidates:
  - (a) a stratified sample of pages with hand-corrected line-level transcription;
  - (b) the ~13.9k pages whose `updated_by` is a real user, after checking they were actually edited;
  - (c) born-digital text-layer PDFs.
- `compare_ocr.py` gives a starting harness: PDF page → two engines → diff. It needs a CER/WER metric and normalization (strip `[Footer]`, unify reflow) to be useful.

### Gaps
- Whether production `pages` contain any `surya_local` books, or LLM spell-check `prev_text` pairs, is unknown. Both are zero locally.
- The quality of Gemini OCR against a human reference has never been measured in this repo.
