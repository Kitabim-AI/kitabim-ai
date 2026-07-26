-- Migration 071: Add batch_embedding_jobs table for Gemini Batch API Embedding processing

CREATE TABLE IF NOT EXISTS batch_embedding_jobs (
    id VARCHAR(64) PRIMARY KEY,
    gemini_batch_id VARCHAR(255) UNIQUE,
    book_ids VARCHAR(64)[] NOT NULL,
    page_ids INT[] NOT NULL,
    chunk_ids INT[] NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'submitting',
    gcs_input_uri TEXT,
    gcs_output_uri TEXT,
    total_chunks INT NOT NULL DEFAULT 0,
    processed_chunks INT NOT NULL DEFAULT 0,
    error TEXT,
    submitted_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT check_batch_embedding_jobs_status CHECK (
        status IN ('submitting', 'submitted', 'running', 'succeeded', 'failed', 'cancelled')
    )
);

CREATE INDEX IF NOT EXISTS idx_batch_embedding_jobs_book_ids ON batch_embedding_jobs USING GIN (book_ids);
CREATE INDEX IF NOT EXISTS idx_batch_embedding_jobs_status ON batch_embedding_jobs(status);
