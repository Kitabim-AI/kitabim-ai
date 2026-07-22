# Gemini Batch API Embedding Architecture & Implementation Plan

## Executive Summary

This document outlines the architecture and implementation plan to integrate the **Gemini Batch API** for vector embeddings generation in **Kitabim.AI**.

Using Gemini Batch API for bulk embedding tasks provides a **50% cost reduction** compared to standard online/real-time inference and avoids hitting standard API rate limits during large book ingestions. To ensure zero disruption to current operations, the system will support a **dual-mode architecture**:
- **Online Mode (Default / Fallback)**: Real-time embedding pipeline using `GeminiEmbeddings.aembed_documents()` (`batchEmbedContents`).
- **Batch Mode**: Asynchronous batch processing using `client.batches.create()` with GCS input/output JSONL datasets and Gemini Files API.

The feature will be controlled dynamically via a system configuration flag (`use_batch_embedding_api`) stored in the `system_configs` table. Administrators can toggle between modes at runtime without restarting services.

---

## Technical Architecture

```mermaid
flowchart TD
    subgraph Trigger & Ingestion
        A[Embedding Scanner] --> B{system_config:\nuse_batch_embedding_api}
    end

    subgraph Mode 1: Online Embedding (Existing)
        B -- false --> C[Standard embedding_job]
        C --> D[Fetch unembedded chunks for page]
        D --> E[Gemini API: aembed_documents / batchEmbedContents]
        E --> F[Update Chunk.embedding & Page embedding_milestone]
    end

    subgraph Mode 2: Batch Embedding (New)
        B -- true --> G[Submit Batch Embedding Job]
        G --> H[Extract Chunks & Build JSONL Dataset]
        H --> I[Upload JSONL to GCS & Gemini Files API]
        I --> J[Call client.batches.create]
        J --> K[Record batch_embedding_jobs entry in DB]
        
        L[Batch Embedding Poller Scanner] --> M[Poll client.batches.get]
        M --> N{Job Status}
        N -- RUNNING/PENDING --> O[Wait for next poll cycle]
        N -- SUCCEEDED --> P[Download Output JSONL from Gemini/GCS]
        P --> Q[Parse Embeddings & Update Chunk.embedding in DB]
        Q --> R[Mark Pages & Book embedding_milestone succeeded]
        N -- FAILED --> S[Mark Pages/Chunks Failed / Trigger Retries]
    end
```

---

## Detailed Design Components

### 1. Database Schema & System Configuration

#### Database Migration (`packages/backend-core/migrations/071_add_batch_embedding_jobs.sql`)
A new table `batch_embedding_jobs` will track the lifecycle of Gemini Batch API embedding requests.

```sql
CREATE TABLE IF NOT EXISTS batch_embedding_jobs (
    id VARCHAR(64) PRIMARY KEY, -- UUID
    gemini_batch_id VARCHAR(255) UNIQUE, -- Gemini API batch job name (e.g. 'batches/98765432')
    book_id VARCHAR(64) NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    page_ids INT[] NOT NULL, -- Array of Page IDs included in batch
    chunk_ids INT[] NOT NULL, -- Array of Chunk IDs included in batch
    status VARCHAR(20) NOT NULL DEFAULT 'submitting', -- 'submitting', 'submitted', 'running', 'succeeded', 'failed', 'cancelled'
    gcs_input_uri TEXT,
    gcs_output_uri TEXT,
    total_chunks INT NOT NULL DEFAULT 0,
    processed_chunks INT NOT NULL DEFAULT 0,
    error TEXT,
    submitted_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_batch_embedding_jobs_book_id ON batch_embedding_jobs(book_id);
CREATE INDEX idx_batch_embedding_jobs_status ON batch_embedding_jobs(status);
```

Rollback migration (`packages/backend-core/migrations/071_rollback_add_batch_embedding_jobs.sql`):
```sql
DROP TABLE IF EXISTS batch_embedding_jobs CASCADE;
```

#### System Config Defaults (`packages/backend-core/app/db/seeds.py`)
Add the following system configuration keys:

| Config Key | Default Value | Description |
| :--- | :--- | :--- |
| `use_batch_embedding_api` | `false` | Dynamically enables/disables Batch API embedding processing (`true`/`false`). |
| `gemini_batch_embedding_timeout_hours` | `24` | Timeout threshold after which a pending/running batch job is marked stale and retried. |

---

### 2. Service Layer (`packages/backend-core/app/services/batch_embedding_service.py`)

Provides core utilities for:
1. **JSONL Format Assembly**: Converts unembedded chunks into JSONL request lines adhering to Google GenAI Batch API format for embedding requests:
   ```json
   {
     "custom_id": "chunk_1024",
     "request": {
       "content": {
         "parts": [
           {"text": "Sample text content of the chunk..."}
         ]
       },
       "outputDimensionality": 768
     }
   }
   ```
2. **Submission (`submit_batch_embedding_job`)**:
   - Queries idle pages/chunks for a `book_id`.
   - Builds JSONL dataset.
   - Uploads audit JSONL payload to GCS storage (`batch_embedding/inputs/<job_id>.jsonl`).
   - Uploads payload to Gemini Files API (`client.files.upload()`).
   - Submits batch job via `client.batches.create(model=embedding_model, src=uploaded_file.name)`.
   - Records `BatchEmbeddingJob` entry in DB and updates page status to `in_progress`.
3. **Polling & Ingestion (`poll_and_process_batch_embedding_jobs`)**:
   - Queries `BatchEmbeddingJob` records with `status.in_(["submitting", "submitted", "running"])`.
   - Queries status from Gemini API (`client.batches.get(name=job.gemini_batch_id)`).
   - Upon `JOB_STATE_SUCCEEDED`:
     - Downloads result JSONL output (`client.files.download()` or GCS).
     - Parses vector float array per `custom_id` (`chunk_<id>`).
     - Batch updates `Chunk.embedding` in database.
     - Sets page `embedding_milestone="succeeded"`, `is_indexed=True`, and emits pipeline events.
     - Updates book milestone using `BookMilestoneService.update_book_milestone_for_step()`.
   - Upon failure or timeout (> 24 hrs):
     - Marks job status as `failed` and resets page/chunk retries.

---

### 3. Worker Scanners & Scheduling

1. **`services/worker/scanners/embedding_scanner.py`**:
   - Reads `use_batch_embedding_api` setting from `SystemConfigsRepository`.
   - If `use_batch_embedding_api` is `True`: Groups idle embedding pages by `book_id` and invokes `submit_batch_embedding_job()`.
   - If `False`: Enqueues standard real-time `embedding_job`.
2. **`services/worker/scanners/batch_embedding_poller_scanner.py`**:
   - Runs periodically (every 1 minute) in the worker process to invoke `poll_and_process_batch_embedding_jobs()`.
3. **`services/worker/scanners/stale_watchdog_scanner.py`**:
   - Updated to monitor stuck `BatchEmbeddingJob` instances (jobs in `submitted`/`running` for > 2 hours with no progress) and trigger recovery.

---

### 4. Verification & Testing

1. **Unit & Integration Tests**:
   - `packages/backend-core/tests/app/services/batch_embedding_service_test.py`: Tests JSONL payload generation, batch submission mocking, result JSONL parsing, database vector updates, and failure recovery.
2. **Local End-to-End Test**:
   - Enable `use_batch_embedding_api = "true"` via DB seed / admin config.
   - Run document ingestion pipeline and verify batch job submission, poller execution, vector persistence, and book milestone completion.

---
