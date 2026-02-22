# Book Processing Pipeline Diagram

Here is a visual representation of the book processing pipeline, including triggers, milestone changes, and outputs.

## Overview

The pipeline processes PDF books through multiple stages:
1. **Initialization**: Book upload or discovery → Job enqueue
2. **OCR Stage**: Extract text from PDF pages using Gemini Vision API
3. **Indexing Stage**: Chunk text and generate embeddings using Gemini Embeddings API
4. **Finalization**: Determine final book status and cleanup

## Pipeline Diagram

```mermaid
flowchart TD
    %% Triggers
    subgraph Triggers [Event Triggers]
        T1[User Uploads PDF<br/>POST /api/books/upload] --> |Creates Book Record| Enqueue
        T2[GCS Discovery Sync<br/>Scheduled/Manual] --> |Discovers New Books| Enqueue
    end

    %% Initialization Stage
    Enqueue[Enqueue Redis Job<br/>via ARQ Worker]
    Enqueue --> InitDB([Book Created<br/>status: pending<br/>processing_step: ocr])

    %% Job Execution
    InitDB --> WorkerStart{Worker: process_pdf_job}

    subgraph PDF Processing Pipeline [PDF Processing Pipeline]
        WorkerStart --> ConfigCheck{System Configs}
        ConfigCheck --> |pdf_processing_enabled=false| Skipped([Job Skipped])
        ConfigCheck --> |Check llm_cb_* configs| ConfigUpdate[Update Circuit Breaker Config]

        ConfigUpdate --> BookCheck{Book Already Ready?}
        BookCheck --> |Yes| AlreadyDone([Mark Job Succeeded])
        BookCheck --> |No| Lock[Acquire Processing Lock]

        Lock --> |Lock Busy| LockFail([Job Skipped: Lock Busy])
        Lock --> |Lock Acquired| CBCheck{Circuit Breaker Open?}
        CBCheck --> |Yes| CBSkip([Job Skipped: CB Open])
        CBCheck --> |No| DownloadCloud[Download PDF from Storage<br/>Local Cache or Re-download]

        DownloadCloud --> |Error| DownloadFail([Status: error])
        DownloadCloud --> |Success| ExtractMeta[Count Pages<br/>Create Page Records<br/>Status: ocr_processing]

        ExtractMeta --> CoverExtract[Extract Cover<br/>First Page as JPG]
        CoverExtract -.-> OutputCover[(Cover Uploaded to Storage<br/>Local + GCS)]

        %% OCR Stage
        CoverExtract --> OCR_Loop
        subgraph OCR [OCR Stage - Parallel Processing]
            OCR_Loop[Find Pages<br/>status != ocr_done] --> OCR_Semaphore[Semaphore Limit<br/>max_parallel_pages]
            OCR_Semaphore --> OCR_PageCheck{Page Already<br/>Verified?}
            OCR_PageCheck --> |Yes| OCR_Skip[Skip OCR]
            OCR_PageCheck --> |No| OCR_PageStatus[Update Page<br/>status: ocr_processing]

            OCR_PageStatus --> OCR_CB{Circuit Breaker<br/>Check}
            OCR_CB --> |Open| OCR_Abort([Stop OCR Loop<br/>Leave Pending])
            OCR_CB --> |OK| OCR_Process[Gemini Vision API<br/>Extract Text from Image]

            OCR_Process --> |Success| OCR_Normalize[Normalize Markdown]
            OCR_Normalize --> PageComplete(Update Page<br/>status: ocr_done<br/>text: normalized_text)

            OCR_Process --> |Failure| PageError(Update Page<br/>status: error<br/>error: message)
        end
        PageComplete -.-> OutputText[(Normalized Markdown<br/>Stored in pages.text)]

        %% Embedding Stage
        OCR_Loop --> Embed_Loop
        subgraph Embedding [Chunking & Embedding Stage]
            Embed_Loop[Find Pages<br/>status=ocr_done AND<br/>is_indexed=false] --> Embed_Count{Pages to Index?}
            Embed_Count --> |No| Embed_Skip[Skip Indexing]
            Embed_Count --> |Yes| Embed_BookStatus[Update Book<br/>status: indexing]

            Embed_BookStatus --> Embed_CB1{Circuit Breaker<br/>Check}
            Embed_CB1 --> |Open| Embed_Abort([Skip Indexing<br/>Will Retry Later])
            Embed_CB1 --> |OK| Embed_Batch[Process in Batches<br/>batch_size=20]

            Embed_Batch --> Embed_PageStatus[Update Pages<br/>status: indexing]
            Embed_PageStatus --> Embed_CB2{Circuit Breaker<br/>Per-Batch Check}
            Embed_CB2 --> |Open| Embed_BatchAbort([Stop Processing<br/>Leave Unindexed])
            Embed_CB2 --> |OK| Chunk[Chunk Text<br/>RecursiveCharacterTextSplitter<br/>chunk_size=1000, overlap=200]

            Chunk --> EmbedText[Gemini Embeddings API<br/>Batch Embed All Chunks]

            EmbedText --> |Success| SaveChunks[Delete Old Chunks<br/>Insert New Chunks<br/>to chunks table]
            SaveChunks --> ChunkComplete(Update Pages<br/>status: indexed<br/>is_indexed: true)

            EmbedText --> |Failure| EmbedError([Record Error<br/>Leave Unindexed])
        end
        ChunkComplete -.-> OutputVector[(Vector Embeddings<br/>Stored in chunks table<br/>with pgvector)]

        %% Finalization
        Embed_Loop --> FinalCheck[Aggregate Stats<br/>Count by Status]
    end

    %% Milestones / Final State
    subgraph Final State [Final Status Determination]
        FinalCheck --> CountStats{Count Pages:<br/>OCR Done vs Indexed}
        CountStats --> |All OCR + All Indexed| Ready([Book Status: ready])
        CountStats --> |All OCR + Not All Indexed| OcrDone([Book Status: ocr_done])
        CountStats --> |Not All OCR| ErrorState([Book Status: error])

        Ready --> Cleanup[Cleanup:<br/>1. Delete Local Files if GCS<br/>2. Update Job: succeeded<br/>3. Trigger Discovery Check]
        OcrDone --> PartialCleanup[Update Job: succeeded<br/>Note: Indexing Pending]
        ErrorState --> ErrorCleanup[Update Job: failed<br/>Release Lock]
    end

    Cleanup --> NextDiscovery[Trigger GCS Discovery<br/>Check for New Books]

    classDef output fill:#d4f1f4,stroke:#189ab4,stroke-width:2px,color:#05445E;
    classDef trigger fill:#ffe8d6,stroke:#b5838d,stroke-width:2px,color:#6d6875;
    classDef state fill:#e9edc9,stroke:#606c38,stroke-width:2px;
    classDef error fill:#ffcccb,stroke:#d32f2f,stroke-width:2px;

    class OutputCover,OutputText,OutputVector output;
    class T1,T2 trigger;
    class InitDB,Ready,OcrDone,AlreadyDone state;
    class ErrorState,DownloadFail,Skipped,LockFail,CBSkip,OCR_Abort,Embed_Abort,PageError,EmbedError,Embed_BatchAbort,ErrorCleanup error;
```

## Status Flow

### Book Statuses
- `pending` → Initial state after upload/discovery
- `ocr_processing` → OCR in progress
- `indexing` → Embedding generation in progress
- `ocr_done` → OCR complete, but embeddings pending
- `ready` → Fully processed and searchable
- `error` → Processing failed

### Page Statuses
- `pending` → Created but not processed
- `ocr_processing` → OCR in progress for this page
- `ocr_done` → Text extracted, ready for indexing
- `indexing` → Embedding generation in progress
- `indexed` → Fully processed with embeddings
- `error` → OCR failed for this page

## Key Components

### Storage
- **Local**: Temporary cache in `settings.uploads_dir` and `settings.covers_dir`
- **Cloud**: GCS bucket for persistent storage (PDFs and covers)
- **Database**: PostgreSQL with pgvector extension for embeddings

### APIs Used
- **Gemini Vision API**: OCR text extraction from PDF pages
- **Gemini Embeddings API**: Generate vector embeddings for semantic search

### Circuit Breaker
- Prevents overwhelming LLM APIs during outages
- Configurable via `llm_cb_failure_threshold` and `llm_cb_recovery_seconds`
- Checked before OCR and embedding operations

### Processing Lock
- Prevents concurrent processing of the same book
- TTL-based (configurable via `job_lock_ttl_seconds`)
- Auto-releases on job completion or timeout
