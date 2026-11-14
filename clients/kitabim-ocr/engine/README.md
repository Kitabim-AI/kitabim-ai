# Kitabim OCR Engine

## Overview
Core OCR processing, layout analysis, dictionary validation, queue scheduling, and local workspace persistence for the standalone Kitabim OCR desktop client. It coordinates Surya OCR model inference, image preprocessing (bleed-through suppression, dot enhancement), Uyghur text cleanup, line-end dehyphenation, and sequential background queue management.

## Interface
- `[config.py:get_configured_engine]`: Resolves configured OCR engine from `KITABIM_OCR_ENGINE` or `OCR_ENGINE` (default `'surya'`).
- `[config.py:get_configured_concurrency]`: Reads concurrency from `KITABIM_OCR_CONCURRENCY` or `OCR_CONCURRENCY` (default 4).
- `[config.py:resolve_concurrency]`: Resolves concurrency clamped to `[config.py:MAX_SURYA_CONCURRENCY]` (4).
- `[config.py:get_configured_page_timeout]`: Reads per-page timeout from `KITABIM_OCR_PAGE_TIMEOUT` (default 120.0s).
- `[config.py:get_configured_max_retries]`: Reads retry limit from `KITABIM_OCR_MAX_RETRIES` (default 2).
- `[config.py:apply_surya_token_limits]`: Applies `SURYA_MAX_TOKENS_FULL_PAGE` environment limit (default 2500).
- `[config.py:is_bleed_through_suppression_enabled]`: Reads `KITABIM_OCR_BLEED_THROUGH_SUPPRESSION` toggle.
- `[config.py:get_configured_zoom_factor]`: Reads `KITABIM_OCR_ZOOM_FACTOR` (clamped [1.5, 5.0], default 3.0).
- `[config.py:is_dot_enhancement_enabled]`: Reads `KITABIM_OCR_DOT_ENHANCEMENT` toggle.
- `[dictionary.py:fetch_and_cache_words]`: Downloads dictionary bundle from Kitabim API and writes cache file.
- `[dictionary.py:load_cached_words]`: Loads cached words set from disk.
- `[dictionary.py:get_valid_words]`: Retrieves valid words set via in-memory cache, disk cache, or remote API.
- `[line_ends.py:get_line_detector]`: Thread-safe getter for process-wide Surya text-line detector.
- `[line_ends.py:read_line_end_words]`: Detects normalized words ending with line-break hyphens on page margins.
- `[line_ends.py:read_bottom_line_end_word]`: Crops only the bottom body line to verify a trailing hyphenated stem.
- `[line_ends.py:join_cross_page_hyphenated_words]`: Joins words split by line-break hyphens across contiguous body pages `(p, p + 1)`.
- `[line_ends.py:apply_cross_page_dehyphenation]`: Applies cross-page dehyphenation across contiguous freshly Surya-OCR'd body pages.
- `[queue.py:BookQueueManager]`: Sequential background queue manager coordinating single-book OCR execution.
  - `[queue.py:BookQueueManager.enqueue]`: Enqueues session ID and transitions metadata status.
  - `[queue.py:BookQueueManager.cancel]`: Cancels pending queued session before execution.
  - `[queue.py:BookQueueManager.reset_interrupted_sessions]`: Resets lingering active sessions to idle or completed.
  - `[queue.py:BookQueueManager.recover_queue]`: Recovers and re-enqueues unfinished sessions on startup.
  - `[queue.py:BookQueueManager.wait_all]`: Waits for all active and queued sessions to complete.
- `[recognize.py:LowConfidenceOcrError]`: Exception raised on empty or low-confidence OCR output for non-blank pages.
- `[recognize.py:PageOcrResult]`: Dataclass returned by `ocr_page_with_meta` carrying `text`, `detected_page_number`, and `ended_with_hyphen`.
- `[recognize.py:get_recognition_predictor]`: Instantiates or returns Surya recognition predictor.
- `[recognize.py:ocr_page]`: Async page OCR executor orchestrating zoom, preprocessing, inference, Table-of-Contents line-aware recovery and pipe-table formatting, and retry loops.
- `[recognize.py:ocr_page_with_meta]`: Async page OCR executor returning `PageOcrResult` with bleed-through-safe sidecar `detected_page_number` and `ended_with_hyphen`.
- `[recognize.py:is_page_blank]`: Checks rendered Pixmap variance against blank page threshold.
- `[recognize.py:suppress_bleed_through]`: Cleans background show-through ink from scanned pages.
- `[recognize.py:enhance_dots_and_contrast]`: Enhances diacritics and dots for Uyghur Arabic script.
- `[recognize.py:get_adaptive_page_zoom]`: Computes rendering zoom factor based on input page dimensions.
- `[text_cleanup.py:clean_uyghur_text]`: Sanitizes OCR output, strips isolated page numbers, and normalizes typography.
- `[text_cleanup.py:strip_page_numbers_with_capture]`: Strips isolated header/footer page numbers and captures the printed page number sidecar.
- `[text_cleanup.py:extract_standalone_page_number]`: Extracts pure-digit printed page candidates (`1 <= n <= 5000`) from header/footer lines.
- `[text_cleanup.py:normalize_uyghur_chars]`: Normalizes unicode codepoints for Uyghur Arabic characters.
- `[text_cleanup.py:is_toc_page]`: Evaluates if page text represents a Table of Contents.
- `[text_cleanup.py:is_block_repetition_loop]`: Identifies degenerate looping hallucinations while preserving punctuated literary vocalizations and table rows.
- `[text_cleanup.py:is_hallucinated_arabic_block]`: Identifies unvocalized non-Uyghur Arabic bleed-through hallucinations while preserving Turkic consonants and vocalized quotations.
- `[text_cleanup.py:is_hallucinated_ghost_text]`: Identifies pseudo-Uyghur bleed-through hallucinations with garbled internal syllable loops or extreme content-word duplication.
- `[text_cleanup.py:is_degenerate_ocr_output]`: Enforces upper bounds on character counts and catches per-block or consecutive-line runaway loops without rejecting structured quiz/form pages.
- `[workdir.py:PageState]`: Dataclass modeling individual page OCR results, sidecar `detected_page_number`, `skipped`, and review state.
- `[workdir.py:OcrWorkDir]`: Local filesystem manager for session state, `book.json`, `pages.json`, and rendered PNGs.

## Invariants
- `[queue.py:BookQueueManager]`: Exactly one book session undergoes OCR processing at any given time; FIFO ordering serialized with `asyncio.Lock` and `threading.RLock`.
- `[config.py:resolve_concurrency]`: Surya OCR parallelism is strictly clamped between 1 and `[config.py:MAX_SURYA_CONCURRENCY]` (4).
- `[workdir.py:OcrWorkDir._write_atomic]`: Session metadata writes are serialized through atomic temporary file swaps `.{filename}.tmp.<pid>.<tid>`.
- `[line_ends.py:get_line_detector]`: Single detector instance loaded under process-wide `[line_ends.py:_detector_lock]`.

## Side Effects
- `[dictionary.py:fetch_and_cache_words]`: Issues network HTTP GET requests to `${KITABIM_BASE_URL}/dictionary/words-bundle` and writes disk cache to `~/.cache/kitabim-ocr/words_dict.txt`.
- `[workdir.py:OcrWorkDir.save]`: Writes session JSON files (`book.json`, `pages.json`) and stores page image PNGs under `pages/` on local disk.
- `[queue.py:BookQueueManager._process_loop]`: Mutates local session statuses (`processing`, `completed`, `failed`) on the filesystem.

## Verification
- Run: `pytest clients/kitabim-ocr/tests`
