# API Code Review — 2026-07-22 (Batch Embedding)

**Branch:** feature/adk-2-upgrade-v2
**Verdict:** Request changes

## Issues

### `packages/backend-core/app/db/models.py`

- No issues found. `BatchEmbeddingJob` has a sequential migration, a `CheckConstraint` on `status`, `book_ids` correctly modeled as `ARRAY(String(64))` (no FK, matching `page_ids`/`chunk_ids` array convention), and `updated_at` has `onupdate=func.now()`.

### `packages/backend-core/migrations/071_add_batch_embedding_jobs.sql` / `071_rollback_add_batch_embedding_jobs.sql`

- No issues found. Sequential numbering is correct, `CHECK` constraint and `IF NOT EXISTS` guards mirror the landed `070_add_batch_ocr_jobs.sql` convention, GIN index on `book_ids` is appropriate for an array column, rollback drops the table with `CASCADE`.

### `packages/backend-core/app/db/seeds.py`

- No issues found. All four new config keys (`embed_batch_enabled`, `_timeout_hours`, `_max_chunks_per_job`, `_max_retry_count`) are actually read by `batch_embedding_service.py` — unlike `ocr_batch_size_per_job`/`_poll_interval`, which were seeded but never wired up (see prior OCR review).

### `packages/backend-core/app/services/batch_embedding_service.py`

- **[blocking]** Lines 323-328 — `output_file_name = batch_job_info.dest` (with an `elif hasattr(batch_job_info, "output_file")` fallback) treats `batch_job_info.dest` itself as a file-name string. The sibling `batch_ocr_service.py` (`_ingest_batch_ocr_results`, lines 405-407) establishes that `dest` is a container object exposing `.gcs_uri` and `.file_name` attributes: `dest = getattr(batch_job_info, "dest", None); output_file_name = getattr(dest, "file_name", None) if dest else None`. Passing the `dest` object directly to `client.files.download(file=output_file_name)` will fail against the real Gemini SDK response shape. Fix: mirror the OCR extraction exactly.
- **[blocking]** Lines 344-349 — `settings.gcp_storage_bucket` does not exist (`packages/backend-core/app/core/config.py` only defines `gcs_data_bucket` / `gcs_media_bucket`), and `storage.download_bytes(...)` does not exist on `storage_service` (only `read_bytes` is defined, correctly used at `batch_ocr_service.py:418`). This whole GCS-output fallback branch raises `AttributeError` the moment it runs. It's unreachable today only because `job.gcs_output_uri` is never assigned anywhere in this file before being read here — but that's itself a gap (the field is written by the OCR service on the GCS-destination path and should be here too for parity/audit). Fix both the attribute names and actually populate `job.gcs_output_uri` on the success path.
- **[blocking]** Lines 120-136 (`submit_batch_embedding_job`) + lines 420-450 (`poll_and_process_batch_embedding_jobs`) — chunks are ordered only by `Chunk.id` and sliced by `max_chunks_per_job` with no page-boundary awareness, so a single page's chunks can straddle two different `BatchEmbeddingJob` submissions. At ingestion, a page's succeeded/failed status is computed purely from the chunks present in *that* job's own `chunk_ids` (`p_chunks = [c[0] for c in c_info if c[1] == b_id and c[2] == p_num]`) — it never re-checks whether the page has other still-`NULL` chunks living in a sibling job. If a page's chunks split across jobs, the first job to succeed can mark the page `embedding_milestone="succeeded"` while chunks in the other job are still unembedded — permanently, since nothing re-claims a `succeeded` page. Under current defaults (`scanner_page_limit=100`, `max_chunks_per_job=5000`) this is unlikely to trigger, but it's a real, silent-data-loss bug waiting on a config change or a chunk-dense book. Fix: group chunks by `(book_id, page_number)` before slicing so a page never splits across jobs, or re-query `Chunk.embedding IS NULL` for the page's complete chunk set before marking it `succeeded`.
- **[suggestion]** Lines 471-481 — the `failed_pages` update path sets `embedding_milestone="failed"` and increments `retry_count` but never adds a `PipelineEvent("embedding_failed")`, unlike the `succeeded_pages` branch just above it and unlike `batch_ocr_service.py`'s `_record_page_ocr_failure` (which emits an event on both outcomes). Not a correctness bug — retries still happen via the milestone — but it's an observability gap relative to the established convention.
- **[suggestion]** Lines 34-35 — `_get_embedding_dimensionality` duplicates the exact `"gemini-embedding-2" in model_name` check already in `GeminiEmbeddings.aembed_documents` (`app/llm/models.py:538`). Worth extracting to one shared helper so a future third model doesn't have to be updated in two places.

### `packages/backend-core/tests/app/services/batch_embedding_service_test.py`

- **[suggestion]** `test_poll_and_process_batch_embedding_jobs_success` (line 239) sets `mock_batch_info.dest = "files/out_123"` — a bare string. This matches the implementation's incorrect assumption about the `dest` shape rather than the real Gemini SDK response (an object with `.file_name`/`.gcs_uri`, per the OCR precedent), so the test passes without ever exercising the bug described above. Update the mock (and the implementation) together so this test would actually catch it.
- **[suggestion]** Missing scenarios versus what the plan doc calls for: `JOB_STATE_FAILED`/`CANCELLED` handling, a per-line `error` on one chunk inside an otherwise-`SUCCEEDED` job (both the retry and the skip-after-`max_retries` paths), a submission that splits across multiple jobs when exceeding `max_chunks_per_job`, and the no-active-jobs early return (`active_jobs` empty → `processed_count == 0`, no Gemini API calls). Current coverage is submit-success, submit-no-chunks, submit-failure, poll-success, poll-timeout only.

## Summary

Schema, migration, and seed changes are clean and correctly wired up — a clear improvement over the OCR feature's dead-config mistake. The service layer has three blocking bugs: the batch output file is fetched with the wrong `dest` attribute shape (will crash on every real successful job), a GCS-fallback branch references two nonexistent APIs, and chunk-to-job slicing can silently strand a page's embeddings across two jobs. See the companion worker review for a related session-handling regression in `embedding_scanner.py`.
