# Gemini Batch API OCR Architecture & Implementation Plan

## Executive Summary

This document outlines the architecture and implementation plan to integrate the **Gemini Batch API** for OCR page processing in **Kitabim.AI**.

Using Gemini Batch API provides a **50% cost reduction** compared to standard online/real-time inference. To ensure zero disruption to current operations, the system will support a **dual-mode architecture**:
- **Online Mode (Default)**: Existing real-time OCR pipeline using `client.aio.models.generate_content`.
- **Batch Mode**: Asynchronous batch processing using `client.batches.create()` and GCS input/output datasets.

The feature will be controlled dynamically via a system configuration flag (`ocr_batch_enabled`) stored in the `system_configs` table. Administrators can switch between modes at runtime without restarting services.

---

## Technical Architecture

```mermaid
flowchart TD
    subgraph Trigger & Ingestion
        A[OCR Scanner] --> B{system_config:\nocr_batch_enabled}
    end

    subgraph Mode 1: Online OCR (Existing)
        B -- false --> C[Standard ocr_job]
        C --> D[Render Page Image]
        D --> E[Gemini Vision API: generate_content]
        E --> F[Update Page.text & Emit ocr_succeeded Event]
    end

    subgraph Mode 2: Batch OCR (New)
        B -- true --> G[Batch OCR Submission Job]
        G --> H[Extract & Upload Page Images/JSONL to GCS]
        H --> I[Call client.batches.create]
        I --> J[Record batch_ocr_jobs entry]
        
        K[Batch OCR Poller Scanner] --> L[Poll client.batches.get]
        L --> M{Job Status}
        M -- RUNNING/PENDING --> N[Wait for next poll cycle]
        M -- SUCCEEDED --> O[Download Result JSONL from GCS]
        O --> P[Parse Results & Update Pages & Emit ocr_succeeded Events]
        M -- FAILED --> Q[Mark Pages Failed / Fallback to Retries]
    end
```

---

## Detailed Design Components

### 1. Database Schema & System Configuration

#### Database Migration (`migrations/067_add_batch_ocr_jobs.sql`)
A new table `batch_ocr_jobs` will track the lifecycle of Gemini Batch API requests.

```sql
CREATE TABLE IF NOT EXISTS batch_ocr_jobs (
    id VARCHAR(64) PRIMARY KEY, -- UUID or custom ID
    gemini_batch_id VARCHAR(255) UNIQUE, -- Gemini API batch job name (e.g. 'batches/12345678')
    book_id VARCHAR(64) NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    page_ids INT[] NOT NULL, -- Array of Page IDs included in batch
    status VARCHAR(20) NOT NULL DEFAULT 'submitting', -- 'submitting', 'submitted', 'running', 'succeeded', 'failed', 'cancelled'
    gcs_input_uri TEXT,
    gcs_output_uri TEXT,
    total_pages INT NOT NULL DEFAULT 0,
    processed_pages INT NOT NULL DEFAULT 0,
    error TEXT,
    submitted_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_batch_ocr_jobs_book_id ON batch_ocr_jobs(book_id);
CREATE INDEX idx_batch_ocr_jobs_status ON batch_ocr_jobs(status);
```

#### System Config Defaults (`packages/backend-core/app/db/seeds.py`)
Add the following system configuration keys:

| Config Key | Default Value | Description |
| :--- | :--- | :--- |
| `ocr_batch_enabled` | `false` | Dynamically enables/disables Batch API OCR processing (`true`/`false`). |
| `ocr_batch_size_per_job` | `50` | Maximum number of pages bundled into a single Batch API job. |
| `gemini_batch_ocr_poll_interval` | `120` | Interval in seconds between poller executions to check batch job status. |
| `ocr_batch_timeout_hours` | `24` | Timeout threshold after which a pending/running batch job is marked stale and retried. |

---

### 2. Core Service Extensions (`packages/backend-core/app/llm/` & `app/services/`)

#### A. Batch Request Builder & Parser (`app/services/batch_ocr_service.py`)
Provides core utilities for:
1. **JSONL Format Assembly**: Converts page images and system OCR prompts into JSONL request lines adhering to Google GenAI Batch API format.
   ```json
   {
     "custom_id": "page_1024",
     "request": {
       "contents": [
         {
           "parts": [
             {"text": "<OCR_PROMPT>"},
             {
               "inline_data": {
                 "mime_type": "image/jpeg",
                 "data": "<BASE64_JPEG_DATA>"
               }
             }
           ]
         }
       ],
       "generation_config": { "temperature": 0.0 }
     }
   }
   ```
2. **GCS Upload / Download**: Uploads `.jsonl` input files to `gs://<bucket>/batch_ocr/inputs/<job_id>.jsonl` and fetches output `.jsonl` from `gs://<bucket>/batch_ocr/outputs/<job_id>.jsonl`.
3. **Batch Job Submission**: Uses `genai.Client().batches.create(...)` to launch Gemini Batch jobs.
4. **Batch Status Ingestion**: Reads result JSONL line by line, maps `custom_id` (`page_<id>`) to database pages, cleans text via `clean_uyghur_text()`, checks table of contents (`is_toc_page()`), updates `Page.text`, and marks `Page.ocr_milestone = 'succeeded'`.

---

### 3. Worker Pipelines & Scanners (`services/worker/`)

#### A. Ingestion Router (`services/worker/jobs/ocr_job.py`)
Modify `ocr_job` to inspect `ocr_batch_enabled`:
- If `ocr_batch_enabled == "false"`: Run existing real-time page-by-page vision calls via `ocr_page_with_gemini()`.
- If `ocr_batch_enabled == "true"`:
  1. Render page image pixmaps from PDF.
  2. Assemble JSONL file and upload to GCS.
  3. Call `client.batches.create()`.
  4. Create `batch_ocr_jobs` row in PostgreSQL.
  5. Keep `Page.ocr_milestone = 'in_progress'`.

#### B. Batch Poller Scanner (`services/worker/scanners/batch_ocr_poller_scanner.py`)
A new periodic background scanner running every 2 minutes:
1. Queries `batch_ocr_jobs` where `status IN ('submitted', 'running')`.
2. Calls `client.batches.get(name=job.gemini_batch_id)`.
3. Handles state transitions:
   - **`JOB_STATE_SUCCEEDED`**: Triggers result download, updates page records, emits `ocr_succeeded` events, updates book milestone.
   - **`JOB_STATE_FAILED` / `JOB_STATE_CANCELLED`**: Logs failure, marks job `failed`, sets `Page.ocr_milestone = 'failed'` (or increments `retry_count`) for re-claiming.
   - **Stale/Timeout (>24 hours)**: Marks job expired and unlocks pages for retry.

---

## Downstream Compatibility & Zero-Downtime Guarantee

1. **Downstream Pipelines Unchanged**:
   - `chunking_scanner`, `spell_check_scanner`, and `embedding_scanner` react to `PipelineEvent(event_type="ocr_succeeded")` and `Page.ocr_milestone == 'succeeded'`.
   - Batch OCR emits the exact same `ocr_succeeded` events upon batch completion, guaranteeing 100% compatibility with all existing downstream workers.
2. **Seamless Mode Switching**:
   - Toggling `ocr_batch_enabled` from `false` to `true` instantly routes new OCR jobs to the Batch API.
   - Toggling back to `false` routes new jobs to standard real-time API while allowing existing submitted batch jobs to complete via the poller scanner.

---

## File Changes Overview

### Backend Core (`packages/backend-core/`)
- `[NEW]` `migrations/067_add_batch_ocr_jobs.sql`: Migration script for `batch_ocr_jobs` table.
- `[NEW]` `app/db/models.py`: Add `BatchOCRJob` model mapping.
- `[NEW]` `app/services/batch_ocr_service.py`: JSONL formatting, GCS handling, Gemini Batch API client calls, and output parsing.
- `[MODIFY]` `app/db/seeds.py`: Add default `ocr_batch_enabled`, `ocr_batch_size_per_job`, `gemini_batch_ocr_poll_interval`.
- `[MODIFY]` `app/services/ocr_service.py`: Add helper wrappers for batch OCR job submission and ingestion.

### Worker Service (`services/worker/`)
- `[NEW]` `services/worker/scanners/batch_ocr_poller_scanner.py`: Scanner for monitoring running batch jobs and ingesting results.
- `[MODIFY]` `services/worker/jobs/ocr_job.py`: Add conditional switch to delegate to batch submission when flag is active.
- `[MODIFY]` `services/worker/worker.py`: Register `batch_ocr_poller_scanner` in cron schedules.

---

## Verification & Testing Strategy

1. **Unit Tests**:
   - `packages/backend-core/tests/app/services/batch_ocr_service_test.py`: Test JSONL serialization/deserialization, prompt embedding, and result parsing.
2. **Integration Tests**:
   - Mock Gemini `client.batches.create` and `client.batches.get` endpoints.
   - Verify page milestone transitions (`idle` -> `in_progress` -> `succeeded`) and `PipelineEvent` emission.
3. **End-to-End Local Verification**:
   - Rebuild local docker container: `./deploy/local/rebuild-and-restart.sh worker`
   - Set `ocr_batch_enabled = 'true'` in System Configs.
   - Upload sample PDF and verify batch job lifecycle.
