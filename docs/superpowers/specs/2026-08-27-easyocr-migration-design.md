# EasyOCR Migration Design

**Date:** 2026-08-27
**Branch:** `poc/easy-ocr`
**Status:** Approved — ready for implementation planning

## Motivation

The current OCR stage sends every scanned page image to the Gemini Vision API (`packages/backend-core/app/core/prompts.py` `OCR_PROMPT`, called from `ocr_service.py`/`batch_ocr_service.py`). This requires sending book page images to a third-party cloud API. The requirement driving this design is **data privacy / offline processing** — OCR must run fully self-hosted, with no scanned page content leaving the infrastructure. EasyOCR (local, self-hosted, CPU-capable) replaces Gemini as the OCR engine.

This is a **full replacement**, not a coexistence/feature-flagged option: once shipped, EasyOCR is the only active OCR path. Gemini's code is kept in place but unused (see "Out of scope" below) rather than deleted, preserving the option to reinstate it later without a re-implementation.

## Current State (for context — unchanged by this design except where noted)

- **Pipeline shape:** `ocr_scanner.py` claims idle `Page` rows per book (`FOR UPDATE SKIP LOCKED`), enqueues one `ocr_job` per book with the claimed `page_ids`. `ocr_job.py` downloads the book's PDF once, renders each page to a JPEG via PyMuPDF (`fitz`), and — today — sends each rendered page image to Gemini Vision, bounded by `asyncio.Semaphore(max_parallel_pages)`.
- **Gemini's prompt does more than transcription** — it asks the model to also emit structure: `#`/`##` Markdown headings for titles/chapters, `[Header]`/`[Footer]` tags on their own line for physical page furniture (running headers, footers, page numbers), bare pipe-table rows for detected TOC pages, and preserved line breaks for poems. It also gives the model contextual rules for disambiguating visually similar Perso-Arabic letters (و/ۇ/ۆ/ۈ/ۋ, ڭ vs ك, ھ vs ە, ف vs ق, ع/ح→غ/خ, suffix-vowel dropping, -ىي truncation) and a DB-backed `frequent_corrections` list (`AutoCorrectRulesRepository`) it's asked to auto-apply.
- **Storage:** OCR output is stored verbatim as Markdown in `pages.text` after passing through `clean_uyghur_text` (`app/utils/text.py`), which NFKC-normalizes characters, strips `[Header]`/`[Footer]`-tagged content entirely (page furniture is discarded, never shown to readers), joins hyphen-split words, and re-flows paragraphs. `is_toc_page(text)` then sets `Page.is_toc`, which drives `content_page_offset` and the reader's clickable TOC navigation (`MarkdownContent.tsx`).
- **Retry semantics:** an inner per-call retry loop (transient API errors, `DegenerateOcrOutputError` for repetition-loop hallucination) and an outer pipeline-level retry budget (`ocr_max_retry_count`) that soft-skips a page to `text=""`, `ocr_milestone='succeeded'` after exhaustion — deliberately not `failed`, so one bad page never blocks a book.
- **Dependencies:** `services/worker/requirements.worker.txt` currently has none beyond backend packages; this is a from-scratch integration.

## Compute Target

**CPU-only.** No GPU is available in the deployment target. This has two consequences threaded through the whole design:
1. Per-page latency will be materially higher than the Gemini API call it replaces.
2. Concurrency per worker process must be low (near 1-2, tuned empirically); horizontal scaling (more worker container replicas) is the primary throughput lever, not per-process parallelism.

## Phasing

### Phase 0 — Validation spike (blocking gate)

Before any pipeline code changes, run ~20-30 real scanned pages (spanning several already-ingested books — a mix of body text, a title/chapter page, a TOC page, and a poem page if one exists) through `easyocr.Reader(['ug'], gpu=False)` in a standalone throwaway script (not wired into the pipeline). Compare the raw transcribed text against the corresponding `pages.text` already stored from Gemini:
- Character-level accuracy, specifically on the letter-confusion pairs the Gemini prompt calls out.
- Word-level completeness (dropped/merged words).
- Per-page latency on the actual CPU target, to calibrate concurrency and horizontal scaling needs.

This is a go/no-go gate. If accuracy is far below Gemini's, the project pauses here for a decision (e.g. the local-LLM-restructuring alternative below, or a custom fine-tune) before building structural heuristics on top of unproven transcription.

### Phase 1 — Full replacement build

Once Phase 0 passes, wire EasyOCR into `ocr_job.py` as the only inline OCR path, with geometric structural heuristics and rule-based character correction, as detailed below.

## Architecture

New modules, parallel to the existing (now-dormant) Gemini ones:

```
packages/backend-core/app/
  core/prompts.py               # unchanged — Gemini's OCR_PROMPT stays, dormant
  services/
    ocr_service.py              # unchanged — Gemini path stays, dormant
    batch_ocr_service.py        # unchanged — dormant
    easyocr_service.py          # NEW — engine entry point
  utils/
    text.py                     # clean_uyghur_text, is_toc_page — reused as-is
    ocr_structure.py            # NEW — geometric reconstruction & classification
    ocr_corrections.py          # NEW — rule-based frequent_corrections post-process
```

`easyocr_service.py` exposes `ocr_page_with_easyocr(fitz_page, reader, timeout) -> str`, matching the signature shape of today's `ocr_page_with_gemini`. `ocr_job.py` changes at one call site: the `ocr_engine` system_config (`gemini` | `easyocr`, defaulted to `easyocr` once shipped) selects which function is called, replacing today's `ocr_batch_enabled` branch when the engine is `easyocr` (batch mode has no EasyOCR equivalent and becomes inert under that engine). Everything else in `ocr_job.py` — `MultiPageLock`, PDF download, PyMuPDF rendering, the semaphore, the outer retry/skip state machine, `PipelineEvent` emission, `sync_content_page_offset` — is engine-agnostic and unchanged.

The `easyocr.Reader` is expensive to construct (loads model weights) and must be a **module-level singleton** per worker process, built once on first use — never per-page or per-job. Since `.readtext()` is a synchronous, CPU-bound blocking call, it runs via `loop.run_in_executor()` on a dedicated `ThreadPoolExecutor` sized to match the low CPU-bound concurrency ceiling, so it never blocks the worker's asyncio event loop.

## Reading Order & Structural Classification (`ocr_structure.py`)

EasyOCR returns `[(bbox, text, confidence), ...]` in arbitrary detection order with no semantic labels. Reconstruction stages:

1. **Line clustering** — group boxes whose vertical centers overlap within a tolerance into the same line.
2. **RTL ordering** — within a line, sort boxes by x-coordinate **descending** (Uyghur is right-to-left); lines are ordered top-to-bottom as usual.
3. **Paragraph grouping** — group consecutive lines into paragraphs by vertical gap, mirroring `clean_uyghur_text`'s existing block-splitting logic.
4. **Header/footer band filter** — lines whose vertical center falls within the top or bottom `ocr_easyocr_header_footer_band_pct` of the page height are classified as physical header/footer and **excluded from the assembled body text**, matching today's behavior (this content is discarded, never shown to readers, regardless of engine).
5. **Heading detection** — compute the median line-height (bbox height, a font-size proxy) across body lines; a line exceeding the median by `ocr_easyocr_heading_size_ratio` and short relative to the page's text-block width is classified as a heading, mapped to `#`/`##` by relative size tier.
6. **TOC detection** — after assembling a page's plain text, reuse `is_toc_page(text)` **unchanged** (already text-pattern-based: dot-leaders + page-number progression, not Gemini-specific). Matching lines are reformatted into the same bare pipe-row convention (`| text | page |`, no header/separator row) `MarkdownContent.tsx` already parses.
7. **Poem detection** — within a paragraph, a run of consecutive short lines that don't extend near the right text margin is treated as verse and keeps hard line breaks rather than being joined into flowing prose.

The assembled markdown is then passed through the existing, **unchanged** `clean_uyghur_text` for normalization.

## Character-Accuracy Correction (`ocr_corrections.py`)

Gemini's contextual letter-disambiguation and its `frequent_corrections` auto-fix relied on the model's reasoning — EasyOCR's CRNN+CTC decoder has none. The `frequent_corrections` data (from `AutoCorrectRulesRepository`, currently injected as prompt text) is reapplied as a **post-hoc regex find/replace pass** on the assembled EasyOCR output — same data source, new consumer. The harder-to-generalize letter-confusion pairs (context-dependent, not simple word substitutions) are not fully replicable this way; Phase 0's spike output determines whether the residual error rate is acceptable or whether a handful of the most common confusion patterns need dedicated regex rules.

## Error Handling & Retries

The outer pipeline-level retry/skip state machine (`retry_count`, `ocr_milestone`, soft-skip-to-`text=""` after exhaustion) is unchanged — it's engine-agnostic. What changes is the *inner* retry's purpose and the degenerate-output check:

- EasyOCR is deterministic given the same input image — retrying the exact same render produces the exact same result. Inner retries (triggered by exceptions, e.g. OOM, corrupted render) must **vary the input** on each attempt (e.g. bump render zoom/DPI, apply contrast normalization) rather than blindly repeating, or the retry has zero chance of a different outcome.
- `is_degenerate_ocr_output` (Gemini's repetition-loop hallucination detector) is dropped — irrelevant to a non-generative model. It's replaced by a **low-confidence check**: if EasyOCR's mean detection confidence falls below `ocr_easyocr_min_confidence` and the page isn't legitimately blank (checked against image pixel variance), the page is treated as failed and eligible for the varied-input retry above.

## New `system_configs` Keys

Following the existing `ocr_*` naming convention; all DB-driven per the worker-designer convention of never hardcoding tuneables:

| Key | Purpose | Notes |
|---|---|---|
| `ocr_engine` | `gemini` \| `easyocr` selector | defaults to `easyocr` once shipped; keeps Gemini path reachable without code changes |
| `ocr_easyocr_max_parallel_pages` | per-process concurrency ceiling | default low (e.g. `1`); tuned in Phase 0/1 against real CPU throughput |
| `ocr_easyocr_header_footer_band_pct` | margin band for header/footer exclusion | default ~`0.08`, tuned against real scans |
| `ocr_easyocr_heading_size_ratio` | bbox-height threshold for heading detection | default ~`1.3` |
| `ocr_easyocr_min_confidence` | threshold for the low-confidence retry trigger | tuned from Phase 0 spike data |

## Dependencies & Offline Deployment

`services/worker/requirements.worker.txt` gains `easyocr` and a CPU-only `torch` build (avoiding CUDA wheels, since compute target is CPU-only). Because the whole point of this migration is offline processing, EasyOCR's default behavior of downloading model weights at first `Reader()` construction must not happen at runtime in production — the `ug` recognition and CRAFT detector model weights are fetched once at image-build time and baked into `Dockerfile.worker`, so no outbound network call occurs when a book is actually processed.

## Testing

- Unit tests for `ocr_structure.py`'s classification functions against synthetic bbox fixtures — no need to invoke real EasyOCR in unit tests (mock `reader.readtext()`'s return shape).
- Unit tests for `ocr_corrections.py` against existing `AutoCorrectRulesRepository` fixtures.
- Update `services/worker/tests/jobs/ocr_job_test.py`'s existing cases (`test_ocr_job_success`, `_failure_retry`, `_failure_exhausted_skip`) to exercise the EasyOCR call path.

(Full test conventions to be applied by `/worker-unit-tester` during implementation.)

## Out of Scope / Left Dormant

- `ocr_service.py` (Gemini inline path), `batch_ocr_service.py`, the `batch_ocr_jobs` table, and `batch_ocr_poller_scanner.py` are **not modified or removed** — they remain reachable via `ocr_engine=gemini` but are not exercised once EasyOCR is the default.
- No changes to `MarkdownContent.tsx` or any frontend rendering — the output markdown convention (`#`/`##` headings, bare pipe-row TOC tables, discarded header/footer content) is preserved exactly, so the existing frontend parser needs no changes.
- No changes to `chunking_job.py`, embedding, or spell-check stages — they consume `pages.text` the same way regardless of which engine produced it.
